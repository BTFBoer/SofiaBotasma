"""Per-chat message batching.

People often send a thought in several quick messages ("wait" / "no" /
"actually…"). A person on the other end reads them all and answers once.
Incoming messages are therefore collected for a short debounce window and
processed as one batch. A per-chat lock guarantees replies never overlap;
messages that arrive while Sofia is "typing" are picked up afterwards (or
merged in, see the bot layer).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.utils.logging import get_logger

log = get_logger(__name__)

ProcessFn = Callable[[int, list[int]], Awaitable[None]]


@dataclass
class _ChatState:
    pending: list[int] = field(default_factory=list)
    first_pending_at: float | None = None
    timer: asyncio.Task[None] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChatCoordinator:
    def __init__(self, process: ProcessFn, *, debounce: float = 2.2, max_wait: float = 9.0) -> None:
        self._process = process
        self.debounce = max(0.0, debounce)
        self.max_wait = max(self.debounce, max_wait)
        self._chats: dict[int, _ChatState] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def _chat(self, chat_id: int) -> _ChatState:
        return self._chats.setdefault(chat_id, _ChatState())

    def submit(self, chat_id: int, message_id: int) -> None:
        st = self._chat(chat_id)
        st.pending.append(message_id)
        now = time.monotonic()
        if st.first_pending_at is None:
            st.first_pending_at = now
        if st.timer is not None and not st.timer.done():
            st.timer.cancel()
        waited = now - st.first_pending_at
        delay = max(0.0, min(self.debounce, self.max_wait - waited))
        task = asyncio.create_task(self._fire(chat_id, delay))
        st.timer = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def take_pending(self, chat_id: int) -> list[int]:
        """Remove and return messages that arrived after a batch started processing."""
        st = self._chat(chat_id)
        taken, st.pending = st.pending, []
        st.first_pending_at = None
        if st.timer is not None and not st.timer.done():
            st.timer.cancel()
        st.timer = None
        return taken

    def has_pending(self, chat_id: int) -> bool:
        return bool(self._chat(chat_id).pending)

    def is_busy(self, chat_id: int) -> bool:
        st = self._chat(chat_id)
        return bool(st.pending) or st.lock.locked()

    def lock(self, chat_id: int) -> asyncio.Lock:
        """The per-chat lock; hold it to send something that must not interleave with a reply."""
        return self._chat(chat_id).lock

    def clear(self, chat_id: int) -> None:
        self.take_pending(chat_id)

    async def _fire(self, chat_id: int, delay: float) -> None:
        st = self._chat(chat_id)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if st.timer is asyncio.current_task():
            st.timer = None  # past the debounce: no longer cancellable by new messages
        async with st.lock:
            batch, st.pending = st.pending, []
            st.first_pending_at = None
            if not batch:
                return
            try:
                await self._process(chat_id, batch)
            except Exception:
                log.exception("processing batch failed")

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

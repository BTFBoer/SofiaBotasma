"""Human-feeling response timing and Telegram's real typing indicator.

The goal is "a person who read your message and typed a reply", not
"a slow bot". Ordinary replies land in roughly 1-8 seconds; long or
emotionally heavy ones may take a little longer. Time already spent waiting
for the model counts towards the delay.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

TYPING_REFRESH_SECONDS = 4.5  # Telegram shows "typing" for ~5 s per chat action


@dataclass(frozen=True)
class BubbleTiming:
    pause_before: float  # silence before the typing indicator starts
    typing: float  # how long "typing…" is shown before the bubble appears


def _typing_seconds(text: str, rng: random.Random) -> float:
    chars_per_second = rng.uniform(7.0, 11.0)  # a fast thumb typist
    return len(text) / chars_per_second


def plan_timings(
    incoming_text: str,
    bubbles: list[str],
    *,
    already_elapsed: float = 0.0,
    weighty: bool = False,
    rng: random.Random | None = None,
) -> list[BubbleTiming]:
    """Return per-bubble timings.

    `already_elapsed` is time already spent (debounce + model latency) and is
    subtracted from the first bubble so slow models don't feel even slower.
    """
    rng = rng or random.Random()
    timings: list[BubbleTiming] = []
    if not bubbles:
        return timings

    read = min(2.5, len(incoming_text) / 45.0)
    first_typing = _typing_seconds(bubbles[0], rng)
    target = 0.8 + read + first_typing + rng.uniform(0.0, 1.2)
    upper = 11.0 if (weighty or len(bubbles[0]) > 280) else 8.0
    target = max(1.0, min(upper, target))
    remaining = max(0.4, target - already_elapsed)
    timings.append(BubbleTiming(pause_before=0.0, typing=remaining))

    for bubble in bubbles[1:]:
        pause = rng.uniform(0.3, 1.1)
        typing = max(0.7, min(6.0, _typing_seconds(bubble, rng) + rng.uniform(0.2, 0.8)))
        timings.append(BubbleTiming(pause_before=pause, typing=typing))
    return timings


class TypingIndicator:
    """Keeps Telegram's native 'typing…' action alive while active."""

    def __init__(self, send_action: Callable[[], Awaitable[object]]) -> None:
        self._send_action = send_action
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self._send_action()
            await asyncio.sleep(TYPING_REFRESH_SECONDS)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    async def __aenter__(self) -> TypingIndicator:
        self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

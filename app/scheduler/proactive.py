"""Optional spontaneous messages — rare, continuity-driven, never needy.

Hard rules (checked before the model is even asked):
- off unless /proactive on (default from PROACTIVE_DEFAULT)
- never during quiet hours (default 23:30–08:30 Europe/Amsterdam)
- never double-texting: if Sofia sent the last message, she waits for him
- at most PROACTIVE_MAX_PER_DAY (≤2) per local day, at least 6 h apart
- not within 3 h of the last exchange (that's just a conversation pausing)
- early in the relationship: only when there is a concrete reason

Then a dice roll with a small probability, higher when there's a concrete
hook (an event today, something he was dreading yesterday). Then the model
itself decides whether Sofia would actually text — "no" is a fine outcome.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from app.companion.engine import CompanionEngine, TurnPlan
from app.config import Settings
from app.controls import ControlService
from app.memory.store import MemoryStore
from app.utils.logging import get_logger
from app.utils.timeutil import relative_day

log = get_logger(__name__)

TICK_MINUTES = 30
MIN_GAP_AFTER_ACTIVITY = timedelta(hours=3)
MIN_GAP_BETWEEN_PROACTIVE = timedelta(hours=6)


@dataclass
class Hook:
    text: str
    strong: bool = False


@dataclass
class ProactiveInputs:
    now_local: datetime
    enabled: bool
    last_message_at: datetime | None
    last_message_role: str | None
    sent_today: int
    last_proactive_at: datetime | None
    familiarity: float
    hooks: list[Hook] = field(default_factory=list)


@dataclass
class ProactiveDecision:
    allowed: bool
    reason: str
    probability: float = 0.0


def in_quiet_hours(local: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    t = local.time()
    s, e = time(*start), time(*end)
    if s <= e:
        return s <= t < e
    return t >= s or t < e


def evaluate(inputs: ProactiveInputs, settings: Settings) -> ProactiveDecision:
    if not inputs.enabled:
        return ProactiveDecision(False, "disabled")
    if in_quiet_hours(inputs.now_local, settings.quiet_hours_start, settings.quiet_hours_end):
        return ProactiveDecision(False, "quiet hours")
    if inputs.last_message_at is None:
        return ProactiveDecision(False, "no conversation yet")
    if inputs.last_message_role == "assistant":
        return ProactiveDecision(False, "she sent the last message; no double texting")
    if inputs.sent_today >= settings.proactive_max_per_day:
        return ProactiveDecision(False, "daily cap reached")
    now = inputs.now_local
    if inputs.last_proactive_at and now - inputs.last_proactive_at < MIN_GAP_BETWEEN_PROACTIVE:
        return ProactiveDecision(False, "too soon after the previous spontaneous message")
    gap = now - inputs.last_message_at
    if gap < MIN_GAP_AFTER_ACTIVITY:
        return ProactiveDecision(False, "conversation was recent")

    strong = any(h.strong for h in inputs.hooks)
    if inputs.familiarity < 0.25 and not inputs.hooks:
        return ProactiveDecision(False, "too new for random check-ins")

    probability = 0.12 if strong else (0.05 if inputs.hooks else 0.015)
    if inputs.familiarity < 0.25:
        probability *= 0.5
    if gap > timedelta(days=3):
        probability *= 1.4
    return ProactiveDecision(True, "eligible", min(probability, 0.25))


async def gather_hooks(store: MemoryStore, now: datetime, today) -> list[Hook]:
    hooks: list[Hook] = []
    for thread in await store.list_threads("open"):
        if thread.due_date is not None:
            diff = (thread.due_date - today).days
            if -1 <= diff <= 1:
                hooks.append(Hook(f"{thread.content} (due {relative_day(thread.due_date, today)})", strong=True))
            elif 1 < diff <= 3:
                hooks.append(Hook(f"{thread.content} (due {relative_day(thread.due_date, today)})"))
        elif now - thread.updated_at < timedelta(days=3):
            hooks.append(Hook(thread.content))
    for mem in await store.list_memories("bram"):
        if mem.event_date is None:
            continue
        diff = (mem.event_date - today).days
        if diff in (0, -1):
            hooks.append(Hook(f"{mem.content} ({relative_day(mem.event_date, today)})", strong=True))
        elif 1 <= diff <= 3:
            hooks.append(Hook(f"{mem.content} ({relative_day(mem.event_date, today)})"))
    episodes = await store.list_episodes()
    if episodes:
        last = episodes[-1]
        if last.importance >= 0.7 and now - last.ended_at < timedelta(days=2):
            hooks.append(Hook(f"still on her mind: {last.title} — {last.summary}"))
    return hooks[:6]


class ProactiveScheduler:
    def __init__(
        self,
        settings: Settings,
        store: MemoryStore,
        engine: CompanionEngine,
        controls: ControlService,
        send_plan: Callable[[TurnPlan], Awaitable[bool]],
        chat_id: int,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.engine = engine
        self.controls = controls
        self.send_plan = send_plan
        self.chat_id = chat_id
        self.rng = rng or random.Random()

    async def build_inputs(self) -> ProactiveInputs:
        now = self.engine.clock()
        tz = self.settings.tz
        local = now.astimezone(tz)
        midnight_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        last = await self.store.last_message(self.chat_id)
        state = await self.engine.load_state()
        last_proactive = await self.store.last_proactive_at()
        return ProactiveInputs(
            now_local=local,
            enabled=await self.controls.proactive_enabled(),
            last_message_at=last.created_at.astimezone(tz) if last else None,
            last_message_role=last.role if last else None,
            sent_today=await self.store.proactive_sent_since(midnight_local),
            last_proactive_at=last_proactive.astimezone(tz) if last_proactive else None,
            familiarity=state.dims["familiarity"],
            hooks=await gather_hooks(self.store, now, local.date()),
        )

    async def tick(self) -> bool:
        try:
            inputs = await self.build_inputs()
            decision = evaluate(inputs, self.settings)
            if not decision.allowed:
                log.debug("proactive skipped: %s", decision.reason)
                return False
            if self.rng.random() >= decision.probability:
                return False
            plan = await self.engine.plan_proactive(self.chat_id, [h.text for h in inputs.hooks])
            if plan is None:
                log.info("proactive: model chose not to text")
                return False
            sent = await self.send_plan(plan)
            if sent:
                reason = inputs.hooks[0].text[:120] if inputs.hooks else "spontaneous"
                await self.store.log_proactive(reason)
                log.info("proactive message sent")
            return sent
        except Exception:
            log.exception("proactive tick failed")
            return False

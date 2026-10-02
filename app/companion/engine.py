"""The companion engine: one turn = assemble context -> generate -> validate -> update.

Telegram-agnostic. The bot layer records incoming messages, asks the engine
for a TurnPlan, sends the bubbles with human timing, records each sent bubble
and then calls `apply()` so memory and relationship state are updated.

Per turn:
  1. recent messages (verbatim, token-budgeted)
  2. relevant long-term memories (+ always-on boundaries / pet names / near events)
  3. unresolved threads
  4. Sofia's mood and relationship state (with time-based decay)
  5. time since the previous interaction
  6. generate (strict JSON), recover from bad output, guard against assistant voice
  7. update memories, threads, Sofia's own facts and relationship state afterwards
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.companion import dynamics
from app.companion.persona import Persona, UserProfile
from app.companion.prompts import (
    FINAL_REMINDER,
    OPENER_TASK,
    PROACTIVE_TASK,
    PromptContext,
    RetrievedContext,
    build_instructions,
    render_current,
    render_dynamic_context,
    render_history,
    render_user_content,
)
from app.companion.schemas import PROACTIVE_SCHEMA, TURN_SCHEMA, ParseError, TurnOutput, parse_turn_output
from app.companion.state import Mood, RelationshipState, apply_nudges, apply_time_decay
from app.companion.style import bram_uses_action_format, finalize_bubbles, find_assistant_phrases, style_notes
from app.config import Settings
from app.llm.provider import ChatMessage, ImagePart, LLMError, LLMProvider, LLMResult
from app.memory.episodes import EpisodeSummarizer
from app.memory.extraction import Consolidator, MemoryWriter
from app.memory.models import Message
from app.memory.retrieval import Retriever
from app.memory.store import MemoryStore
from app.memory.text import estimate_tokens, jaccard, token_keys, truncate
from app.utils.logging import get_logger
from app.utils.timeutil import humanize_delta, parse_date, utcnow

log = get_logger(__name__)

GLITCH_MESSAGES = [
    "wait, something glitched on my side 🙃 try that again?",
    "hm, that didn't come through properly on my end. say it again?",
    "ugh, my phone just ate that. one more time?",
]
REFUSAL_NOTICE = (
    "⚙️ The model provider declined to generate a reply to that message, so Sofia never saw it. "
    "Rephrase it or carry on — nothing was stored as her reply."
)
CACHE_KEY = "sofia-companion-v1"
MAX_OPEN_THREADS = 12


@dataclass
class IncomingMessage:
    telegram_message_id: int | None
    text: str
    kind: str = "text"  # text | photo | voice | sticker | other
    images: list[ImagePart] = field(default_factory=list)
    reply_to: dict[str, Any] | None = None  # {"who", "text", "telegram_message_id", "quote"}
    forwarded_from: str | None = None
    sent_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnPlan:
    chat_id: int
    kind: str  # reply | proactive | opener | fallback | refusal
    bubbles: list[str]
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    reaction: str | None = None
    react_to_telegram_id: int | None = None
    output: TurnOutput | None = None
    state: RelationshipState | None = None
    batch_ids: list[int] = field(default_factory=list)
    source_message_id: int | None = None
    incoming_text: str = ""
    llm_elapsed: float = 0.0
    weighty: bool = False
    bram_hit_ids: list[str] = field(default_factory=list)
    retrieved_memory_ids: set[int] = field(default_factory=set)
    ooc: bool = False

    @property
    def stores_as_dialogue(self) -> bool:
        return self.kind in {"reply", "proactive", "opener"}


class CompanionEngine:
    def __init__(
        self,
        settings: Settings,
        store: MemoryStore,
        provider: LLMProvider,
        persona: Persona,
        profile: UserProfile,
        *,
        clock: Callable[[], datetime] = utcnow,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.provider = provider
        self.persona = persona
        self.profile = profile
        self.clock = clock
        self.rng = rng or random.Random()
        self.tz = settings.tz
        self.instructions = build_instructions(persona, profile)
        self.dynamic_specs = profile.dynamics
        self.retriever = Retriever(store, today=lambda now: now.astimezone(self.tz).date())
        self.writer = MemoryWriter(store, provider, clock)
        utility = settings.effective_utility_model
        self.summarizer = EpisodeSummarizer(
            store, provider, self.writer, self.tz, utility, keep_verbatim=max(10, settings.recent_messages_max // 2)
        )
        self.consolidator = Consolidator(store, provider, self.writer, utility)
        self._maintenance_lock = asyncio.Lock()

    # ------------------------------------------------------------------ state
    async def load_state(self) -> RelationshipState:
        data = await self.store.load_state()
        if data is None:
            state = RelationshipState.initial(self.persona.initial_state)
            state.last_decay_at = self.clock()
            return state
        return RelationshipState.from_dict(data)

    # ------------------------------------------------------------------ recording
    async def record_incoming(self, chat_id: int, incoming: IncomingMessage) -> int | None:
        meta = dict(incoming.meta)
        reply_tg_id = None
        if incoming.reply_to:
            reply = dict(incoming.reply_to)
            reply_tg_id = reply.get("telegram_message_id")
            if reply_tg_id is not None:
                stored = await self.store.get_message_by_telegram_id(chat_id, reply_tg_id)
                if stored is not None:
                    reply["who"] = "sofia" if stored.role == "assistant" else "bram"
                    if not reply.get("text"):
                        reply["text"] = stored.content if stored.role == "assistant" else render_user_content(stored)
            if reply.get("text"):
                meta["reply_to"] = {k: reply.get(k) for k in ("who", "text", "quote") if reply.get(k)}
        if incoming.forwarded_from:
            meta["forwarded_from"] = incoming.forwarded_from
        if incoming.images:
            meta["had_image"] = True
        elif incoming.kind == "photo":
            meta["image_unavailable"] = True
        return await self.store.add_message(
            chat_id=chat_id,
            role="user",
            content=incoming.text,
            kind=incoming.kind,
            telegram_message_id=incoming.telegram_message_id,
            reply_to_telegram_message_id=reply_tg_id,
            meta=meta,
            created_at=incoming.sent_at or self.clock(),
        )

    async def record_user_reaction(self, chat_id: int, target_telegram_id: int, emoji: str) -> None:
        target = await self.store.get_message_by_telegram_id(chat_id, target_telegram_id)
        if target is None or target.role != "assistant":
            return
        await self.store.add_message(
            chat_id=chat_id,
            role="user",
            kind="reaction",
            content=f"[he reacted {emoji} to her message “{truncate(target.content, 120)}”]",
        )

    async def record_outgoing(self, plan: TurnPlan, text: str, telegram_message_id: int | None) -> None:
        await self.store.add_message(
            chat_id=plan.chat_id,
            role="assistant",
            content=text,
            kind="proactive" if plan.kind == "proactive" else "text",
            telegram_message_id=telegram_message_id,
            turn_id=plan.turn_id,
            excluded=not plan.stores_as_dialogue,
            meta={"plan": plan.kind},
        )

    async def record_sofia_reaction(self, plan: TurnPlan, emoji: str) -> None:
        await self.store.add_message(
            chat_id=plan.chat_id,
            role="assistant",
            kind="reaction",
            content=f"reacted {emoji} to his message",
            turn_id=plan.turn_id,
        )

    # ------------------------------------------------------------------ planning
    async def plan_reply(self, chat_id: int, batch_ids: list[int], images: dict[int, list[ImagePart]]) -> TurnPlan:
        batch = await self.store.get_messages(batch_ids)
        if not batch:
            return self._fallback(chat_id, batch_ids, "")
        return await self._plan(chat_id, mode="reply", batch=batch, images=images)

    async def plan_opener(self, chat_id: int) -> TurnPlan:
        return await self._plan(chat_id, mode="opener", batch=[], images={}, task=OPENER_TASK)

    async def plan_proactive(self, chat_id: int, hooks: list[str]) -> TurnPlan | None:
        last = await self.store.last_message(chat_id)
        gap = humanize_delta(self.clock() - last.created_at) if last else "a while"
        last_role = "her own last message" if last and last.role == "assistant" else "his last message"
        task = PROACTIVE_TASK.format(
            gap=gap, last_role=last_role, hooks="\n".join(f"- {h}" for h in hooks) or "- (nothing specific)"
        )
        plan = await self._plan(chat_id, mode="proactive", batch=[], images={}, task=task)
        if plan.kind != "proactive" or not plan.bubbles or (plan.output is not None and not plan.output.send):
            return None
        return plan

    def _fallback(self, chat_id: int, batch_ids: list[int], incoming_text: str) -> TurnPlan:
        return TurnPlan(
            chat_id=chat_id,
            kind="fallback",
            bubbles=[self.rng.choice(GLITCH_MESSAGES)],
            batch_ids=batch_ids,
            incoming_text=incoming_text,
        )

    def _history_window(self, messages: list[Message]) -> list[Message]:
        """Keep the newest messages that fit in the token budget."""
        budget = self.settings.recent_tokens_budget
        kept: list[Message] = []
        used = 0
        for msg in reversed(messages):
            cost = estimate_tokens(msg.content) + 6
            if kept and used + cost > budget:
                break
            kept.append(msg)
            used += cost
        return list(reversed(kept))

    async def _plan(
        self,
        chat_id: int,
        *,
        mode: str,
        batch: list[Message],
        images: dict[int, list[ImagePart]],
        task: str | None = None,
    ) -> TurnPlan:
        now = self.clock()
        state = await self.load_state()
        apply_time_decay(state, now)

        incoming_text = "\n".join(render_user_content(m) for m in batch)
        bram_hits = dynamics.observe_bram(state, self.dynamic_specs, incoming_text, now) if batch else []

        before_id = batch[0].id if batch else None
        history = self._history_window(
            await self.store.recent_messages(chat_id, self.settings.recent_messages_max, before_id=before_id)
        )
        dialogue = [m for m in history if m.kind != "reaction"]
        previous_any = dialogue[-1] if dialogue else None
        previous_user = next((m for m in reversed(dialogue) if m.role == "user"), None)

        query_parts = [incoming_text] + [m.content for m in dialogue[-3:]]
        query = truncate("\n".join(p for p in query_parts if p), 2000)
        query_embedding = None
        if self.provider.can_embed and query:
            try:
                vectors = await self.provider.embed([query])
                query_embedding = vectors[0] if vectors else None
            except Exception:
                log.warning("query embedding failed", exc_info=True)
        retrieved: RetrievedContext = await self.retriever.retrieve(query, now, query_embedding)

        user_texts = [m.content for m in [*history, *batch] if m.role == "user"]
        ctx = PromptContext(
            now=now,
            tz=self.tz,
            state=state,
            retrieved=retrieved,
            previous_user_at=previous_user.created_at if previous_user else None,
            previous_any_at=previous_any.created_at if previous_any else None,
            previous_any_role=previous_any.role if previous_any else None,
            activity=self.persona.current_activity(now.astimezone(self.tz)),
            dynamics_lines=dynamics.render(state, self.dynamic_specs, now),
            style_notes=style_notes(await self.store.recent_assistant_turns(chat_id, 6)),
            allow_actions=bram_uses_action_format(user_texts),
        )

        messages: list[ChatMessage] = [ChatMessage("developer", render_dynamic_context(ctx))]
        messages += render_history(history, self.tz)
        if batch:
            prev_at = previous_any.created_at if previous_any else None
            messages += render_current(batch, images, self.tz, prev_at)
        if task:
            messages.append(ChatMessage("developer", task))
        messages.append(ChatMessage("developer", FINAL_REMINDER))

        schema, schema_name = (
            (PROACTIVE_SCHEMA, "sofia_proactive") if mode == "proactive" else (TURN_SCHEMA, "sofia_turn")
        )
        batch_ids = [m.id for m in batch]
        retrieved_ids = {m.id for m in [*retrieved.bram, *retrieved.relationship, *retrieved.sofia]}

        try:
            output, result = await self._generate_validated(messages, schema, schema_name, require_text=mode != "reply")
        except _RefusalError:
            log.warning("provider refusal", extra={"mode": mode})
            if batch_ids:
                await self.store.mark_excluded(batch_ids)
            return TurnPlan(chat_id=chat_id, kind="refusal", bubbles=[REFUSAL_NOTICE], batch_ids=batch_ids, ooc=True)
        except (LLMError, ParseError, _EmptyReplyError) as exc:
            log.error("generation failed, sending neutral fallback: %s", exc, exc_info=isinstance(exc, LLMError))
            return self._fallback(chat_id, batch_ids, incoming_text)

        allow_actions = ctx.allow_actions
        bubbles = finalize_bubbles(output.messages, allow_actions=allow_actions)
        weighty = len(incoming_text) > 300 or sum(len(b) for b in bubbles) > 450 or state.mood.intensity > 0.75
        return TurnPlan(
            chat_id=chat_id,
            kind=mode,
            bubbles=bubbles,
            reaction=output.reaction if mode == "reply" else None,
            react_to_telegram_id=batch[-1].telegram_message_id if batch else None,
            output=output,
            state=state,
            batch_ids=batch_ids,
            source_message_id=batch[-1].id if batch else None,
            incoming_text=incoming_text,
            llm_elapsed=result.elapsed,
            weighty=weighty,
            bram_hit_ids=bram_hits,
            retrieved_memory_ids=retrieved_ids,
        )

    async def _call(self, messages: list[ChatMessage], schema: dict, schema_name: str) -> LLMResult:
        return await self.provider.generate_json(
            instructions=self.instructions,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
            cache_key=CACHE_KEY,
        )

    async def _generate_validated(
        self, messages: list[ChatMessage], schema: dict, schema_name: str, *, require_text: bool
    ) -> tuple[TurnOutput, LLMResult]:
        """Generate, parse, and retry once on unusable or assistant-sounding output."""
        result = await self._call(messages, schema, schema_name)
        elapsed = result.elapsed
        if result.refusal and not result.text.strip():
            raise _RefusalError(result.refusal)

        corrective: str | None = None
        output: TurnOutput | None = None
        try:
            output = parse_turn_output(result.text)
        except ParseError as exc:
            corrective = (
                f"Your previous output could not be used ({exc}). Return exactly one JSON object matching the schema."
            )

        if output is not None:
            bubbles = finalize_bubbles(output.messages)
            if not bubbles and not (output.reaction and not require_text) and output.send:
                corrective = "Your previous output had no usable messages. Write Sofia's reply in 'messages'."
            elif self.settings.style_guard_regenerate and (found := find_assistant_phrases(bubbles)):
                corrective = (
                    "Your draft slipped into assistant voice (" + ", ".join(f'"{f}"' for f in found[:3]) + "). "
                    "Rewrite it as Sofia: a person texting someone she knows, not a service. Same intent, her voice."
                )

        if corrective is None and output is not None:
            return output, result

        log.info("regenerating once", extra={"reason": corrective[:80] if corrective else ""})
        retry = await self._call([*messages, ChatMessage("developer", corrective or "")], schema, schema_name)
        elapsed += retry.elapsed
        if retry.refusal and not retry.text.strip():
            raise _RefusalError(retry.refusal)
        try:
            retried = parse_turn_output(retry.text)
        except ParseError:
            if output is not None and finalize_bubbles(output.messages):
                retry.elapsed = elapsed
                return output, retry  # first draft was usable, just not ideal
            raise
        if not finalize_bubbles(retried.messages) and not retried.reaction and retried.send:
            if output is not None and finalize_bubbles(output.messages):
                return output, retry
            raise _EmptyReplyError("empty reply after retry")
        retry.elapsed = elapsed
        return retried, retry

    # ------------------------------------------------------------------ applying
    async def apply(self, plan: TurnPlan) -> None:
        """Persist the consequences of a turn that was actually sent."""
        if plan.output is None or plan.state is None or not plan.stores_as_dialogue:
            return
        out = plan.output
        state = plan.state
        now = self.clock()
        local_date = now.astimezone(self.tz).date().isoformat()

        cause = (out.mood_update.cause if out.mood_update else "") or state.irritation_cause or "something he said"
        apply_nudges(state, out.relationship_update.as_dict(), local_date, cause=cause)
        if out.mood_update and out.mood_update.label:
            state.mood = Mood(out.mood_update.label, out.mood_update.intensity, out.mood_update.cause, now)
        if out.dynamic_note and out.dynamic_note.strip():
            state.dynamic_summary = out.dynamic_note.strip()[:300]
        dynamics.establish(state, self.dynamic_specs, out.established_dynamics, now)
        dynamics.observe_sofia(state, self.dynamic_specs, plan.bubbles, now, plan.bram_hit_ids)
        await self.store.save_state(state.to_dict())

        await self.writer.ingest_candidates(out.memory_candidates, plan.source_message_id)
        await self.writer.ingest_sofia_facts(out.sofia_facts, plan.source_message_id)
        await self._apply_threads(out, plan.source_message_id)

        if out.image_note and plan.batch_ids:
            photos = [m for m in await self.store.get_messages(plan.batch_ids) if m.kind == "photo"]
            if photos:
                await self.store.update_message_meta(photos[-1].id, {"image_note": truncate(out.image_note, 200)})

        used = [i for i in out.used_memory_ids if i in plan.retrieved_memory_ids]
        await self.store.touch_memories(used)

    async def _apply_threads(self, out: TurnOutput, source_message_id: int | None) -> None:
        open_threads = await self.store.list_threads("open")
        open_ids = {t.id for t in open_threads}
        for update in out.unresolved_threads:
            if update.action == "resolve":
                if update.id is not None and update.id in open_ids:
                    await self.store.set_thread_status(update.id, "resolved")
                continue
            content = " ".join(update.content.split())
            if len(content) < 10:
                continue
            keys = token_keys(content)
            if any(jaccard(keys, token_keys(t.content)) >= 0.6 for t in open_threads):
                continue
            await self.store.open_thread(
                content[:300], due_date=parse_date(update.due_date), source_message_id=source_message_id
            )
        remaining = await self.store.list_threads("open")
        for stale in remaining[: max(0, len(remaining) - MAX_OPEN_THREADS)]:
            await self.store.set_thread_status(stale.id, "stale")

    # ------------------------------------------------------------------ maintenance
    async def maintenance(self, chat_id: int, *, idle: bool = False) -> None:
        """Background upkeep after a turn (or periodically when idle)."""
        if self._maintenance_lock.locked():
            return
        async with self._maintenance_lock:
            try:
                if idle:
                    await self.summarizer.maybe_run(chat_id, min_messages=8)
                else:
                    await self.summarizer.maybe_run(chat_id)
                await self.consolidator.maybe_run()
                await self.store.purge_expired_memories()
                await self.store.stale_old_threads(timedelta(days=21))
            except Exception:
                log.exception("maintenance failed")


class _RefusalError(Exception):
    pass


class _EmptyReplyError(Exception):
    pass

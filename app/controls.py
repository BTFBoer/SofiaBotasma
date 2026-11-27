"""Out-of-character controls behind the slash commands.

Kept free of Telegram types so the logic (confirmation flows, memory search,
export) is easy to test. These are never treated as dialogue: nothing here
reaches the model and nothing here is stored as conversation.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.config import Settings
from app.llm.provider import LLMProvider
from app.memory.models import Episode, Memory
from app.memory.store import MemoryStore
from app.memory.text import containment, cosine, token_keys, truncate
from app.utils.timeutil import format_short_date, utcnow

CONFIRMATION_TTL = timedelta(minutes=5)
PROACTIVE_KEY = "proactive_enabled"

ABOUT_TEXT = (
    "Sofia is a private fictional AI character running through this Telegram bot. Her personality, memories "
    "and relationship continuity are simulated by the companion system, using a large language model.\n\n"
    "She isn't a real person, can't meet you, and doesn't see anything you don't send her. Ask her directly "
    "and she'll tell you the same."
)


@dataclass
class PendingAction:
    action: str  # "reset" | "forget"
    payload: dict[str, Any]
    expires_at: datetime


@dataclass
class ForgetMatch:
    kind: str  # "memory" | "episode"
    id: int
    text: str


@dataclass
class ControlService:
    settings: Settings
    store: MemoryStore
    provider: LLMProvider | None = None
    clock: Callable[[], datetime] = utcnow
    _pending: dict[str, PendingAction] = field(default_factory=dict)

    # ------------------------------------------------------------------ confirmations
    def _new_token(self, action: str, payload: dict[str, Any]) -> str:
        self._purge()
        token = secrets.token_hex(6)
        self._pending[token] = PendingAction(action, payload, self.clock() + CONFIRMATION_TTL)
        return token

    def _purge(self) -> None:
        now = self.clock()
        for token in [t for t, p in self._pending.items() if p.expires_at <= now]:
            del self._pending[token]

    def _take(self, token: str, action: str) -> PendingAction | None:
        self._purge()
        pending = self._pending.get(token)
        if pending is None or pending.action != action:
            return None
        del self._pending[token]
        return pending

    def cancel(self, token: str) -> bool:
        return self._pending.pop(token, None) is not None

    # ------------------------------------------------------------------ reset
    def request_reset(self) -> str:
        return self._new_token("reset", {})

    async def confirm_reset(self, token: str) -> bool:
        if self._take(token, "reset") is None:
            return False
        await self.store.reset_all()
        return True

    # ------------------------------------------------------------------ forget
    async def find_forget_matches(self, query: str, limit: int = 8) -> list[ForgetMatch]:
        query = query.strip()
        if not query:
            return []
        keys = token_keys(query)
        lowered = query.lower()
        q_emb = None
        if self.provider is not None and self.provider.can_embed:
            try:
                vectors = await self.provider.embed([query])
                q_emb = vectors[0] if vectors else None
            except Exception:
                q_emb = None

        def score(text: str, emb: list[float] | None) -> float:
            s = containment(keys, token_keys(text))
            if lowered in text.lower():
                s = max(s, 1.0)
            if q_emb is not None and emb is not None:
                s = max(s, (cosine(q_emb, emb) - 0.3) / 0.35)
            return s

        scored: list[tuple[float, ForgetMatch]] = []
        memories: list[Memory] = await self.store.list_memories(active_only=False)
        for mem in memories:
            s = score(mem.content, mem.embedding)
            if s >= 0.5:
                scored.append((s, ForgetMatch("memory", mem.id, mem.content)))
        episodes: list[Episode] = await self.store.list_episodes()
        for ep in episodes:
            s = score(f"{ep.title} {ep.summary}", ep.embedding)
            if s >= 0.5:
                scored.append((s, ForgetMatch("episode", ep.id, f"{ep.title} — {ep.summary}")))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def request_forget(self, matches: list[ForgetMatch]) -> str:
        return self._new_token("forget", {"matches": [(m.kind, m.id) for m in matches]})

    async def confirm_forget(self, token: str, index: int | None) -> int:
        """Delete one match (by index) or all (index None). Returns number deleted, -1 if token invalid."""
        pending = self._take(token, "forget")
        if pending is None:
            return -1
        matches: list[tuple[str, int]] = [tuple(m) for m in pending.payload["matches"]]  # type: ignore[misc]
        if index is not None:
            if not 0 <= index < len(matches):
                return 0
            matches = [matches[index]]
        memory_ids = [i for kind, i in matches if kind == "memory"]
        episode_ids = [i for kind, i in matches if kind == "episode"]
        deleted = await self.store.delete_memories(memory_ids)
        deleted += await self.store.delete_episodes(episode_ids)
        return deleted

    # ------------------------------------------------------------------ memory summary
    async def memory_summary(self) -> str:
        bram = sorted(await self.store.list_memories("bram"), key=lambda m: m.importance, reverse=True)
        rel = sorted(await self.store.list_memories("relationship"), key=lambda m: m.importance, reverse=True)
        sofia = await self.store.list_memories("sofia")
        episodes = await self.store.list_episodes()
        threads = await self.store.list_threads("open")
        total_messages = await self.store.count_messages()

        if not (bram or rel or sofia or episodes or threads):
            return (
                "🗂 Memory\n\nNothing stored yet beyond the raw chat log "
                f"({total_messages} messages). Memories form as you talk."
            )

        lines = ["🗂 What Sofia currently remembers", ""]
        if bram:
            lines.append(f"About you ({len(bram)}):")
            for m in bram[:25]:
                date = f" [{m.event_date.isoformat()}]" if m.event_date else ""
                lines.append(f"• {truncate(m.content, 160)}{date}")
            if len(bram) > 25:
                lines.append(f"  …and {len(bram) - 25} more (see /export)")
            lines.append("")
        if rel:
            lines.append(f"Between you two ({len(rel)}):")
            lines.extend(f"• {truncate(m.content, 160)}" for m in rel[:15])
            lines.append("")
        if episodes:
            lines.append(f"Moments ({len(episodes)}), most recent:")
            for ep in episodes[-6:]:
                lines.append(f"• {format_short_date(ep.ended_at)} — {truncate(ep.title, 80)}")
            lines.append("")
        if threads:
            lines.append("Open threads:")
            lines.extend(f"• {truncate(t.content, 140)}" for t in threads[:10])
            lines.append("")
        lines.append(f"Things Sofia has established about herself: {len(sofia)}")
        lines.append(f"Raw chat log: {total_messages} messages.")
        lines.append("")
        lines.append("Use /forget <words> to remove something, /export for everything.")
        return "\n".join(lines)

    # ------------------------------------------------------------------ export
    async def export_json(self) -> bytes:
        data = await self.store.export_all()
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    # ------------------------------------------------------------------ proactive
    async def proactive_enabled(self) -> bool:
        value = await self.store.get_setting(PROACTIVE_KEY)
        if value is None:
            return self.settings.proactive_default
        return value == "1"

    async def set_proactive(self, enabled: bool) -> None:
        await self.store.set_setting(PROACTIVE_KEY, "1" if enabled else "0")

    # ------------------------------------------------------------------ privacy / about
    def privacy_text(self) -> str:
        s = self.settings
        provider = (
            "OpenAI (Responses API)"
            if s.llm_provider == "openai"
            else f"an OpenAI-compatible API ({s.llm_base_url or 'default URL'})"
        )
        features = []
        if s.embedding_model:
            features.append("memory and message snippets are sent for embeddings (to find relevant memories)")
        if s.transcription_model:
            features.append("voice messages are sent for transcription")
        if s.vision_enabled:
            features.append("photos you send are sent to the model so Sofia can see them")
        feature_text = "; ".join(features) if features else "no extra features enabled"
        image_storage = (
            f"Photos are kept in {s.image_dir} (KEEP_IMAGES=true)."
            if s.keep_images
            else "Photos and voice messages are processed in memory and not saved; only a short text note may be kept."
        )
        return (
            "🔒 Privacy\n\n"
            "Stored locally (SQLite):\n"
            f"• {s.database_path} — your chat log, learned memories, episode summaries, open threads, "
            "Sofia's mood/relationship state and settings. Nothing is stored anywhere else by this app.\n"
            f"• {image_storage}\n"
            "• Logs contain metadata (timings, token counts), not message contents, unless LOG_LEVEL=DEBUG.\n\n"
            f"Sent to the LLM provider — {provider} — on every reply:\n"
            "• Sofia's persona and behaviour instructions, your profile files\n"
            "• a selection of relevant memories, recent episode summaries, open threads, her current state\n"
            "• the recent chat verbatim and your current message\n"
            f"• {feature_text}.\n"
            "Requests are sent with store=false (no server-side conversation state). The provider's own data "
            "retention and usage policy still applies — check it.\n\n"
            "Telegram: bot chats are cloud chats, not end-to-end encrypted. Telegram's servers see these messages.\n\n"
            "Your controls: /memory (see), /forget <words> (delete), /export (download everything), "
            "/reset (erase everything)."
        )

    @staticmethod
    def about_text() -> str:
        return ABOUT_TEXT

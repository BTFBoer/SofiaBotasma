"""Episodic memory: folding older conversation into summaries.

The newest messages stay verbatim in context. Once enough older, not yet
summarized messages pile up behind that window, they're summarized into 1-3
episodes, durable facts are extracted, settled threads are closed, and the
messages are marked summarized (they remain in the database for /export).
Important facts are never lost just because they're old: they live on as
memories and episodes.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from app.companion.prompts import SUMMARY_INSTRUCTIONS, render_summary_input
from app.companion.schemas import SUMMARY_SCHEMA, ParseError, SummaryOutput, parse_model
from app.llm.provider import ChatMessage, LLMError, LLMProvider
from app.memory.extraction import MemoryWriter
from app.memory.store import MemoryStore
from app.utils.logging import get_logger

log = get_logger(__name__)


class EpisodeSummarizer:
    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        writer: MemoryWriter,
        tz: ZoneInfo,
        model: str | None,
        *,
        keep_verbatim: int = 20,
        threshold: int = 24,
        chunk_size: int = 40,
    ) -> None:
        self.store = store
        self.provider = provider
        self.writer = writer
        self.tz = tz
        self.model = model
        self.keep_verbatim = keep_verbatim
        self.threshold = threshold
        self.chunk_size = chunk_size

    async def _boundary_id(self, chat_id: int) -> int | None:
        recent = await self.store.recent_messages(chat_id, self.keep_verbatim)
        if len(recent) < self.keep_verbatim:
            return None
        return recent[0].id

    async def maybe_run(self, chat_id: int, *, min_messages: int | None = None) -> bool:
        boundary = await self._boundary_id(chat_id)
        if boundary is None:
            return False
        needed = self.threshold if min_messages is None else min_messages
        pending = await self.store.count_unsummarized_before(chat_id, boundary)
        if pending < max(1, needed):
            return False
        chunk = await self.store.unsummarized_before(chat_id, boundary, self.chunk_size)
        return await self.summarize(chunk)

    async def summarize(self, chunk: list) -> bool:
        if not chunk:
            return False
        threads = await self.store.list_threads("open")
        try:
            result = await self.provider.generate_json(
                instructions=SUMMARY_INSTRUCTIONS,
                messages=[ChatMessage("user", render_summary_input(chunk, threads, self.tz))],
                schema=SUMMARY_SCHEMA,
                schema_name="episode_summary",
                model=self.model,
                max_output_tokens=4000,
            )
            output: SummaryOutput = parse_model(result.text, SummaryOutput)
        except (LLMError, ParseError) as exc:
            log.warning("episode summarization failed (will retry later): %s", exc)
            return False

        episodes = [e for e in output.episodes if e.title.strip() and e.summary.strip()][:3]
        embeddings = await self.writer._embed([f"{e.title}. {e.summary}" for e in episodes])
        for episode, emb in zip(episodes, embeddings, strict=True):
            await self.store.add_episode(
                title=episode.title.strip()[:120],
                summary=episode.summary.strip()[:1200],
                tone=episode.tone.strip()[:80],
                importance=episode.importance,
                tags=[t.strip().lower() for t in episode.tags if t.strip()][:8],
                started_at=chunk[0].created_at,
                ended_at=chunk[-1].created_at,
                embedding=emb,
            )
        source = chunk[-1].id
        await self.writer.ingest_candidates(output.memory_candidates, source)
        await self.writer.ingest_sofia_facts(output.sofia_facts, source)
        open_ids = {t.id for t in threads}
        for thread_id in output.resolved_thread_ids:
            if thread_id in open_ids:
                await self.store.set_thread_status(thread_id, "resolved")
        await self.store.mark_summarized([m.id for m in chunk])
        log.info("episode summary stored", extra={"messages": len(chunk), "episodes": len(episodes)})
        return True

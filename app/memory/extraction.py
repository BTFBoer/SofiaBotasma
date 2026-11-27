"""Turning model suggestions into durable memories — selectively.

The model proposes memory candidates every turn; this module decides what is
actually kept: it filters trivia and speculation, normalizes categories,
de-duplicates against what is already stored (newer wins for Bram, older wins
for Sofia, to keep her consistent), and periodically consolidates the store.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta

from app.companion.prompts import CONSOLIDATION_INSTRUCTIONS, render_consolidation_input
from app.companion.schemas import (
    CONSOLIDATION_SCHEMA,
    ConsolidationOutput,
    MemoryCandidate,
    ParseError,
    SofiaFact,
    parse_model,
)
from app.llm.provider import ChatMessage, LLMError, LLMProvider
from app.memory.models import BRAM_CATEGORIES, RELATIONSHIP_CATEGORIES, SOFIA_CATEGORIES, NewMemory
from app.memory.store import MemoryStore
from app.memory.text import cosine, jaccard, normalize, token_keys
from app.utils.logging import get_logger
from app.utils.timeutil import parse_date

log = get_logger(__name__)

MIN_IMPORTANCE = 0.3
MIN_CONFIDENCE = 0.55
DUPLICATE_JACCARD = 0.72
DUPLICATE_COSINE = 0.90
SOFIA_DAY_FACT_TTL = timedelta(days=5)

_TRIVIAL_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(said|says|typed|wrote|sent)\s+(lol|haha+|ok(ay)?|hi|hey|hello|yes|no|morning|night|goodnight)\b",
        r"\bis (currently |now )?(drinking|having) (a )?(water|coffee|tea)\b",
        r"\b(said|says) (good ?morning|good ?night|hi|hello|hey)\b",
        r"\bsent (an? )?(emoji|sticker)\b",
        r"\bis (currently )?(typing|online|texting)\b",
    )
]

_CATEGORY_ALIASES = {
    "plans": "plan",
    "people": "person",
    "relationship_person": "person",
    "family": "person",
    "friend": "person",
    "likes": "preference",
    "like": "preference",
    "dislikes": "dislike",
    "hates": "dislike",
    "joke": "inside_joke",
    "jokes": "inside_joke",
    "running_joke": "inside_joke",
    "nickname": "pet_name",
    "petname": "pet_name",
    "pet name": "pet_name",
    "events": "event",
    "emotion": "emotional",
    "feelings": "emotional",
    "job": "work",
    "career": "work",
    "boundaries": "boundary",
    "limit": "boundary",
    "music": "interest",
    "hobby": "interest",
    "sexual": "intimacy",
    "sex": "intimacy",
    "fetish": "intimacy",
    "kink": "intimacy",
    "theme": "shared_theme",
    "daily": "today",
    "day": "today",
    "life": "biography",
    "past": "biography",
}


def normalize_category(category: str, subject: str) -> str:
    cat = normalize(category).replace(" ", "_") or "other"
    cat = _CATEGORY_ALIASES.get(cat, _CATEGORY_ALIASES.get(category.lower().strip(), cat))
    allowed = {"bram": BRAM_CATEGORIES, "relationship": RELATIONSHIP_CATEGORIES, "sofia": SOFIA_CATEGORIES}[subject]
    return cat if cat in allowed else "other"


def is_trivial(content: str) -> bool:
    text = content.strip()
    if len(text) < 12 or len(text.split()) < 3:
        return True
    return any(p.search(text) for p in _TRIVIAL_PATTERNS)


class MemoryWriter:
    def __init__(self, store: MemoryStore, provider: LLMProvider | None, clock: Callable[[], datetime]) -> None:
        self.store = store
        self.provider = provider
        self.clock = clock

    async def _embed(self, texts: list[str]) -> list[list[float] | None]:
        if not texts or self.provider is None or not self.provider.can_embed:
            return [None] * len(texts)
        try:
            vectors = await self.provider.embed(texts)
        except Exception:  # embeddings are an optimisation, never a failure
            log.warning("embedding batch failed", exc_info=True)
            vectors = None
        if not vectors or len(vectors) != len(texts):
            return [None] * len(texts)
        return list(vectors)

    async def ingest_candidates(self, candidates: list[MemoryCandidate], source_message_id: int | None) -> list[int]:
        accepted: list[NewMemory] = []
        for cand in candidates:
            content = " ".join(cand.content.split())
            if not content or is_trivial(content):
                continue
            if cand.importance < MIN_IMPORTANCE or cand.confidence < MIN_CONFIDENCE:
                continue
            accepted.append(
                NewMemory(
                    subject=cand.subject,
                    category=normalize_category(cand.category, cand.subject),
                    content=content[:500],
                    importance=cand.importance,
                    confidence=cand.confidence,
                    source_message_id=source_message_id,
                    event_date=parse_date(cand.event_date),
                )
            )
        return await self._write_all(accepted)

    async def ingest_sofia_facts(self, facts: list[SofiaFact], source_message_id: int | None) -> list[int]:
        now = self.clock()
        accepted: list[NewMemory] = []
        for fact in facts:
            content = " ".join(fact.content.split())
            if len(content) < 8:
                continue
            accepted.append(
                NewMemory(
                    subject="sofia",
                    category="today" if not fact.durable else normalize_category(fact.category, "sofia"),
                    content=content[:400],
                    importance=0.6 if fact.durable else 0.35,
                    confidence=0.95,
                    source_message_id=source_message_id,
                    expires_at=None if fact.durable else now + SOFIA_DAY_FACT_TTL,
                )
            )
        return await self._write_all(accepted)

    async def _write_all(self, items: list[NewMemory]) -> list[int]:
        if not items:
            return []
        embeddings = await self._embed([m.content for m in items])
        ids: list[int] = []
        for item, emb in zip(items, embeddings, strict=True):
            item.embedding = emb
            memory_id = await self._write_one(item)
            if memory_id is not None:
                ids.append(memory_id)
        return ids

    async def _write_one(self, new: NewMemory) -> int | None:
        existing = await self.store.list_memories(new.subject)
        norm = normalize(new.content)
        keys = token_keys(new.content)
        for mem in existing:
            if mem.normalized == norm:
                await self.store.update_memory(
                    mem.id,
                    importance=max(mem.importance, new.importance),
                    confidence=max(mem.confidence, new.confidence),
                    event_date=new.event_date,
                )
                return mem.id
            similar = jaccard(keys, token_keys(mem.content)) >= DUPLICATE_JACCARD
            if not similar and new.embedding is not None and mem.embedding is not None:
                similar = cosine(new.embedding, mem.embedding) >= DUPLICATE_COSINE
            if not similar:
                continue
            if new.subject == "sofia":
                # Consistency: what she said first stays true.
                return mem.id
            # About Bram / the relationship: the newer phrasing carries the newer information.
            await self.store.update_memory(
                mem.id,
                content=new.content,
                importance=max(mem.importance, new.importance),
                confidence=max(mem.confidence, new.confidence),
                event_date=new.event_date,
                embedding=new.embedding,
                consolidated=False,
            )
            return mem.id
        return await self.store.add_memory(new)


class Consolidator:
    """Periodic LLM-assisted clean-up of duplicate and obsolete memories."""

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        writer: MemoryWriter,
        model: str | None,
        *,
        threshold: int = 20,
        max_batch: int = 150,
    ) -> None:
        self.store = store
        self.provider = provider
        self.writer = writer
        self.model = model
        self.threshold = threshold
        self.max_batch = max_batch

    async def maybe_run(self) -> None:
        for subject in ("bram", "relationship", "sofia"):
            if await self.store.count_unconsolidated(subject) >= self.threshold:
                await self.run(subject)

    async def run(self, subject: str) -> None:
        memories = await self.store.list_memories(subject)
        if len(memories) < 4:
            await self.store.mark_all_consolidated(subject)
            return
        batch = memories[-self.max_batch :]
        try:
            result = await self.provider.generate_json(
                instructions=CONSOLIDATION_INSTRUCTIONS,
                messages=[ChatMessage("user", render_consolidation_input(batch, subject))],
                schema=CONSOLIDATION_SCHEMA,
                schema_name="memory_consolidation",
                model=self.model,
                max_output_tokens=4000,
            )
            output: ConsolidationOutput = parse_model(result.text, ConsolidationOutput)
        except (LLMError, ParseError) as exc:
            log.warning("consolidation failed for %s: %s", subject, exc)
            return

        valid = {m.id: m for m in batch}
        touched: set[int] = set()
        for merge in output.merges:
            ids = [i for i in dict.fromkeys(merge.ids) if i in valid and i not in touched]
            content = " ".join(merge.content.split())
            if len(ids) < 2 or len(content) < 8:
                continue
            keeper = max(ids, key=lambda i: (valid[i].importance, valid[i].created_at))
            emb = (await self.writer._embed([content]))[0]
            await self.store.update_memory(
                keeper,
                content=content,
                importance=max(merge.importance, *(valid[i].importance for i in ids)),
                embedding=emb,
            )
            await self.store.deactivate_memories([i for i in ids if i != keeper])
            touched.update(ids)
        retire = [i for i in output.retire_ids if i in valid and i not in touched]
        await self.store.deactivate_memories(retire)
        await self.store.mark_all_consolidated(subject)
        log.info(
            "memories consolidated", extra={"subject": subject, "merges": len(output.merges), "retired": len(retire)}
        )

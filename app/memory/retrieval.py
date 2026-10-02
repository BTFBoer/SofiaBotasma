"""Selects the few memories worth putting in front of the model this turn.

Score = relevance to the current message (embeddings when available, lexical
overlap always) + importance + recency + confidence, with two overrides:
- events dated in the near past/future are always included (so a techno night
  three days out surfaces on its own), and
- boundaries and pet names are always included (they're never irrelevant).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from app.companion.prompts import RetrievedContext
from app.memory.models import Episode, Memory
from app.memory.store import MemoryStore
from app.memory.text import containment, cosine, token_keys

ALWAYS_RELATIONSHIP_CATEGORIES = {"pet_name", "boundary"}
ALWAYS_BRAM_CATEGORIES = {"boundary", "communication"}


@dataclass
class RetrievalLimits:
    bram: int = 10
    relationship: int = 6
    sofia: int = 8
    episodes_recent: int = 2
    episodes_relevant: int = 3
    threads: int = 8
    event_window_past_days: int = 2
    event_window_future_days: int = 10


def _relevance(query_keys: set[str], query_emb: list[float] | None, keys: set[str], emb: list[float] | None) -> float:
    lexical = containment(query_keys, keys)
    lexical = min(1.0, lexical * 1.4)
    semantic = 0.0
    if query_emb is not None and emb is not None:
        # text-embedding-3-* cosine for related short texts typically sits around 0.3–0.6.
        semantic = max(0.0, min(1.0, (cosine(query_emb, emb) - 0.22) / 0.4))
    return max(lexical, semantic)


def _recency(mem_time: datetime, now: datetime, half_life_days: float = 45.0) -> float:
    days = max(0.0, (now - mem_time).total_seconds() / 86400.0)
    return math.pow(0.5, days / half_life_days)


def _event_bonus(event_date: date | None, today: date, limits: RetrievalLimits) -> float:
    if event_date is None:
        return 0.0
    diff = (event_date - today).days
    if -limits.event_window_past_days <= diff <= limits.event_window_future_days:
        return 1.0 - min(1.0, abs(diff) / (limits.event_window_future_days + 1))
    return 0.0


def score_memory(
    mem: Memory,
    query_keys: set[str],
    query_emb: list[float] | None,
    now: datetime,
    today: date,
    limits: RetrievalLimits,
) -> tuple[float, float]:
    """Returns (score, relevance)."""
    relevance = _relevance(query_keys, query_emb, token_keys(mem.content), mem.embedding)
    recency = _recency(mem.last_referenced_at or mem.created_at, now)
    score = 0.55 * relevance + 0.25 * mem.importance + 0.10 * recency + 0.10 * mem.confidence
    score += 0.5 * _event_bonus(mem.event_date, today, limits)
    return score, relevance


class Retriever:
    def __init__(
        self,
        store: MemoryStore,
        *,
        today: Callable[[datetime], date],
        limits: RetrievalLimits | None = None,
    ) -> None:
        self.store = store
        self.today = today
        self.limits = limits or RetrievalLimits()

    async def retrieve(self, query: str, now: datetime, query_embedding: list[float] | None = None) -> RetrievedContext:
        limits = self.limits
        today = self.today(now)
        query_keys = token_keys(query)

        def select(memories: list[Memory], limit: int, always: set[str]) -> list[Memory]:
            scored = []
            forced: list[Memory] = []
            for mem in memories:
                score, relevance = score_memory(mem, query_keys, query_embedding, now, today, limits)
                if mem.category in always or _event_bonus(mem.event_date, today, limits) > 0.6:
                    forced.append(mem)
                    continue
                # Without any relevance, only genuinely important memories may surface.
                if relevance < 0.15 and mem.importance < 0.75:
                    continue
                scored.append((score, mem))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            forced.sort(key=lambda m: m.importance, reverse=True)
            chosen = forced[: max(2, limit // 2)]
            chosen_ids = {m.id for m in chosen}
            for _, mem in scored:
                if len(chosen) >= limit:
                    break
                if mem.id not in chosen_ids:
                    chosen.append(mem)
                    chosen_ids.add(mem.id)
            return chosen

        bram = select(await self.store.list_memories("bram"), limits.bram, ALWAYS_BRAM_CATEGORIES)
        relationship = select(
            await self.store.list_memories("relationship"), limits.relationship, ALWAYS_RELATIONSHIP_CATEGORIES
        )

        # Sofia's own facts: relevant ones + recent day-to-day ones (they expire anyway).
        sofia_all = await self.store.list_memories("sofia")
        recent_life = [m for m in sofia_all if m.expires_at is not None][-4:]
        durable = [m for m in sofia_all if m.expires_at is None]
        sofia_scored = sorted(
            durable,
            key=lambda m: score_memory(m, query_keys, query_embedding, now, today, limits)[0],
            reverse=True,
        )
        sofia = sofia_scored[: limits.sofia] + recent_life

        episodes = await self._episodes(query_keys, query_embedding, now)
        threads = (await self.store.list_threads("open"))[-limits.threads :]
        return RetrievedContext(bram=bram, relationship=relationship, sofia=sofia, episodes=episodes, threads=threads)

    async def _episodes(self, query_keys: set[str], query_emb: list[float] | None, now: datetime) -> list[Episode]:
        episodes = await self.store.list_episodes()
        if not episodes:
            return []
        recent = episodes[-self.limits.episodes_recent :]
        candidates = []
        for ep in episodes[: -self.limits.episodes_recent] if len(episodes) > self.limits.episodes_recent else []:
            relevance = _relevance(query_keys, query_emb, token_keys(ep.title + " " + ep.summary), ep.embedding)
            score = 0.6 * relevance + 0.3 * ep.importance + 0.1 * _recency(ep.ended_at, now, 60)
            if relevance >= 0.2 or ep.importance >= 0.85:
                candidates.append((score, ep))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        relevant = [ep for _, ep in candidates[: self.limits.episodes_relevant]]
        return sorted([*relevant, *recent], key=lambda ep: ep.ended_at)

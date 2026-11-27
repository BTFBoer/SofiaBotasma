"""Context retrieval picks relevant memories, near events and always-on items."""

from __future__ import annotations

from datetime import date, timedelta

from app.memory.models import NewMemory
from app.memory.retrieval import Retriever


def retriever(store, settings):
    return Retriever(store, today=lambda now: now.astimezone(settings.tz).date())


async def seed(store):
    ids = {}
    ids["mulero"] = await store.add_memory(
        NewMemory("bram", "interest", "Bram loves Óscar Mulero's hypnotic sets.", 0.6, 0.9)
    )
    ids["olives"] = await store.add_memory(NewMemory("bram", "dislike", "Bram can't stand olives on pizza.", 0.4, 0.9))
    ids["boundary"] = await store.add_memory(
        NewMemory("bram", "boundary", "Bram hates it when every message ends with a question.", 0.9, 0.95)
    )
    ids["pet"] = await store.add_memory(
        NewMemory("relationship", "pet_name", "Sofia calls him 'professor' when he over-explains.", 0.7, 0.9)
    )
    ids["joke"] = await store.add_memory(
        NewMemory("relationship", "inside_joke", "The running joke about the colour-blind boyfriend.", 0.5, 0.9)
    )
    return ids


async def test_relevant_memory_selected_irrelevant_skipped(store, settings, clock):
    ids = await seed(store)
    ctx = await retriever(store, settings).retrieve("did you ever see Mulero live?", clock())
    chosen = {m.id for m in ctx.bram}
    assert ids["mulero"] in chosen
    assert ids["olives"] not in chosen
    assert ids["boundary"] in chosen  # always-on
    assert ids["pet"] in {m.id for m in ctx.relationship}  # always-on


async def test_upcoming_event_surfaces_without_being_mentioned(store, settings, clock):
    today = clock().astimezone(settings.tz).date()
    soon = await store.add_memory(
        NewMemory("bram", "plan", "Bram is going to Levenslang.", 0.7, 0.95, event_date=today + timedelta(days=2))
    )
    far = await store.add_memory(
        NewMemory("bram", "plan", "Bram has a wedding to attend.", 0.7, 0.95, event_date=today + timedelta(days=60))
    )
    ctx = await retriever(store, settings).retrieve("ugh mondays", clock())
    chosen = {m.id for m in ctx.bram}
    assert soon in chosen
    assert far not in chosen


async def test_embeddings_improve_recall(store, settings, clock):
    # Lexically different but semantically matched via (toy) embeddings.
    mem = await store.add_memory(
        NewMemory("bram", "interest", "He is into dark techno.", 0.5, 0.9, embedding=[1, 0, 0, 0, 0, 0, 0, 1, 0.1])
    )
    ctx = await retriever(store, settings).retrieve(
        "what are you listening to", clock(), query_embedding=[1, 0, 0, 0, 0, 0, 0, 1, 0.1]
    )
    assert mem in [m.id for m in ctx.bram]


async def test_episodes_and_threads_included(store, settings, clock):
    now = clock()
    await store.add_episode(
        title="Late talk about Lisbon",
        summary="Sofia told him why she left.",
        tone="tender",
        importance=0.9,
        tags=["lisbon"],
        started_at=now - timedelta(days=3),
        ended_at=now - timedelta(days=3),
    )
    await store.open_thread("Bram is dreading Monday's meeting with his manager", due_date=date(2026, 10, 5))
    ctx = await retriever(store, settings).retrieve("hey", now)
    assert [e.title for e in ctx.episodes] == ["Late talk about Lisbon"]
    assert [t.content for t in ctx.threads] == ["Bram is dreading Monday's meeting with his manager"]

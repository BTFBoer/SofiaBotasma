"""Memory storage, de-duplication, deletion and persistence."""

from __future__ import annotations

from datetime import date

from app.companion.schemas import MemoryCandidate, SofiaFact
from app.memory.database import Database
from app.memory.extraction import MemoryWriter, is_trivial, normalize_category
from app.memory.models import NewMemory
from app.memory.store import MemoryStore


def cand(content: str, **kw) -> MemoryCandidate:
    return MemoryCandidate(content=content, **{"category": "preference", "importance": 0.7, "confidence": 0.9, **kw})


async def test_store_and_list_memory(store):
    mem_id = await store.add_memory(
        NewMemory(
            subject="bram",
            category="plan",
            content="Bram is going to Levenslang on 23 October.",
            importance=0.8,
            confidence=0.95,
            event_date=date(2026, 10, 23),
            source_message_id=12,
        )
    )
    memories = await store.list_memories("bram")
    assert [m.id for m in memories] == [mem_id]
    m = memories[0]
    assert m.event_date == date(2026, 10, 23)
    assert m.source_message_id == 12
    assert m.created_at is not None and m.last_referenced_at is None


async def test_writer_filters_trivia_and_speculation(store, clock):
    writer = MemoryWriter(store, None, clock)
    ids = await writer.ingest_candidates(
        [
            cand("Bram said lol."),
            cand("Bram is drinking water."),
            cand("Bram might secretly hate his job.", confidence=0.3),
            cand("Bram prefers Óscar Mulero to mainstream hard techno."),
        ],
        source_message_id=None,
    )
    contents = [m.content for m in await store.list_memories("bram")]
    assert contents == ["Bram prefers Óscar Mulero to mainstream hard techno."]
    assert len(ids) == 1


async def test_writer_deduplicates_and_newer_wins_for_bram(store, clock):
    writer = MemoryWriter(store, None, clock)
    await writer.ingest_candidates([cand("Bram prefers Mulero to mainstream hard techno.", importance=0.5)], None)
    await writer.ingest_candidates([cand("Bram prefers Mulero to mainstream hard techno!", importance=0.9)], None)
    clock.advance(days=1)
    await writer.ingest_candidates([cand("Bram strongly prefers Mulero over mainstream hard techno.")], None)
    memories = await store.list_memories("bram")
    assert len(memories) == 1
    assert memories[0].importance == 0.9
    assert "strongly" in memories[0].content


async def test_sofia_facts_older_claim_wins_and_day_facts_expire(store, clock):
    writer = MemoryWriter(store, None, clock)
    await writer.ingest_sofia_facts(
        [SofiaFact(content="Sofia hates raisins in savory food.", category="preference")], None
    )
    await writer.ingest_sofia_facts(
        [SofiaFact(content="Sofia hates raisins in any savory food.", category="preference")], None
    )
    await writer.ingest_sofia_facts(
        [SofiaFact(content="Sofia is having dinner with Tiago tonight.", category="today", durable=False)], None
    )
    facts = await store.list_memories("sofia")
    assert [f.content for f in facts] == [
        "Sofia hates raisins in savory food.",
        "Sofia is having dinner with Tiago tonight.",
    ]
    clock.advance(days=6)
    assert [f.content for f in await store.list_memories("sofia")] == ["Sofia hates raisins in savory food."]
    assert await store.purge_expired_memories() == 1


async def test_delete_memories(store):
    a = await store.add_memory(NewMemory("bram", "plan", "Bram has a dentist appointment on Friday.", 0.5, 0.9))
    b = await store.add_memory(NewMemory("bram", "person", "Bram's sister is called Eva.", 0.8, 0.9))
    assert await store.delete_memories([a]) == 1
    assert [m.id for m in await store.list_memories("bram")] == [b]


async def test_database_persists_across_restart(tmp_path, clock):
    path = tmp_path / "persist.db"
    db = Database(path)
    await db.connect()
    store = MemoryStore(db, clock=clock)
    await store.add_message(chat_id=1, role="user", content="morning", telegram_message_id=10)
    await store.add_memory(NewMemory("bram", "interest", "Bram loves Dasha Rush's ambient work.", 0.7, 0.9))
    await store.save_state({"dims": {"trust": 0.4}})
    await store.set_setting("proactive_enabled", "1")
    await db.close()

    db2 = Database(path)
    await db2.connect()
    store2 = MemoryStore(db2, clock=clock)
    assert [m.content for m in await store2.recent_messages(1, 10)] == ["morning"]
    assert [m.content for m in await store2.list_memories("bram")] == ["Bram loves Dasha Rush's ambient work."]
    assert (await store2.load_state())["dims"]["trust"] == 0.4
    assert await store2.get_setting("proactive_enabled") == "1"
    await db2.close()


async def test_duplicate_telegram_message_ignored(store):
    first = await store.add_message(chat_id=1, role="user", content="hey", telegram_message_id=5)
    second = await store.add_message(chat_id=1, role="user", content="hey", telegram_message_id=5)
    assert first is not None and second is None
    assert await store.count_messages() == 1


def test_trivial_and_category_helpers():
    assert is_trivial("Bram said lol.")
    assert is_trivial("ok")
    assert not is_trivial("Bram's sister Eva is getting married in June.")
    assert normalize_category("Inside Joke", "relationship") == "inside_joke"
    assert normalize_category("nickname", "relationship") == "pet_name"
    assert normalize_category("weird", "bram") == "other"

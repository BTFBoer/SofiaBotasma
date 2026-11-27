"""/reset and /forget require explicit confirmation."""

from __future__ import annotations

from app.memory.models import NewMemory


async def seed(store):
    await store.add_message(chat_id=1, role="user", content="remember Levenslang", telegram_message_id=1)
    await store.add_memory(NewMemory("bram", "plan", "Bram is going to Levenslang on 23 October.", 0.8, 0.9))
    await store.add_memory(NewMemory("bram", "person", "Bram's sister is called Eva.", 0.8, 0.9))
    await store.save_state({"dims": {"trust": 0.5}})
    await store.set_setting("proactive_enabled", "1")


async def test_reset_requires_valid_confirmation(controls, store):
    await seed(store)
    token = controls.request_reset()
    assert await store.count_messages() == 1  # nothing erased by merely asking

    assert await controls.confirm_reset("wrong-token") is False
    assert await store.count_messages() == 1

    assert await controls.confirm_reset(token) is True
    assert await store.count_messages() == 0
    assert await store.list_memories() == []
    assert await store.load_state() is None
    assert await store.get_setting("proactive_enabled") == "1"  # preferences survive

    assert await controls.confirm_reset(token) is False  # single use


async def test_reset_confirmation_expires(controls, store, clock):
    await seed(store)
    token = controls.request_reset()
    clock.advance(minutes=6)
    assert await controls.confirm_reset(token) is False
    assert await store.count_messages() == 1


async def test_reset_cancel(controls, store):
    await seed(store)
    token = controls.request_reset()
    assert controls.cancel(token) is True
    assert await controls.confirm_reset(token) is False
    assert await store.count_messages() == 1


async def test_forget_finds_and_deletes_selected_only(controls, store):
    await seed(store)
    matches = await controls.find_forget_matches("levenslang")
    assert [m.text for m in matches] == ["Bram is going to Levenslang on 23 October."]
    token = controls.request_forget(matches)
    assert len(await store.list_memories("bram")) == 2  # not yet
    assert await controls.confirm_forget(token, 0) == 1
    assert [m.content for m in await store.list_memories("bram")] == ["Bram's sister is called Eva."]
    assert await controls.confirm_forget(token, 0) == -1  # token consumed


async def test_export_contains_everything(controls, store):
    import json

    await seed(store)
    data = json.loads(await controls.export_json())
    assert data["format"] == "sofia-export"
    assert len(data["messages"]) == 1 and data["messages"][0]["role"] == "bram"
    assert len(data["memories"]) == 2
    assert "embedding" not in data["memories"][0]

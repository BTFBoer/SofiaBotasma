"""The real delivery path: batch -> plan -> typing -> timed bubbles -> recorded -> state applied."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.companion.engine import IncomingMessage
from app.telegram_bot import SofiaBot
from tests.conftest import ALLOWED_ID
from tests.fakes import turn_json


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    real_sleep = asyncio.sleep

    async def _instant(_seconds: float) -> None:
        await real_sleep(0)  # still yield to the event loop

    monkeypatch.setattr("app.telegram_bot.asyncio.sleep", _instant)
    monkeypatch.setattr("app.utils.timing.asyncio.sleep", _instant)


@pytest.fixture
def bot(settings, db, store, provider, engine, controls):
    sofia = SofiaBot(settings, db=db, store=store, provider=provider, engine=engine, controls=controls)
    counter = {"n": 1000}

    async def send_message(chat_id, text):
        counter["n"] += 1
        return SimpleNamespace(message_id=counter["n"], text=text)

    fake_bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=send_message),
        send_chat_action=AsyncMock(),
        set_message_reaction=AsyncMock(),
    )
    sofia.app = SimpleNamespace(bot=fake_bot)  # type: ignore[assignment]
    return sofia


async def test_multi_bubble_delivery_and_recording(bot, engine, provider, store):
    provider.queue(
        turn_json(
            ["bold assumption", "…but unfortunately yes"],
            relationship_update={
                "familiarity": 0,
                "trust": 0,
                "affection": 1,
                "attraction": 0,
                "playfulness": 0,
                "emotional_openness": 0,
                "sexual_comfort": 0,
                "irritation": 0,
            },
        )
    )
    local_id = await engine.record_incoming(ALLOWED_ID, IncomingMessage(telegram_message_id=1, text="You missed me."))
    await bot._process_batch(ALLOWED_ID, [local_id])

    sent = [c.args[1] for c in bot.app.bot.send_message.await_args_list]
    assert sent == ["bold assumption", "…but unfortunately yes"]
    bot.app.bot.send_chat_action.assert_awaited()  # Telegram's real typing indicator
    stored = await store.recent_messages(ALLOWED_ID, 10)
    assert [(m.role, m.telegram_message_id) for m in stored] == [("user", 1), ("assistant", 1001), ("assistant", 1002)]
    assert (await engine.load_state()).dims["affection"] > 0.15


async def test_reaction_only_reply(bot, engine, provider):
    provider.queue(turn_json([], reaction="❤"))
    local_id = await engine.record_incoming(ALLOWED_ID, IncomingMessage(telegram_message_id=2, text="night x"))
    await bot._process_batch(ALLOWED_ID, [local_id])
    bot.app.bot.set_message_reaction.assert_awaited_once()
    bot.app.bot.send_message.assert_not_awaited()


async def test_llm_outage_sends_neutral_message_not_a_stack_trace(bot, engine, provider):
    from tests.fakes import transient

    provider.queue(transient())
    local_id = await engine.record_incoming(ALLOWED_ID, IncomingMessage(telegram_message_id=3, text="hey"))
    await bot._process_batch(ALLOWED_ID, [local_id])
    (text,) = [c.args[1] for c in bot.app.bot.send_message.await_args_list]
    assert "Traceback" not in text and "Error" not in text
    assert "glitch" in text or "again" in text

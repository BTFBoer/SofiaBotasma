"""Unauthorized users are blocked before anything else runs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ApplicationHandlerStop

from app.telegram_bot import SofiaBot, is_authorized
from tests.conftest import ALLOWED_ID


def fake_update(user_id: int | None, *, chat_type: str = "private", update_id: int = 1):
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    message = SimpleNamespace(reply_text=AsyncMock(), text="hi", caption=None)
    return SimpleNamespace(
        update_id=update_id,
        effective_user=user,
        effective_chat=SimpleNamespace(id=user_id or 0, type=chat_type),
        effective_message=message,
        callback_query=None,
    )


@pytest.fixture
def bot(settings, db, store, provider, engine, controls):
    return SofiaBot(settings, db=db, store=store, provider=provider, engine=engine, controls=controls)


def test_is_authorized():
    assert is_authorized(fake_update(ALLOWED_ID), ALLOWED_ID)
    assert not is_authorized(fake_update(999), ALLOWED_ID)
    assert not is_authorized(fake_update(None), ALLOWED_ID)
    assert not is_authorized(fake_update(ALLOWED_ID), None)


async def test_gate_blocks_unauthorized_user_silently(bot, provider, store):
    update = fake_update(999)
    with pytest.raises(ApplicationHandlerStop):
        await bot._gate(update, SimpleNamespace())
    update.effective_message.reply_text.assert_not_called()
    assert provider.calls == []
    assert await store.count_messages() == 0


async def test_gate_optional_unauthorized_reply(tmp_path, db, store, provider, engine, controls):
    from tests.conftest import make_settings

    settings = make_settings(tmp_path, UNAUTHORIZED_REPLY="This is a private bot.")
    bot = SofiaBot(settings, db=db, store=store, provider=provider, engine=engine, controls=controls)
    update = fake_update(999)
    with pytest.raises(ApplicationHandlerStop):
        await bot._gate(update, SimpleNamespace())
    update.effective_message.reply_text.assert_awaited_once_with("This is a private bot.")


async def test_gate_allows_owner_and_drops_duplicates(bot):
    update = fake_update(ALLOWED_ID, update_id=77)
    await bot._gate(update, SimpleNamespace())  # passes
    with pytest.raises(ApplicationHandlerStop):
        await bot._gate(update, SimpleNamespace())  # same update id again


async def test_gate_ignores_group_chats(bot):
    with pytest.raises(ApplicationHandlerStop):
        await bot._gate(fake_update(ALLOWED_ID, chat_type="group", update_id=5), SimpleNamespace())


async def test_handlers_recheck_authorization(bot, provider, store):
    # Even if the gate were bypassed, handlers refuse to act for strangers.
    update = fake_update(999)
    await bot.on_message(update, SimpleNamespace())
    await bot.cmd_memory(update, SimpleNamespace())
    await bot.cmd_export(update, SimpleNamespace())
    update.effective_message.reply_text.assert_not_called()
    assert provider.calls == []
    assert await store.count_messages() == 0

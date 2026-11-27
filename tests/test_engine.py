"""Engine: context assembly, updates after a turn, and failure recovery."""

from __future__ import annotations

import asyncio

import pytest

from app.companion.engine import GLITCH_MESSAGES, REFUSAL_NOTICE, IncomingMessage
from app.llm.provider import ImagePart, LLMError, LLMResult, LLMTransientError, with_retries
from app.memory.models import NewMemory
from tests.conftest import ALLOWED_ID
from tests.fakes import transient, turn_json

CHAT = ALLOWED_ID


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    real_sleep = asyncio.sleep

    async def _no_sleep(_seconds: float) -> None:
        await real_sleep(0)  # still yield to the event loop

    monkeypatch.setattr("app.llm.provider.asyncio.sleep", _no_sleep)


def all_text(call) -> str:
    return "\n".join(m.text for m in call["messages"])


async def say(engine, text: str, tg_id: int, **kw) -> int:
    local_id = await engine.record_incoming(CHAT, IncomingMessage(telegram_message_id=tg_id, text=text, **kw))
    assert local_id is not None
    return local_id


async def test_reply_turn_end_to_end(engine, provider, store):
    provider.queue(
        turn_json(
            ["bold assumption", "…but unfortunately yes"],
            memory_candidates=[
                {
                    "subject": "bram",
                    "content": "Bram is going to Levenslang on 23 October.",
                    "category": "plan",
                    "importance": 0.85,
                    "confidence": 0.95,
                    "event_date": "2026-10-23",
                }
            ],
            sofia_facts=[{"content": "Sofia has never been to Levenslang.", "category": "biography", "durable": True}],
            unresolved_threads=[
                {
                    "action": "open",
                    "id": None,
                    "content": "Whether Sofia will ever come round to Mulero",
                    "due_date": None,
                }
            ],
            relationship_update={
                "familiarity": 1,
                "trust": 0,
                "affection": 1,
                "attraction": 1,
                "playfulness": 1,
                "emotional_openness": 0,
                "sexual_comfort": 0,
                "irritation": 0,
            },
        )
    )
    msg_id = await say(engine, "You missed me. Also: Levenslang on the 23rd, Mulero closing.", 100)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.kind == "reply"
    assert plan.bubbles == ["bold assumption", "…but unfortunately yes"]

    call = provider.calls[0]
    assert call["schema_name"] == "sofia_turn"
    assert "You are Sofia." in call["instructions"]
    context = call["messages"][0].text
    assert "CURRENT STATE" in context and "Europe/Amsterdam" in context
    assert call["messages"][-2].role == "user" and "Levenslang" in call["messages"][-2].text

    for i, bubble in enumerate(plan.bubbles):
        await engine.record_outgoing(plan, bubble, 500 + i)
    await engine.apply(plan)

    memories = await store.list_memories("bram")
    assert [m.content for m in memories] == ["Bram is going to Levenslang on 23 October."]
    assert memories[0].source_message_id == msg_id
    assert [m.content for m in await store.list_memories("sofia")] == ["Sofia has never been to Levenslang."]
    assert len(await store.list_threads("open")) == 1
    state = await engine.load_state()
    assert state.dims["affection"] > 0.15 and state.turns == 1
    assert [m.role for m in await store.recent_messages(CHAT, 10)] == ["user", "assistant", "assistant"]


async def test_memories_and_reply_context_reach_the_model(engine, provider, store):
    await store.add_memory(NewMemory("bram", "interest", "Bram loves Óscar Mulero's hypnotic sets.", 0.7, 0.95))
    await store.add_message(
        chat_id=CHAT, role="assistant", content="okay but is Mulero actually good or just loud", telegram_message_id=900
    )
    msg_id = await say(
        engine, "he is NOT just loud", 101, reply_to={"who": "sofia", "text": "", "telegram_message_id": 900}
    )
    await engine.plan_reply(CHAT, [msg_id], {})
    text = all_text(provider.calls[0])
    assert "Bram loves Óscar Mulero's hypnotic sets." in text
    assert "[replying to her message: “okay but is Mulero actually good or just loud”]" in text


async def test_images_are_passed_and_noted(engine, provider, store):
    provider.queue(turn_json(["that cat is judging you"], image_note="a grey cat on a windowsill"))
    msg_id = await say(engine, "", 102, kind="photo", images=[ImagePart(b"\xff\xd8fake", "image/jpeg")])
    plan = await engine.plan_reply(CHAT, [msg_id], {msg_id: [ImagePart(b"\xff\xd8fake", "image/jpeg")]})
    assert provider.calls[0]["messages"][-2].images
    await engine.apply(plan)
    stored = (await store.get_messages([msg_id]))[0]
    assert stored.meta["image_note"] == "a grey cat on a windowsill"


async def test_transient_failures_fall_back_to_neutral_message(engine, provider, store):
    provider.queue(transient(), transient(), transient())
    msg_id = await say(engine, "morning", 103)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.kind == "fallback"
    assert plan.bubbles[0] in GLITCH_MESSAGES
    await engine.record_outgoing(plan, plan.bubbles[0], 600)
    await engine.apply(plan)  # no-op for fallbacks
    history = await store.recent_messages(CHAT, 10)
    assert [m.content for m in history] == ["morning"]  # glitch text excluded from future context


async def test_openai_provider_retries_transient_errors(settings):
    import httpx
    import openai

    from app.llm.openai_provider import OpenAIResponsesProvider
    from app.llm.provider import ChatMessage

    provider = OpenAIResponsesProvider(settings)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    rate_limited = openai.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None)

    class FakeResponse:
        output_text = turn_json(["morning"])
        output = []
        usage = None
        status = "completed"

    calls = {"n": 0}

    async def create(**kwargs):
        calls["n"] += 1
        assert kwargs["store"] is False
        assert kwargs["text"]["format"]["strict"] is True
        if calls["n"] == 1:
            raise rate_limited
        return FakeResponse()

    provider.client.responses.create = create  # type: ignore[method-assign]
    result = await provider.generate_json(
        instructions="x", messages=[ChatMessage("user", "morning")], schema={}, schema_name="t"
    )
    assert calls["n"] == 2
    assert "morning" in result.text
    await provider.aclose()


async def test_garbage_output_is_regenerated(engine, provider):
    provider.queue('{"broken": ', turn_json(["shut up"]))
    msg_id = await say(engine, "You're behaving.", 105)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.bubbles == ["shut up"]
    assert "could not be used" in provider.calls[1]["messages"][-1].text


async def test_assistant_voice_triggers_one_rewrite(engine, provider):
    provider.queue(
        turn_json(["That's a great question, Bram! How can I help you today?"]),
        turn_json(["that's a very generous interpretation of the evidence"]),
    )
    msg_id = await say(engine, "You're behaving.", 106)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.bubbles == ["that's a very generous interpretation of the evidence"]
    assert len(provider.calls) == 2


async def test_unrecoverable_twice_falls_back(engine, provider):
    provider.queue("{", "{")
    msg_id = await say(engine, "hey", 107)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.kind == "fallback"


async def test_refusal_becomes_ooc_notice_and_is_excluded(engine, provider, store):
    provider.queue(LLMResult(text="", refusal="I can't help with that."))
    msg_id = await say(engine, "something the provider refuses", 108)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.kind == "refusal" and plan.ooc
    assert plan.bubbles == [REFUSAL_NOTICE]
    assert await store.recent_messages(CHAT, 10) == []


async def test_non_transient_error_is_not_retried(engine, provider):
    provider.queue(LLMError("bad request"))
    msg_id = await say(engine, "hey", 109)
    plan = await engine.plan_reply(CHAT, [msg_id], {})
    assert plan.kind == "fallback" and len(provider.calls) == 1


async def test_with_retries_backoff():
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise LLMTransientError("503")
        return "ok"

    assert await with_retries(flaky, attempts=3) == "ok"
    assert attempts["n"] == 3


async def test_private_dynamic_stays_latent_until_bram_raises_it(engine, provider):
    # Only meaningful when a private overlay defines dynamics.
    if not engine.dynamic_specs:
        pytest.skip("no private dynamics configured")
    spec = engine.dynamic_specs[0]
    first = await say(engine, "long day, I'm exhausted", 110)
    await engine.plan_reply(CHAT, [first], {})
    assert spec.emerging_guidance[:40] not in all_text(provider.calls[-1])

    keyword = spec.detect_keywords[0]
    second = await say(engine, f"my {keyword} hurt after that walk", 111)
    plan = await engine.plan_reply(CHAT, [second], {})
    assert spec.emerging_guidance[:40] in all_text(provider.calls[-1])
    assert plan.state.dynamics[spec.id].stage == "emerging"


async def test_opener_and_proactive_decline(engine, provider):
    provider.queue(turn_json(["so this is where you text people"]))
    opener = await engine.plan_opener(CHAT)
    assert opener.kind == "opener" and opener.bubbles

    proactive_json = turn_json([], send=False)
    provider.queue(proactive_json)
    assert await engine.plan_proactive(CHAT, ["Bram has a big meeting today"]) is None
    assert provider.calls[-1]["schema_name"] == "sofia_proactive"


async def test_concurrent_writes_are_safe(engine, store):
    await asyncio.gather(*(say(engine, f"msg {i}", 200 + i) for i in range(20)))
    assert await store.count_messages() == 20

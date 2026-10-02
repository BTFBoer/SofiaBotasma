"""The first-time setup assistant: input cleaning, .env writing, and the full flow with fakes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import setup_wizard as wiz

TOKEN = "1234567890:AAH" + "x" * 32


def test_clean_paste_removes_accidental_characters():
    assert wiz.clean_paste(f'  "{TOKEN}"\n') == TOKEN
    assert wiz.clean_paste("sk-abc​def ghi") == "sk-abcdefghi"


def test_token_and_key_shapes():
    assert wiz.looks_like_bot_token(TOKEN)
    assert not wiz.looks_like_bot_token("hallo")
    assert wiz.looks_like_openai_key("sk-proj-" + "a" * 40)
    assert not wiz.looks_like_openai_key("pk-123")


def test_render_env_fills_template_and_keeps_comments():
    template = "# comment\nTELEGRAM_BOT_TOKEN=\nLLM_MODEL=gpt-x\nTIMEZONE=Europe/Amsterdam\n"
    out = wiz.render_env(template, {"TELEGRAM_BOT_TOKEN": TOKEN, "LLM_MODEL": "m", "EXTRA": "1"})
    assert "# comment" in out
    assert f"TELEGRAM_BOT_TOKEN={TOKEN}" in out
    assert "LLM_MODEL=m" in out and "TIMEZONE=Europe/Amsterdam" in out
    assert out.rstrip().endswith("EXTRA=1")
    assert wiz.parse_env(out)["LLM_MODEL"] == "m"


def test_model_candidates_follow_what_the_account_has():
    assert wiz.candidate_chat_models(None)[0] == wiz.PREFERRED_CHAT_MODELS[0]
    assert wiz.candidate_chat_models({"gpt-5.5", "gpt-5.4", "whisper-1"}) == ["gpt-5.5", "gpt-5.4"]
    odd = wiz.candidate_chat_models({"gpt-7-nova", "gpt-7-nova-realtime", "dall-e-3"})
    assert odd == ["gpt-7-nova"]
    assert wiz.candidate_utility_models({"gpt-5.4-mini"}, "gpt-5.5") == ["gpt-5.4-mini", "gpt-5.5"]


class FakeOpenAI:
    def __init__(self, models: set[str], working: set[str]) -> None:
        self._models = models
        self._working = working
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id=m) for m in models])
        self.responses = SimpleNamespace(create=self._create)
        self.embeddings = SimpleNamespace(create=lambda **kw: SimpleNamespace(data=[]))

    def _create(self, **kwargs):
        import httpx
        import openai

        if kwargs["model"] not in self._working:
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            raise openai.NotFoundError("model not found", response=httpx.Response(404, request=request), body=None)
        return SimpleNamespace(output_text='{"ok": true}')


def test_full_setup_flow_writes_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    (tmp_path / ".env.example").write_text(
        "TELEGRAM_BOT_TOKEN=\nALLOWED_TELEGRAM_USER_ID=\nOPENAI_API_KEY=\nLLM_MODEL=\nLLM_REASONING_EFFORT=low\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wiz, "ENV_PATH", env_path)
    monkeypatch.setattr(wiz, "TEMPLATE_PATH", tmp_path / ".env.example")
    monkeypatch.setattr(wiz, "PERSONA_DIR", tmp_path / "persona")

    acked = {}

    def fake_telegram(token, method, params=None, timeout=15.0):
        if token != TOKEN:
            return None
        if method == "getMe":
            return {"username": "sofia_test_bot"}
        if method == "deleteWebhook":
            return True
        if method == "getUpdates":
            if params.get("timeout") == 0:
                acked["offset"] = params["offset"]
                return []
            return [
                {"update_id": 7, "message": {"chat": {"type": "private"},
                                             "from": {"id": 4242, "first_name": "Bram", "username": "bbtf1023"}}}
            ]
        raise AssertionError(method)

    monkeypatch.setattr(wiz, "telegram_get", fake_telegram)
    monkeypatch.setattr(
        wiz, "_openai_client", lambda key: FakeOpenAI({"gpt-5.5", "gpt-5.4-mini", "text-embedding-3-small"},
                                                      {"gpt-5.5", "gpt-5.4-mini"})
    )
    answers = iter(["not a token", f"  {TOKEN} ", "j", "sk-proj-" + "a" * 40])
    assert wiz.run(input_fn=lambda _prompt: next(answers)) == 0

    values = wiz.parse_env(env_path.read_text(encoding="utf-8"))
    assert values["TELEGRAM_BOT_TOKEN"] == TOKEN
    assert values["ALLOWED_TELEGRAM_USER_ID"] == "4242"
    assert values["LLM_MODEL"] == "gpt-5.5"
    assert values["UTILITY_MODEL"] == "gpt-5.4-mini"
    assert values["EMBEDDING_MODEL"] == "text-embedding-3-small"
    assert values["LLM_REASONING_EFFORT"] == "low"
    assert acked["offset"] == 8  # the hello message is marked handled


def test_setup_stops_cleanly_without_credit(tmp_path, monkeypatch):
    import httpx
    import openai

    monkeypatch.setattr(wiz, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(wiz, "TEMPLATE_PATH", tmp_path / "missing.example")
    monkeypatch.setattr(wiz, "telegram_get", lambda *a, **k: (
        {"username": "b"} if a[1] == "getMe" else True if a[1] == "deleteWebhook" else (
            [] if (k.get("params") or (a[2] if len(a) > 2 else {})).get("timeout") == 0 else
            [{"update_id": 1, "message": {"chat": {"type": "private"}, "from": {"id": 1, "first_name": "B"}}}])))

    class NoCredit(FakeOpenAI):
        def _create(self, **kwargs):
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            raise openai.RateLimitError("You exceeded your current quota", response=httpx.Response(429, request=request), body=None)

    monkeypatch.setattr(wiz, "_openai_client", lambda key: NoCredit(set(), set()))
    answers = iter([TOKEN, "j", "sk-proj-" + "b" * 40])
    assert wiz.run(input_fn=lambda _p: next(answers)) == 1
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("answer,expected", [("", True), ("J", True), ("nee", False)])
def test_yes_no(answer, expected):
    assert wiz.ask_yes_no("?", True, input_fn=lambda _p: answer) is expected

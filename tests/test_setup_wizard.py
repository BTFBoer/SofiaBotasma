"""The first-time setup assistant: input cleaning, .env writing, and the full flow with fakes."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from app import setup_wizard as wiz

TOKEN = "1234567890:AAH" + "x" * 32
KEY = "sk-proj-" + "a" * 40


def test_clean_paste_removes_accidental_characters():
    assert wiz.clean_paste(f'  "{TOKEN}"\n') == TOKEN
    assert wiz.clean_paste("sk-abc​def ghi") == "sk-abcdefghi"


def test_pick_finds_codes_inside_labels():
    assert wiz.pick(wiz.TOKEN_SEARCH, f"Telegram-token: {TOKEN}") == TOKEN
    assert wiz.pick(wiz.KEY_SEARCH, f"OpenAI-sleutel {KEY}") == KEY
    assert wiz.pick(wiz.TOKEN_SEARCH, "hallo") == "hallo"


def test_token_and_key_shapes():
    assert wiz.looks_like_bot_token(TOKEN)
    assert not wiz.looks_like_bot_token("hallo")
    assert wiz.looks_like_openai_key(KEY)
    assert not wiz.looks_like_openai_key("pk-123")
    assert TOKEN not in wiz.mask(TOKEN) and KEY not in wiz.mask(KEY)


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
    odd = wiz.candidate_chat_models({"gpt-7-nova", "gpt-7-nova-pro", "gpt-7-nova-mini", "gpt-7-nova-realtime"})
    assert odd == ["gpt-7-nova", "gpt-7-nova-mini"]  # no -pro, small models last
    assert wiz.candidate_utility_models({"gpt-5.4-mini"}, "gpt-5.5") == ["gpt-5.4-mini", "gpt-5.5"]


def test_find_misnamed_private_files(tmp_path, monkeypatch):
    persona = tmp_path / "persona"
    persona.mkdir()
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(wiz, "PERSONA_DIR", persona)
    (persona / "user_profile.private.example.yaml").write_text("x")
    (downloads / "persona.private (1).yaml").write_text("x")
    (downloads / "user_profile.private.yaml.txt").write_text("x")
    assert wiz.find_misnamed("persona.private.yaml", [persona, downloads]).name == "persona.private (1).yaml"
    assert wiz.find_misnamed("user_profile.private.yaml", [persona, downloads]).name == "user_profile.private.yaml.txt"
    assert wiz.find_misnamed("user_profile.private.yaml", [persona]) is None  # the example file is ignored


class FakeOpenAI:
    def __init__(self, models: set[str], working: set[str], *, valid: bool = True) -> None:
        self._working = working
        self._valid = valid
        self.models = SimpleNamespace(list=self._list)
        self._models = models
        self.responses = SimpleNamespace(create=self._create)
        self.embeddings = SimpleNamespace(create=lambda **kw: SimpleNamespace(data=[]))

    @staticmethod
    def _error(cls, status: int, message: str):
        request = httpx.Request("POST", "https://api.openai.com/v1/x")
        return cls(message, response=httpx.Response(status, request=request), body=None)

    def _list(self):
        if not self._valid:
            raise self._error(openai.AuthenticationError, 401, "invalid key")
        return [SimpleNamespace(id=m) for m in self._models]

    def _create(self, **kwargs):
        if kwargs["model"] not in self._working:
            raise self._error(openai.NotFoundError, 404, "model not found")
        return SimpleNamespace(output_text='{"ok": true}')


class FakeTelegram:
    def __init__(self) -> None:
        self.dropped = 0

    def __call__(self, token, method, params=None, timeout=15.0):
        if token != TOKEN:
            return None
        if method == "getMe":
            return {"username": "sofia_test_bot"}
        if method == "deleteWebhook":
            if params and params.get("drop_pending_updates") == "true":
                self.dropped += 1
            return True
        if method == "getUpdates":
            return [
                {
                    "update_id": 7,
                    "message": {
                        "chat": {"type": "private"},
                        "from": {"id": 4242, "first_name": "Bram", "username": "bram"},
                    },
                }
            ]
        raise AssertionError(method)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    (tmp_path / ".env.example").write_text(
        "TELEGRAM_BOT_TOKEN=\nALLOWED_TELEGRAM_USER_ID=\nOPENAI_API_KEY=\nLLM_MODEL=\nLLM_REASONING_EFFORT=low\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wiz, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(wiz, "TEMPLATE_PATH", tmp_path / ".env.example")
    monkeypatch.setattr(wiz, "PERSONA_DIR", tmp_path / "persona")
    monkeypatch.setattr(wiz, "ROOT", tmp_path)
    monkeypatch.setattr(wiz.Path, "home", staticmethod(lambda: tmp_path / "home"))
    return tmp_path


def run_with(answers):
    it = iter(answers)
    return wiz.run(input_fn=lambda _prompt: next(it), interactive=False)


def test_full_setup_flow_writes_env(paths, monkeypatch):
    telegram = FakeTelegram()
    monkeypatch.setattr(wiz, "telegram_get", telegram)
    clients = iter(
        [
            FakeOpenAI(set(), set(), valid=False),  # first paste: wrong key → asked again, no restart needed
            FakeOpenAI({"gpt-5.5", "gpt-5.4-mini", "text-embedding-3-small"}, {"gpt-5.5", "gpt-5.4-mini"}),
        ]
    )
    monkeypatch.setattr(wiz, "_openai_client", lambda key: next(clients))
    assert run_with(["not a token", f"Telegram-token: {TOKEN}", "j", "sk-proj-wrongwrongwrongwrong", KEY]) == 0

    values = wiz.parse_env((paths / ".env").read_text(encoding="utf-8"))
    assert values["TELEGRAM_BOT_TOKEN"] == TOKEN
    assert values["ALLOWED_TELEGRAM_USER_ID"] == "4242"
    assert values["OPENAI_API_KEY"] == KEY
    assert values["LLM_MODEL"] == "gpt-5.5"
    assert values["UTILITY_MODEL"] == "gpt-5.4-mini"
    assert values["EMBEDDING_MODEL"] == "text-embedding-3-small"
    assert values["LLM_REASONING_EFFORT"] == "low"
    assert telegram.dropped >= 2  # setup messages are thrown away, so Sofia won't answer them later


def test_redo_setup_can_keep_existing_codes(paths, monkeypatch):
    (paths / ".env").write_text(
        f"TELEGRAM_BOT_TOKEN={TOKEN}\nALLOWED_TELEGRAM_USER_ID=4242\nOPENAI_API_KEY={KEY}\nLLM_MODEL=old\nTIMEZONE=Europe/Amsterdam\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wiz, "telegram_get", FakeTelegram())
    monkeypatch.setattr(wiz, "_openai_client", lambda key: FakeOpenAI({"gpt-5.4"}, {"gpt-5.4"}))
    assert run_with(["j", "j", "j"]) == 0  # redo? keep Telegram? keep key?
    values = wiz.parse_env((paths / ".env").read_text(encoding="utf-8"))
    assert values["LLM_MODEL"] == "gpt-5.4"  # model re-checked
    assert values["ALLOWED_TELEGRAM_USER_ID"] == "4242"
    assert (paths / ".env.backup").exists()


def test_setup_stops_cleanly_without_credit(paths, monkeypatch):
    monkeypatch.setattr(wiz, "telegram_get", FakeTelegram())

    class NoCredit(FakeOpenAI):
        def _create(self, **kwargs):
            raise self._error(openai.RateLimitError, 429, "You exceeded your current quota")

    monkeypatch.setattr(wiz, "_openai_client", lambda key: NoCredit(set(), set()))
    assert run_with([TOKEN, "j", KEY]) == 1
    assert not (paths / ".env").exists()


def test_running_bot_gives_clear_message(paths, monkeypatch):
    def busy(token, method, params=None, timeout=15.0):
        if method == "getMe":
            return {"username": "b"}
        if method == "deleteWebhook":
            return True
        raise wiz.TelegramBusy("Sofia draait nog in een ander venster.")

    monkeypatch.setattr(wiz, "telegram_get", busy)
    assert run_with([TOKEN]) == 1


@pytest.mark.parametrize("answer,expected", [("", True), ("J", True), ("nee", False)])
def test_yes_no(answer, expected):
    assert wiz.ask_yes_no("?", True, input_fn=lambda _p: answer) is expected


def test_broken_private_file_is_not_adopted(paths, monkeypatch):
    downloads = paths / "home" / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "persona.private.yaml").write_text("static_core:\n  note: tijd: 9:00\n", encoding="utf-8")
    (downloads / "user_profile.private (1).yaml").write_text("intimate_profile:\n  general: {}\n", encoding="utf-8")
    missing = wiz.fix_private_files()
    assert missing == ["persona.private.yaml"]
    assert (paths / "persona" / "user_profile.private.yaml").exists()
    assert not (paths / "persona" / "persona.private.yaml").exists()


def test_keeping_telegram_does_not_drop_offline_messages(paths, monkeypatch):
    (paths / ".env").write_text(
        f"TELEGRAM_BOT_TOKEN={TOKEN}\nALLOWED_TELEGRAM_USER_ID=4242\nOPENAI_API_KEY={KEY}\n", encoding="utf-8"
    )
    telegram = FakeTelegram()
    monkeypatch.setattr(wiz, "telegram_get", telegram)
    monkeypatch.setattr(wiz, "_openai_client", lambda key: FakeOpenAI({"gpt-5.4"}, {"gpt-5.4"}))
    assert run_with(["j", "j", "j"]) == 0
    assert telegram.dropped == 0

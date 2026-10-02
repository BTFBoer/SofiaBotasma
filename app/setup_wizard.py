"""Interactive first-time setup (Dutch): python -m app --setup

Asks for the Telegram bot token and the OpenAI key, checks both live, finds
the owner's numeric Telegram id by asking them to message the bot, picks a
model the key actually has access to, and writes .env. Written for people
who have never used a terminal: one question at a time, every answer checked
immediately, plain-language errors.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TEMPLATE_PATH = ROOT / ".env.example"
PERSONA_DIR = ROOT / "persona"

# Suggestions only: the app itself always reads the model from .env.
PREFERRED_CHAT_MODELS = [
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6-astra",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
]
PREFERRED_UTILITY_MODELS = ["gpt-6-luna", "gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.1-mini", "gpt-5-mini"]
EMBEDDING_MODEL = "text-embedding-3-small"
TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
_NOT_CHAT = ("audio", "realtime", "transcribe", "tts", "image", "search", "embedding", "codex", "moderation", "instruct")

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
TELEGRAM_API = "https://api.telegram.org"


class SetupAbort(Exception):
    """Stops the wizard with a plain-language message."""


# --------------------------------------------------------------------------- pure helpers (tested)
def clean_paste(value: str) -> str:
    """Remove whitespace, quotes and invisible characters people paste by accident."""
    value = value.strip().strip("\"'“”‘’").strip()
    return re.sub(r"[\s​‌‍﻿]", "", value)


def looks_like_bot_token(value: str) -> bool:
    return bool(TOKEN_RE.match(value))


def looks_like_openai_key(value: str) -> bool:
    return value.startswith("sk-") and len(value) >= 20


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def render_env(template: str, values: dict[str, str]) -> str:
    """Fill `KEY=` lines of the template with values; keep comments and order; append unknown keys."""
    out: list[str] = []
    seen: set[str] = set()
    for line in template.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values:
                out.append(f"{key}={values[key]}")
                seen.add(key)
                continue
        out.append(line)
    extra = [k for k in values if k not in seen]
    if extra:
        out.append("")
        out.extend(f"{k}={values[k]}" for k in extra)
    return "\n".join(out) + "\n"


def candidate_chat_models(available: set[str] | None) -> list[str]:
    if available is None:
        return list(PREFERRED_CHAT_MODELS)
    preferred = [m for m in PREFERRED_CHAT_MODELS if m in available]
    if preferred:
        return preferred
    generic = [m for m in available if m.startswith("gpt-") and not any(x in m for x in _NOT_CHAT)]
    return sorted(generic, reverse=True)[:6]


def candidate_utility_models(available: set[str] | None, chat_model: str) -> list[str]:
    if available is None:
        return [*PREFERRED_UTILITY_MODELS, chat_model]
    return [m for m in PREFERRED_UTILITY_MODELS if m in available] + [chat_model]


# --------------------------------------------------------------------------- console helpers
def say(text: str = "") -> None:
    print(text, flush=True)


def ask(prompt: str, input_fn: Callable[[str], str] = input) -> str:
    try:
        return input_fn(prompt)
    except EOFError as exc:
        raise SetupAbort("Invoer gestopt.") from exc


def ask_yes_no(prompt: str, default: bool, input_fn: Callable[[str], str] = input) -> bool:
    suffix = " [J/n] " if default else " [j/N] "
    while True:
        answer = ask(prompt + suffix, input_fn).strip().lower()
        if not answer:
            return default
        if answer in {"j", "ja", "y", "yes"}:
            return True
        if answer in {"n", "nee", "no"}:
            return False
        say("   Typ j (ja) of n (nee) en druk op Enter.")


# --------------------------------------------------------------------------- Telegram
def telegram_get(token: str, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
    try:
        response = httpx.get(f"{TELEGRAM_API}/bot{token}/{method}", params=params or {}, timeout=timeout)
    except httpx.HTTPError as exc:
        raise SetupAbort(
            "Ik kan Telegram niet bereiken. Controleer je internetverbinding en probeer het opnieuw."
        ) from exc
    data = response.json() if response.content else {}
    if response.status_code == 401 or (not data.get("ok") and data.get("error_code") == 401):
        return None
    if not data.get("ok"):
        raise SetupAbort(f"Telegram gaf een foutmelding: {data.get('description', response.status_code)}")
    return data["result"]


def step_telegram_token(input_fn: Callable[[str], str]) -> tuple[str, str]:
    say("STAP 1 van 4 — Telegram-bot")
    say("Plak de code (token) die je van BotFather kreeg en druk op Enter.")
    say("Plakken in dit venster: rechtermuisklik, of Ctrl+V (Mac: Cmd+V).")
    for _ in range(5):
        token = clean_paste(ask("Token: ", input_fn))
        if not looks_like_bot_token(token):
            say("   Dat lijkt geen token. Het ziet eruit als 1234567890:AAH... (cijfers, dubbele punt, letters).")
            continue
        me = telegram_get(token, "getMe")
        if me is None:
            say("   Telegram kent dit token niet. Kopieer het nog een keer helemaal uit BotFather.")
            continue
        username = me.get("username", "")
        say(f"   ✓ Gevonden: je bot heet @{username}")
        say()
        return token, username
    raise SetupAbort("Het token werkte niet na meerdere pogingen. Vraag in BotFather een nieuw token met /token.")


def step_find_user_id(token: str, bot_username: str, input_fn: Callable[[str], str]) -> int:
    say("STAP 2 van 4 — Wie ben jij?")
    say("Ik moet weten wie de eigenaar is, zodat Sofia alleen met jou praat.")
    say(f"Open Telegram, ga naar je bot: https://t.me/{bot_username}")
    say("Druk op START (of typ: hallo) en stuur het. Ik wacht hier...")
    telegram_get(token, "deleteWebhook", {"drop_pending_updates": "false"})
    offset = 0
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        updates = telegram_get(
            token, "getUpdates", {"timeout": 25, "offset": offset, "allowed_updates": '["message"]'}, timeout=35
        )
        for update in updates or []:
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            user = message.get("from") or {}
            chat = message.get("chat") or {}
            if not user or chat.get("type") != "private":
                continue
            name = user.get("first_name", "")
            handle = f" (@{user['username']})" if user.get("username") else ""
            say(f"   Bericht ontvangen van {name}{handle}.")
            if ask_yes_no("   Ben jij dit?", True, input_fn):
                # Mark the message as handled so the bot doesn't answer it later.
                telegram_get(token, "getUpdates", {"offset": offset, "timeout": 0})
                say(f"   ✓ Jouw Telegram-nummer (ID) is {user['id']}. Alleen jij komt erin.")
                say()
                return int(user["id"])
            say("   Oké, dan wacht ik op een bericht van jou...")
    raise SetupAbort("Ik heb 10 minuten geen bericht ontvangen. Start het opnieuw en stuur je bot een berichtje.")


# --------------------------------------------------------------------------- OpenAI
def _openai_client(api_key: str) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=60, max_retries=1)


def list_models(client: Any) -> set[str] | None:
    try:
        return {m.id for m in client.models.list()}
    except Exception:
        return None


def test_chat_model(client: Any, model: str) -> tuple[bool, str | None, str]:
    """Try one tiny structured-output call. Returns (works, reasoning_effort, problem)."""
    import openai

    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    base = {
        "model": model,
        "input": "Reply with ok=true.",
        "text": {"format": {"type": "json_schema", "name": "check", "schema": schema, "strict": True}},
        "max_output_tokens": 400,
        "store": False,
    }
    for effort in ("low", None):
        kwargs = dict(base)
        if effort:
            kwargs["reasoning"] = {"effort": effort}
        try:
            client.responses.create(**kwargs)
            return True, effort, ""
        except openai.AuthenticationError as exc:
            raise SetupAbort("OpenAI kent deze sleutel niet. Maak een nieuwe sleutel en plak die.") from exc
        except openai.RateLimitError as exc:
            if "quota" in str(exc).lower():
                raise SetupAbort(
                    "Je OpenAI-account heeft geen tegoed. Ga naar platform.openai.com → Billing en voeg tegoed toe. "
                    "(Een ChatGPT Plus-abonnement telt hier niet mee.) Wacht daarna 5 minuten en probeer opnieuw."
                ) from exc
            return False, None, "te druk (rate limit)"
        except openai.BadRequestError as exc:
            if effort and "reasoning" in str(exc).lower():
                continue  # model doesn't take a reasoning setting: try without
            return False, None, str(exc)[:160]
        except (openai.NotFoundError, openai.PermissionDeniedError) as exc:
            return False, None, "geen toegang tot dit model" + (
                " (mogelijk moet je organisatie geverifieerd zijn)" if "verif" in str(exc).lower() else ""
            )
        except openai.APIConnectionError as exc:
            raise SetupAbort("Ik kan OpenAI niet bereiken. Controleer je internetverbinding.") from exc
        except openai.OpenAIError as exc:
            return False, None, str(exc)[:160]
    return False, None, "werkt niet"


def step_openai(input_fn: Callable[[str], str]) -> dict[str, str]:
    say("STAP 3 van 4 — OpenAI")
    say("Plak je OpenAI-sleutel (begint met sk-) en druk op Enter.")
    for _ in range(5):
        key = clean_paste(ask("Sleutel: ", input_fn))
        if looks_like_openai_key(key):
            break
        say("   Dat lijkt geen OpenAI-sleutel. Hij begint met sk- en is heel lang.")
    else:
        raise SetupAbort("Geen geldige sleutel ingevoerd.")

    client = _openai_client(key)
    say("   Even testen welk model jouw account kan gebruiken (kan een halve minuut duren)...")
    available = list_models(client)
    chat_model, effort = None, None
    for model in candidate_chat_models(available):
        works, effort, problem = test_chat_model(client, model)
        if works:
            chat_model = model
            break
        say(f"   - {model}: {problem}")
    if chat_model is None:
        raise SetupAbort(
            "Geen enkel geschikt model werkte met deze sleutel. Controleer op platform.openai.com of je tegoed "
            "hebt en of je organisatie geverifieerd is (Settings → Organization)."
        )
    say(f"   ✓ Sofia gebruikt: {chat_model}")

    utility = chat_model
    for model in candidate_utility_models(available, chat_model):
        if model == chat_model or test_chat_model(client, model)[0]:
            utility = model
            break

    embedding = ""
    if available is None or EMBEDDING_MODEL in available:
        try:
            client.embeddings.create(model=EMBEDDING_MODEL, input=["test"])
            embedding = EMBEDDING_MODEL
        except Exception:
            embedding = ""
    transcription = TRANSCRIPTION_MODEL if available is None or TRANSCRIPTION_MODEL in available else ""
    say("   ✓ OpenAI werkt.")
    say()
    return {
        "OPENAI_API_KEY": key,
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": chat_model,
        "LLM_REASONING_EFFORT": effort or "",
        "UTILITY_MODEL": utility,
        "EMBEDDING_MODEL": embedding,
        "TRANSCRIPTION_MODEL": transcription,
    }


# --------------------------------------------------------------------------- main
def check_private_files() -> None:
    missing = [n for n in ("persona.private.yaml", "user_profile.private.yaml") if not (PERSONA_DIR / n).exists()]
    if not missing:
        say("   ✓ Je privé-bestanden staan op hun plek.")
        return
    say("   Let op: deze privé-bestanden ontbreken nog in de map 'persona':")
    for name in missing:
        say(f"     - {name}")
    say("   Sofia werkt ook zonder, maar mist dan je persoonlijke instellingen.")
    say(f"   Zet ze in: {PERSONA_DIR}  en start daarna opnieuw.")


def run(input_fn: Callable[[str], str] = input) -> int:
    say()
    say("=" * 60)
    say("  Sofia — eerste keer instellen")
    say("=" * 60)
    say("Ik stel je 3 vragen. Na elke vraag controleer ik meteen of het klopt.")
    say()
    try:
        existing = parse_env(ENV_PATH.read_text(encoding="utf-8")) if ENV_PATH.exists() else {}
        if existing and not ask_yes_no("Er zijn al instellingen. Opnieuw instellen?", False, input_fn):
            say("Niets veranderd.")
            return 0
        token, bot_username = step_telegram_token(input_fn)
        user_id = step_find_user_id(token, bot_username, input_fn)
        openai_values = step_openai(input_fn)

        say("STAP 4 van 4 — Opslaan")
        values = {
            **existing,
            "TELEGRAM_BOT_TOKEN": token,
            "ALLOWED_TELEGRAM_USER_ID": str(user_id),
            **openai_values,
        }
        template = TEMPLATE_PATH.read_text(encoding="utf-8") if TEMPLATE_PATH.exists() else ""
        if ENV_PATH.exists():
            shutil.copyfile(ENV_PATH, ENV_PATH.with_name(".env.backup"))
        ENV_PATH.write_text(render_env(template, values), encoding="utf-8")
        say("   ✓ Instellingen opgeslagen (in het bestand .env — deel dat met niemand).")
        check_private_files()
        say()
        say("Klaar! Sofia kan nu starten.")
        say()
        return 0
    except SetupAbort as exc:
        say()
        say(f"STOP: {exc}")
        say()
        return 1
    except KeyboardInterrupt:
        say()
        say("Gestopt.")
        return 1


if __name__ == "__main__":
    sys.exit(run())

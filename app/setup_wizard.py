"""Interactive first-time setup (Dutch): python -m app --setup

Asks for the Telegram bot token and the OpenAI key, checks both live, finds
the owner's numeric Telegram id by asking them to message the bot, picks a
model the key actually has access to, and writes .env. Written for people
who have never used a terminal: one question at a time, every answer checked
immediately, plain-language errors, secrets wiped from the screen.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
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
PRIVATE_FILES = ("persona.private.yaml", "user_profile.private.yaml")

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
_NOT_CHAT = (
    "audio", "realtime", "transcribe", "tts", "image", "search", "embedding", "codex", "moderation", "instruct",
    "-pro", "deep-research",
)  # fmt: skip

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
TOKEN_SEARCH = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
KEY_SEARCH = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
TELEGRAM_API = "https://api.telegram.org"


class SetupAbort(Exception):
    """Stops the wizard with a plain-language message."""


class TelegramBusy(SetupAbort):
    """Another running copy of Sofia is polling this bot."""


# --------------------------------------------------------------------------- pure helpers (tested)
def clean_paste(value: str) -> str:
    """Remove whitespace, quotes and invisible characters people paste by accident."""
    value = value.strip().strip("\"'“”‘’").strip()
    return re.sub(r"[\s​‌‍﻿]", "", value)


def pick(pattern: re.Pattern[str], raw: str) -> str:
    """Find the code inside whatever was pasted (a label in front, quotes, extra text)."""
    cleaned = clean_paste(raw)
    match = pattern.search(cleaned)
    return match.group(0) if match else cleaned


def looks_like_bot_token(value: str) -> bool:
    return bool(TOKEN_RE.match(value))


def looks_like_openai_key(value: str) -> bool:
    return value.startswith("sk-") and len(value) >= 20


def mask(secret: str) -> str:
    return f"{secret[:6]}…{secret[-4:]}" if len(secret) > 12 else "…"


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
    generic = sorted((m for m in available if m.startswith("gpt-") and not any(x in m for x in _NOT_CHAT)), reverse=True)
    small = [m for m in generic if "mini" in m or "nano" in m]
    return ([m for m in generic if m not in small] + small)[:6]


def candidate_utility_models(available: set[str] | None, chat_model: str) -> list[str]:
    if available is None:
        return [*PREFERRED_UTILITY_MODELS, chat_model]
    return [m for m in PREFERRED_UTILITY_MODELS if m in available] + [chat_model]


def find_misnamed(name: str, folders: list[Path]) -> Path | None:
    """Find a private file saved under a slightly wrong name or in the wrong folder.

    Browsers rename repeat downloads ("persona.private (1).yaml", "persona.private-1.yaml")
    and Safari sometimes appends ".txt"; people also leave files in Downloads.
    """
    stem = name.removesuffix(".yaml")
    found: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            candidates = list(folder.glob(stem + "*"))
        except OSError:
            continue
        for path in candidates:
            if (
                path.is_file()
                and "example" not in path.name
                and path.suffix.lower() in {".yaml", ".yml", ".txt"}
                and path != PERSONA_DIR / name
            ):
                found.append(path)
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


# --------------------------------------------------------------------------- console helpers
def say(text: str = "") -> None:
    print(text, flush=True)


def clear_screen() -> None:
    """Wipe the window so a pasted secret never ends up on a help screenshot."""
    if not sys.stdout.isatty():
        return
    if os.name == "nt":
        os.system("cls")
    else:
        print("\033[H\033[2J\033[3J", end="", flush=True)


def ask(prompt: str, input_fn: Callable[[str], str] = input) -> str:
    try:
        return input_fn(prompt)
    except EOFError as exc:
        raise SetupAbort("Invoer gestopt.") from exc


def ask_yes_no(prompt: str, default: bool, input_fn: Callable[[str], str] = input) -> bool:
    while True:
        answer = ask(f"{prompt} (typ j of n, daarna Enter): ", input_fn).strip().lower()
        if not answer:
            return default
        if answer in {"j", "ja", "y", "yes"}:
            return True
        if answer in {"n", "nee", "no"}:
            return False
        say("   Typ alleen de letter j (ja) of n (nee) en druk op Enter.")


def banner() -> None:
    say()
    say("=" * 60)
    say("  Sofia — eerste keer instellen")
    say("=" * 60)


def heading(number: int, title: str) -> None:
    say(f"VRAAG {number} van 3 — {title}")


# --------------------------------------------------------------------------- Telegram
def telegram_get(token: str, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
    try:
        response = httpx.get(f"{TELEGRAM_API}/bot{token}/{method}", params=params or {}, timeout=timeout)
        data = response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise SetupAbort(
            "Ik kan Telegram niet bereiken. Controleer je internetverbinding en probeer het opnieuw."
        ) from exc
    if response.status_code == 401 or data.get("error_code") == 401:
        return None
    if response.status_code == 409 or data.get("error_code") == 409:
        raise TelegramBusy(
            "Sofia draait nog in een ander venster. Sluit dat venster eerst. Start daarna opnieuw."
        )
    if not data.get("ok"):
        raise SetupAbort(f"Telegram gaf een foutmelding: {data.get('description', response.status_code)}")
    return data["result"]


def drop_pending(token: str) -> None:
    """Throw away START/'hallo'/anything sent during setup, so Sofia never answers setup messages."""
    try:
        telegram_get(token, "deleteWebhook", {"drop_pending_updates": "true"})
    except SetupAbort:
        pass


def check_existing_token(token: str) -> str | None:
    me = telegram_get(token, "getMe")
    return me.get("username", "") if me else None


def step_telegram_token(input_fn: Callable[[str], str]) -> tuple[str, str]:
    heading(1, "Je Telegram-token")
    say("Plak je Telegram-token (de lange code van BotFather). Druk daarna op Enter.")
    say("Plakken: Windows = rechtermuisklik in dit venster. Mac = Cmd+V.")
    for _ in range(5):
        token = pick(TOKEN_SEARCH, ask("Token: ", input_fn))
        clear_screen()
        banner()
        heading(1, "Je Telegram-token")
        if not looks_like_bot_token(token):
            say("   Dat lijkt geen Telegram-token. Het ziet eruit als 1234567890:AAH... (cijfers, dubbele punt, letters).")
            say("   Kopieer het nog een keer uit BotFather en plak het hier.")
            continue
        say(f"   Token ontvangen ({mask(token)}). Ik controleer het...")
        username = check_existing_token(token)
        if username is None:
            say("   Telegram kent dit token niet. Kopieer het nog een keer HELEMAAL uit BotFather en plak het hier.")
            continue
        say(f"   ✓ Gevonden: je bot heet @{username}")
        say()
        return token, username
    raise SetupAbort("Het token werkte niet. Typ in BotFather /token, kies je bot, en gebruik dat nieuwe token.")


def step_find_user_id(token: str, bot_username: str, input_fn: Callable[[str], str]) -> int:
    heading(2, "Wie ben jij?")
    say("Ik moet weten wie de eigenaar is, zodat Sofia alleen met jou praat.")
    say(f"Zoek in Telegram je bot: @{bot_username}")
    say(f"(Of open deze link in je internetprogramma: https://t.me/{bot_username})")
    say("Klik in dat gesprek op START. Zie je geen START? Typ dan: hallo")
    say("Ik wacht hier op je bericht. Dit venster staat even stil. Dat is normaal.")
    say("In Telegram gebeurt nu nog niets. Dat is ook normaal.")
    telegram_get(token, "deleteWebhook", {"drop_pending_updates": "false"})
    offset = 0
    failures = 0
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            updates = telegram_get(
                token, "getUpdates", {"timeout": 25, "offset": offset, "allowed_updates": '["message"]'}, timeout=35
            )
            failures = 0
        except TelegramBusy:
            raise
        except SetupAbort:
            failures += 1  # a short Wi-Fi hiccup shouldn't end the whole setup
            if failures >= 5:
                raise
            time.sleep(5)
            continue
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
                drop_pending(token)
                say(f"   ✓ Jouw Telegram-nummer (ID) is {user['id']}. Alleen jij kunt met Sofia praten.")
                say()
                return int(user["id"])
            say("   Oké, dan wacht ik op een bericht van jou...")
    raise SetupAbort("Ik heb 10 minuten geen bericht ontvangen. Sluit dit venster. Start Sofia opnieuw en klik op START bij je bot.")


# --------------------------------------------------------------------------- OpenAI
def _openai_client(api_key: str) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=60, max_retries=1)


def validate_key(client: Any) -> tuple[bool, set[str] | None]:
    """Returns (key accepted, available model ids or None if the key can't list models)."""
    import openai

    try:
        return True, {m.id for m in client.models.list()}
    except openai.AuthenticationError:
        return False, None
    except openai.APIConnectionError as exc:
        raise SetupAbort("Ik kan OpenAI niet bereiken. Controleer je internetverbinding.") from exc
    except openai.OpenAIError:
        return True, None  # e.g. a restricted key without the "models" permission


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
            raise SetupAbort("OpenAI kent deze sleutel niet. Maak een nieuwe sleutel (handleiding Deel C).") from exc
        except openai.RateLimitError as exc:
            if "quota" in str(exc).lower():
                raise SetupAbort(
                    "Je OpenAI-account heeft geen tegoed. Ga naar platform.openai.com en voeg tegoed toe "
                    "(handleiding Deel C). Een ChatGPT Plus-abonnement telt hier niet mee. "
                    "Wacht daarna 5 minuten en start opnieuw."
                ) from exc
            return False, None, "het is nu te druk bij OpenAI"
        except openai.BadRequestError as exc:
            if effort and "reasoning" in str(exc).lower():
                continue  # this model doesn't take a reasoning setting: try without
            return False, None, "werkt niet met jouw account"
        except (openai.NotFoundError, openai.PermissionDeniedError) as exc:
            if "verif" in str(exc).lower():
                return False, None, "werkt pas als je account geverifieerd is"
            return False, None, "werkt niet met jouw account"
        except openai.APIConnectionError as exc:
            raise SetupAbort("Ik kan OpenAI niet bereiken. Controleer je internetverbinding.") from exc
        except openai.OpenAIError:
            return False, None, "werkt niet met jouw account"
    return False, None, "werkt niet met jouw account"


def ask_openai_key(input_fn: Callable[[str], str]) -> tuple[str, Any, set[str] | None]:
    heading(3, "Je OpenAI-sleutel")
    say("Plak je OpenAI-sleutel (begint met sk-). Druk daarna op Enter.")
    for _ in range(5):
        key = pick(KEY_SEARCH, ask("Sleutel: ", input_fn))
        clear_screen()
        banner()
        heading(3, "Je OpenAI-sleutel")
        if not looks_like_openai_key(key):
            say("   Dat lijkt geen OpenAI-sleutel. Hij begint met sk- en is heel lang. Plak hem nog een keer.")
            continue
        say(f"   Sleutel ontvangen ({mask(key)}). Ik controleer hem...")
        client = _openai_client(key)
        accepted, available = validate_key(client)
        if not accepted:
            say("   OpenAI kent deze sleutel niet. Kopieer hem nog een keer HELEMAAL en plak hem hier.")
            continue
        return key, client, available
    raise SetupAbort("Geen werkende sleutel. Maak een nieuwe sleutel (handleiding Deel C) en start opnieuw.")


def choose_models(client: Any, available: set[str] | None) -> dict[str, str]:
    say("   Even testen welke AI-versie (model) jouw account mag gebruiken. Dit kan een halve minuut duren...")
    chat_model, effort = None, None
    for model in candidate_chat_models(available):
        works, effort, problem = test_chat_model(client, model)
        if works:
            chat_model = model
            break
        say(f"   - {model}: {problem}. Geen probleem, ik probeer de volgende...")
    if chat_model is None:
        raise SetupAbort(
            "Geen enkele AI-versie werkte met deze sleutel. Controleer of je tegoed hebt. Kijk ook of je je "
            "OpenAI-account moet verifiëren (handleiding: Lukt het niet?)."
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
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": chat_model,
        "LLM_REASONING_EFFORT": effort or "",
        "UTILITY_MODEL": utility,
        "EMBEDDING_MODEL": embedding,
        "TRANSCRIPTION_MODEL": transcription,
    }


# --------------------------------------------------------------------------- private files
def open_folder(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
    except OSError:
        pass


def fix_private_files() -> list[str]:
    """Move misnamed or misplaced private files into persona/. Returns names still missing."""
    folders = [PERSONA_DIR, ROOT, Path.home() / "Downloads"]
    missing = []
    for name in PRIVATE_FILES:
        target = PERSONA_DIR / name
        if target.exists():
            continue
        found = find_misnamed(name, folders)
        if found is not None:
            PERSONA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(found), str(target))
            say(f"   ✓ {found.name} gevonden en neergezet als persona/{name}")
        else:
            missing.append(name)
    return missing


def check_private_files(input_fn: Callable[[str], str], interactive: bool) -> None:
    missing = fix_private_files()
    if missing and interactive:
        say("   Let op: deze privé-bestanden ontbreken nog:")
        for name in missing:
            say(f"     - {name}")
        say("   Ik open nu de map 'persona'. Zet de bestanden daarin (zie handleiding, Deel E).")
        open_folder(PERSONA_DIR)
        ask("   Klaar? Druk op Enter. (Wil je zonder verder? Druk ook gewoon op Enter.) ", input_fn)
        missing = fix_private_files()
    if not missing:
        say("   ✓ Je privé-bestanden staan op hun plek.")
    else:
        say("   Sofia start zonder je privé-bestanden. Dat kan; je kunt ze later toevoegen (handleiding, Deel E).")


# --------------------------------------------------------------------------- main
def run(input_fn: Callable[[str], str] = input, *, interactive: bool | None = None) -> int:
    if interactive is None:
        interactive = sys.stdin.isatty()
    banner()
    say("Ik stel je 3 vragen. Na elke vraag controleer ik meteen of het klopt.")
    say()
    token = ""
    try:
        existing = parse_env(ENV_PATH.read_text(encoding="utf-8")) if ENV_PATH.exists() else {}
        if existing and not ask_yes_no("Er zijn al instellingen. Opnieuw instellen?", True, input_fn):
            say("Niets veranderd.")
            return 0

        # Telegram (questions 1 and 2) — can be kept when redoing the setup.
        token, bot_username, user_id = "", "", 0
        old_token, old_id = existing.get("TELEGRAM_BOT_TOKEN", ""), existing.get("ALLOWED_TELEGRAM_USER_ID", "")
        if old_token and old_id.isdigit() and ask_yes_no("Je Telegram-instellingen hetzelfde laten?", True, input_fn):
            username = check_existing_token(old_token)
            if username:
                token, bot_username, user_id = old_token, username, int(old_id)
                say(f"   ✓ Telegram blijft hetzelfde (@{username}).")
                say()
            else:
                say("   Het oude token werkt niet meer. We doen het opnieuw.")
        if not token:
            token, bot_username = step_telegram_token(input_fn)
            user_id = step_find_user_id(token, bot_username, input_fn)

        # OpenAI (question 3) — the key can be kept; the model check always runs again.
        old_key = existing.get("OPENAI_API_KEY", "")
        client, available, key = None, None, ""
        if old_key and ask_yes_no("Je OpenAI-sleutel hetzelfde laten?", True, input_fn):
            heading(3, "Je OpenAI-sleutel")
            client = _openai_client(old_key)
            accepted, available = validate_key(client)
            if accepted:
                key = old_key
            else:
                say("   De oude sleutel werkt niet meer. Plak een nieuwe.")
        if not key:
            key, client, available = ask_openai_key(input_fn)
        model_values = choose_models(client, available)

        say("Alles klopt. Ik sla het nu op...")
        drop_pending(token)  # anything typed to the bot during setup is not a conversation
        values = {
            **existing,
            "TELEGRAM_BOT_TOKEN": token,
            "ALLOWED_TELEGRAM_USER_ID": str(user_id),
            "OPENAI_API_KEY": key,
            **model_values,
        }
        template = TEMPLATE_PATH.read_text(encoding="utf-8") if TEMPLATE_PATH.exists() else ""
        if ENV_PATH.exists():
            shutil.copyfile(ENV_PATH, ENV_PATH.with_name(".env.backup"))
        ENV_PATH.write_text(render_env(template, values), encoding="utf-8")
        say("   ✓ Instellingen opgeslagen (in het bestand .env — deel dat met niemand).")
        check_private_files(input_fn, interactive)
        say()
        say("Klaar! Sofia start nu.")
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

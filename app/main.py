"""Entry point.

python -m app              run the bot
python -m app --check      validate configuration and persona files, then exit
python -m app --init-db    create/upgrade the database, then exit
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.companion.engine import CompanionEngine
from app.companion.persona import PersonaError, load_persona_bundle
from app.companion.prompts import build_instructions
from app.config import ConfigError, Settings
from app.controls import ControlService
from app.llm.provider import build_provider
from app.memory.database import Database
from app.memory.store import MemoryStore
from app.memory.text import estimate_tokens
from app.telegram_bot import SofiaBot, build_setup_app
from app.utils.logging import get_logger, setup_logging

log = get_logger("app")


def _init_db(settings: Settings) -> None:
    async def _run() -> None:
        db = Database(settings.database_path)
        await db.connect()
        await db.close()

    asyncio.run(_run())
    print(f"Database ready at {settings.database_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sofia", description="Private Telegram AI companion")
    parser.add_argument("--setup", action="store_true", help="interactive first-time setup (writes .env)")
    parser.add_argument("--check", action="store_true", help="validate config and persona files, then exit")
    parser.add_argument("--init-db", action="store_true", help="initialize the database, then exit")
    args = parser.parse_args(argv)

    if args.setup:
        from app.setup_wizard import run as run_setup

        return run_setup()

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.log_level, settings.log_format)

    if settings.setup_mode:
        log.warning("ALLOWED_TELEGRAM_USER_ID is not set: running in SETUP MODE (replies with user ids only)")
        if args.check or args.init_db:
            print("Setup mode: set ALLOWED_TELEGRAM_USER_ID first.")
            return 0
        build_setup_app(settings).run_polling(drop_pending_updates=True)
        return 0

    try:
        persona, profile, files = load_persona_bundle(settings.persona_dir)
    except PersonaError as exc:
        print(f"Persona error: {exc}", file=sys.stderr)
        return 2
    log.info("persona loaded", extra={"files": ", ".join(str(f.name) for f in files)})

    if args.check:
        instructions = build_instructions(persona, profile)
        print("Configuration OK")
        print(f"  model:            {settings.llm_model} via {settings.llm_provider}")
        print(f"  utility model:    {settings.effective_utility_model}")
        print(f"  embeddings:       {settings.embedding_model or 'off (lexical retrieval only)'}")
        print(f"  transcription:    {settings.transcription_model or 'off'}")
        print(f"  database:         {settings.database_path}")
        print(f"  persona files:    {', '.join(f.name for f in files)}")
        print(f"  private dynamics: {', '.join(d.id for d in profile.dynamics) or 'none'}")
        print(f"  static prompt:    ~{estimate_tokens(instructions)} tokens (cached by the provider)")
        return 0
    if args.init_db:
        _init_db(settings)
        return 0

    db = Database(settings.database_path)
    store = MemoryStore(db)
    provider = build_provider(settings)
    engine = CompanionEngine(settings, store, provider, persona, profile)
    controls = ControlService(settings, store, provider)
    bot = SofiaBot(settings, db=db, store=store, provider=provider, engine=engine, controls=controls)
    if settings.keep_awake:
        from app.utils.keepawake import keep_awake

        keep_awake()
    bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

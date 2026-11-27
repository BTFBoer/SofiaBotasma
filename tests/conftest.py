from __future__ import annotations

import random
from pathlib import Path

import pytest

from app.companion.engine import CompanionEngine
from app.companion.persona import load_persona_bundle
from app.config import Settings
from app.controls import ControlService
from app.memory.database import Database
from app.memory.store import MemoryStore
from tests.fakes import Clock, FakeProvider

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ID = 424242


def make_settings(tmp_path: Path, **overrides: str) -> Settings:
    env = {
        "TELEGRAM_BOT_TOKEN": "123:test",
        "ALLOWED_TELEGRAM_USER_ID": str(ALLOWED_ID),
        "OPENAI_API_KEY": "sk-test",
        "LLM_MODEL": "test-model",
        "DATABASE_PATH": str(tmp_path / "sofia.db"),
        "PERSONA_DIR": str(ROOT / "persona"),
        "TIMEZONE": "Europe/Amsterdam",
        "DEBOUNCE_SECONDS": "0",
        "STYLE_GUARD_REGENERATE": "true",
    }
    env.update(overrides)
    return Settings.from_env(env)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def store(db: Database, clock: Clock) -> MemoryStore:
    return MemoryStore(db, clock=clock)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def engine(settings: Settings, store: MemoryStore, provider: FakeProvider, clock: Clock) -> CompanionEngine:
    persona, profile, _ = load_persona_bundle(settings.persona_dir)
    return CompanionEngine(settings, store, provider, persona, profile, clock=clock, rng=random.Random(7))


@pytest.fixture
def controls(settings: Settings, store: MemoryStore, provider: FakeProvider, clock: Clock) -> ControlService:
    return ControlService(settings, store, provider, clock=clock)

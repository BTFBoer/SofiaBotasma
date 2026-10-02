"""Configuration loaded from environment variables (optionally via a .env file).

Model names are never hard-coded in the application: every model is chosen
through an environment variable. Optional features (embeddings, voice
transcription) switch themselves off when their model variable is empty.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get(env: dict[str, str], key: str, default: str | None = None) -> str | None:
    value = env.get(key)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _get_bool(env: dict[str, str], key: str, default: bool) -> bool:
    raw = _get(env, key)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be true/false, got {raw!r}")


def _get_int(env: dict[str, str], key: str, default: int | None) -> int | None:
    raw = _get(env, key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _get_float(env: dict[str, str], key: str, default: float | None) -> float | None:
    raw = _get(env, key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _parse_hhmm(value: str, key: str) -> tuple[int, int]:
    try:
        hours, minutes = value.split(":")
        h, m = int(hours), int(minutes)
    except ValueError as exc:
        raise ConfigError(f"{key} must look like HH:MM, got {value!r}") from exc
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ConfigError(f"{key} out of range: {value!r}")
    return h, m


@dataclass(frozen=True)
class Settings:
    # --- Telegram -----------------------------------------------------------
    telegram_bot_token: str
    # None => setup mode: the bot only tells whoever writes to it their numeric id.
    allowed_telegram_user_id: int | None
    unauthorized_reply: str | None = None
    telegram_mode: str = "polling"  # polling | webhook
    webhook_url: str | None = None
    webhook_listen: str = "0.0.0.0"
    webhook_port: int = 8443
    webhook_secret: str | None = None

    # --- LLM ----------------------------------------------------------------
    llm_provider: str = "openai"  # openai (Responses API) | openai_compatible (Chat Completions)
    openai_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str | None = None
    llm_reasoning_effort: str | None = None
    llm_temperature: float | None = None
    llm_verbosity: str | None = None
    llm_max_output_tokens: int = 3000
    llm_timeout_seconds: float = 90.0
    llm_json_mode: str = "json_schema"  # only for openai_compatible: json_schema | json_object
    utility_model: str | None = None  # summaries / consolidation; defaults to llm_model
    embedding_model: str | None = None
    transcription_model: str | None = None
    vision_enabled: bool = True
    image_detail: str = "auto"

    # --- Behaviour ------------------------------------------------------------
    timezone: str = "Europe/Amsterdam"
    proactive_default: bool = False
    proactive_max_per_day: int = 2
    quiet_hours_start: tuple[int, int] = (23, 30)
    quiet_hours_end: tuple[int, int] = (8, 30)
    debounce_seconds: float = 2.2
    debounce_max_seconds: float = 9.0
    recent_messages_max: int = 40
    recent_tokens_budget: int = 3500
    style_guard_regenerate: bool = True

    # --- Storage ------------------------------------------------------------
    database_path: Path = field(default_factory=lambda: Path("./data/sofia.db"))
    persona_dir: Path = field(default_factory=lambda: Path("./persona"))
    keep_images: bool = False
    image_dir: Path = field(default_factory=lambda: Path("./data/images"))
    heartbeat_path: Path = field(default_factory=lambda: Path("./data/heartbeat"))

    # --- Logging ------------------------------------------------------------
    log_level: str = "INFO"
    log_format: str = "text"  # text | json

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def setup_mode(self) -> bool:
        return self.allowed_telegram_user_id is None

    @property
    def effective_utility_model(self) -> str:
        return self.utility_model or self.llm_model

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, load_dotenv_file: bool = True) -> Settings:
        if env is None:
            if load_dotenv_file:
                load_dotenv(override=False)
            env = dict(os.environ)

        token = _get(env, "TELEGRAM_BOT_TOKEN")
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required (get one from @BotFather).")

        allowed = _get_int(env, "ALLOWED_TELEGRAM_USER_ID", None)
        if allowed is not None and allowed <= 0:
            allowed = None

        provider = (_get(env, "LLM_PROVIDER", "openai") or "openai").lower()
        if provider not in {"openai", "openai_compatible"}:
            raise ConfigError("LLM_PROVIDER must be 'openai' or 'openai_compatible'.")

        api_key = _get(env, "OPENAI_API_KEY", "") or ""
        model = _get(env, "LLM_MODEL", "") or ""
        if allowed is not None:
            # Outside setup mode we really need an LLM.
            if not api_key:
                raise ConfigError("OPENAI_API_KEY is required.")
            if not model:
                raise ConfigError("LLM_MODEL is required (see .env.example for suggestions).")

        timezone = _get(env, "TIMEZONE", "Europe/Amsterdam") or "Europe/Amsterdam"
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unknown TIMEZONE {timezone!r}") from exc

        mode = (_get(env, "TELEGRAM_MODE", "polling") or "polling").lower()
        if mode not in {"polling", "webhook"}:
            raise ConfigError("TELEGRAM_MODE must be 'polling' or 'webhook'.")
        webhook_url = _get(env, "WEBHOOK_URL")
        if mode == "webhook" and not webhook_url:
            raise ConfigError("WEBHOOK_URL is required when TELEGRAM_MODE=webhook.")

        reasoning = _get(env, "LLM_REASONING_EFFORT")
        if reasoning is not None:
            reasoning = reasoning.lower()
        verbosity = _get(env, "LLM_VERBOSITY")
        if verbosity is not None and verbosity.lower() not in {"low", "medium", "high"}:
            raise ConfigError("LLM_VERBOSITY must be low, medium or high.")

        json_mode = (_get(env, "LLM_JSON_MODE", "json_schema") or "json_schema").lower()
        if json_mode not in {"json_schema", "json_object"}:
            raise ConfigError("LLM_JSON_MODE must be json_schema or json_object.")

        image_detail = (_get(env, "IMAGE_DETAIL", "auto") or "auto").lower()
        if image_detail not in {"low", "high", "auto", "original"}:
            raise ConfigError("IMAGE_DETAIL must be low, high, auto or original.")

        log_format = (_get(env, "LOG_FORMAT", "text") or "text").lower()
        if log_format not in {"text", "json"}:
            raise ConfigError("LOG_FORMAT must be text or json.")

        database_path = Path(_get(env, "DATABASE_PATH", "./data/sofia.db") or "./data/sofia.db")
        data_dir = database_path.parent

        return cls(
            telegram_bot_token=token,
            allowed_telegram_user_id=allowed,
            unauthorized_reply=_get(env, "UNAUTHORIZED_REPLY"),
            telegram_mode=mode,
            webhook_url=webhook_url,
            webhook_listen=_get(env, "WEBHOOK_LISTEN", "0.0.0.0") or "0.0.0.0",
            webhook_port=_get_int(env, "WEBHOOK_PORT", 8443) or 8443,
            webhook_secret=_get(env, "WEBHOOK_SECRET"),
            llm_provider=provider,
            openai_api_key=api_key,
            llm_model=model,
            llm_base_url=_get(env, "LLM_BASE_URL"),
            llm_reasoning_effort=reasoning,
            llm_temperature=_get_float(env, "LLM_TEMPERATURE", None),
            llm_verbosity=verbosity.lower() if verbosity else None,
            llm_max_output_tokens=_get_int(env, "LLM_MAX_OUTPUT_TOKENS", 3000) or 3000,
            llm_timeout_seconds=_get_float(env, "LLM_TIMEOUT_SECONDS", 90.0) or 90.0,
            llm_json_mode=json_mode,
            utility_model=_get(env, "UTILITY_MODEL"),
            embedding_model=_get(env, "EMBEDDING_MODEL"),
            transcription_model=_get(env, "TRANSCRIPTION_MODEL"),
            vision_enabled=_get_bool(env, "VISION_ENABLED", True),
            image_detail=image_detail,
            timezone=timezone,
            proactive_default=_get_bool(env, "PROACTIVE_DEFAULT", False),
            proactive_max_per_day=max(0, min(2, _get_int(env, "PROACTIVE_MAX_PER_DAY", 2) or 0)),
            quiet_hours_start=_parse_hhmm(_get(env, "QUIET_HOURS_START", "23:30") or "23:30", "QUIET_HOURS_START"),
            quiet_hours_end=_parse_hhmm(_get(env, "QUIET_HOURS_END", "08:30") or "08:30", "QUIET_HOURS_END"),
            debounce_seconds=_get_float(env, "DEBOUNCE_SECONDS", 2.2) or 0.0,
            debounce_max_seconds=_get_float(env, "DEBOUNCE_MAX_SECONDS", 9.0) or 9.0,
            recent_messages_max=_get_int(env, "RECENT_MESSAGES_MAX", 40) or 40,
            recent_tokens_budget=_get_int(env, "RECENT_TOKENS_BUDGET", 3500) or 3500,
            style_guard_regenerate=_get_bool(env, "STYLE_GUARD_REGENERATE", True),
            database_path=database_path,
            persona_dir=Path(_get(env, "PERSONA_DIR", "./persona") or "./persona"),
            keep_images=_get_bool(env, "KEEP_IMAGES", False),
            image_dir=Path(_get(env, "IMAGE_DIR", str(data_dir / "images")) or str(data_dir / "images")),
            heartbeat_path=Path(
                _get(env, "HEARTBEAT_PATH", str(data_dir / "heartbeat")) or str(data_dir / "heartbeat")
            ),
            log_level=(_get(env, "LOG_LEVEL", "INFO") or "INFO").upper(),
            log_format=log_format,
        )

"""Provider-agnostic LLM interface.

The companion engine only talks to `LLMProvider`. Swapping providers means
writing one class; nothing else in the application knows which API is used.
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeVar

from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config import Settings

log = get_logger(__name__)
T = TypeVar("T")

Role = Literal["developer", "user", "assistant"]


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime: str = "image/jpeg"


@dataclass
class ChatMessage:
    role: Role
    text: str
    images: list[ImagePart] = field(default_factory=list)


@dataclass
class LLMResult:
    text: str
    refusal: str | None = None
    incomplete: bool = False
    model: str = ""
    elapsed: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)


class LLMError(Exception):
    """Non-retryable provider error (bad request, auth, ...)."""


class LLMTransientError(LLMError):
    """Retryable error (rate limit, timeout, 5xx, connection)."""


class LLMProvider(ABC):
    name: str = "base"
    supports_vision: bool = True

    @abstractmethod
    async def generate_json(
        self,
        *,
        instructions: str,
        messages: list[ChatMessage],
        schema: dict,
        schema_name: str,
        model: str | None = None,
        max_output_tokens: int | None = None,
        cache_key: str | None = None,
    ) -> LLMResult:
        """Generate a JSON document matching `schema`. Returns raw text; parsing happens upstream."""

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Return one embedding per text, or None if embeddings are unavailable."""
        return None

    async def transcribe(self, audio: bytes, filename: str) -> str | None:
        """Speech-to-text, or None if unavailable."""
        return None

    @property
    def can_embed(self) -> bool:
        return False

    @property
    def can_transcribe(self) -> bool:
        return False

    async def aclose(self) -> None:
        return None


async def with_retries(
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 12.0,
    what: str = "llm call",
) -> T:
    """Exponential backoff with jitter for transient errors only."""
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except LLMTransientError as exc:
            if attempt >= attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1))) * random.uniform(0.7, 1.3)
            log.warning("%s failed (attempt %d/%d), retrying in %.1fs: %s", what, attempt, attempts, delay, exc)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compatible":
        from app.llm.openai_compat_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(settings)
    from app.llm.openai_provider import OpenAIResponsesProvider

    return OpenAIResponsesProvider(settings)

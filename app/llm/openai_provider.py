"""OpenAI provider built on the Responses API.

Design choices:
- Stateless calls with `store=False`. The local SQLite database is the single
  source of truth for history and memory, so we deliberately do not use
  server-side state (`previous_response_id` / the Conversations API): that
  would duplicate intimate conversation data on the provider's side for no
  benefit, and our context is re-assembled from memory every turn anyway.
- Structured Outputs (`text.format = json_schema`, strict) for the turn JSON.
- The static system prompt goes into `instructions` and stays byte-identical
  between calls, so OpenAI's automatic prompt caching can reuse it.
"""

from __future__ import annotations

import base64
import hashlib
import time
from typing import TYPE_CHECKING, Any

import openai
from openai import AsyncOpenAI

from app.llm.provider import (
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMTransientError,
    with_retries,
)
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config import Settings

log = get_logger(__name__)


def map_openai_error(exc: Exception) -> LLMError:
    if isinstance(
        exc, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError)
    ):
        return LLMTransientError(f"{type(exc).__name__}: {exc}")
    if isinstance(exc, openai.APIStatusError) and (exc.status_code >= 500 or exc.status_code in (408, 409, 429)):
        return LLMTransientError(f"{type(exc).__name__}: {exc}")
    return LLMError(f"{type(exc).__name__}: {exc}")


class OpenAIResponsesProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # we retry ourselves with backoff
        )
        self.supports_vision = settings.vision_enabled
        user_id = str(settings.allowed_telegram_user_id or "setup")
        # OpenAI recommends a stable, privacy-preserving end-user identifier.
        self._safety_identifier = "sofia-" + hashlib.sha256(user_id.encode()).hexdigest()[:32]

    # ------------------------------------------------------------------ helpers
    def _convert(self, message: ChatMessage) -> dict[str, Any]:
        if message.role == "assistant":
            return {"role": "assistant", "content": message.text}
        if not message.images:
            return {"role": message.role, "content": message.text}
        parts: list[dict[str, Any]] = []
        if message.text:
            parts.append({"type": "input_text", "text": message.text})
        for image in message.images:
            b64 = base64.b64encode(image.data).decode("ascii")
            parts.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{image.mime};base64,{b64}",
                    "detail": self.settings.image_detail,
                }
            )
        return {"role": message.role, "content": parts}

    @staticmethod
    def _extract_refusal(response: Any) -> str | None:
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", None) or []:
                if getattr(content, "type", None) == "refusal":
                    return getattr(content, "refusal", None) or "refused"
        return None

    # ------------------------------------------------------------------ API
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
        text_config: dict[str, Any] = {
            "format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}
        }
        if self.settings.llm_verbosity:
            text_config["verbosity"] = self.settings.llm_verbosity

        kwargs: dict[str, Any] = {
            "model": model or self.settings.llm_model,
            "instructions": instructions,
            "input": [self._convert(m) for m in messages],
            "text": text_config,
            "store": False,
            "max_output_tokens": max_output_tokens or self.settings.llm_max_output_tokens,
            "safety_identifier": self._safety_identifier,
        }
        if cache_key:
            kwargs["prompt_cache_key"] = cache_key
        if self.settings.llm_reasoning_effort:
            kwargs["reasoning"] = {"effort": self.settings.llm_reasoning_effort}
        if self.settings.llm_temperature is not None:
            kwargs["temperature"] = self.settings.llm_temperature

        async def _call() -> Any:
            try:
                return await self.client.responses.create(**kwargs)
            except openai.OpenAIError as exc:
                raise map_openai_error(exc) from exc

        started = time.monotonic()
        response = await with_retries(_call, what="responses.create")
        elapsed = time.monotonic() - started

        usage: dict[str, int] = {}
        if getattr(response, "usage", None) is not None:
            u = response.usage
            usage = {
                "input": int(getattr(u, "input_tokens", 0) or 0),
                "output": int(getattr(u, "output_tokens", 0) or 0),
            }
            details = getattr(u, "input_tokens_details", None)
            if details is not None:
                usage["cached"] = int(getattr(details, "cached_tokens", 0) or 0)

        incomplete = getattr(response, "status", None) == "incomplete"
        if incomplete:
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            log.warning("response incomplete", extra={"reason": reason})

        log.info(
            "llm call",
            extra={"model": kwargs["model"], "schema": schema_name, "elapsed": round(elapsed, 2), **usage},
        )
        return LLMResult(
            text=response.output_text or "",
            refusal=self._extract_refusal(response),
            incomplete=incomplete,
            model=kwargs["model"],
            elapsed=elapsed,
            usage=usage,
        )

    @property
    def can_embed(self) -> bool:
        return bool(self.settings.embedding_model)

    @property
    def can_transcribe(self) -> bool:
        return bool(self.settings.transcription_model)

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.settings.embedding_model or not texts:
            return None

        async def _call() -> Any:
            try:
                return await self.client.embeddings.create(model=self.settings.embedding_model, input=texts)
            except openai.OpenAIError as exc:
                raise map_openai_error(exc) from exc

        try:
            result = await with_retries(_call, attempts=2, what="embeddings.create")
        except LLMError as exc:
            log.warning("embedding failed; falling back to lexical retrieval: %s", exc)
            return None
        return [list(item.embedding) for item in result.data]

    async def transcribe(self, audio: bytes, filename: str) -> str | None:
        if not self.settings.transcription_model:
            return None

        async def _call() -> Any:
            try:
                return await self.client.audio.transcriptions.create(
                    model=self.settings.transcription_model, file=(filename, audio)
                )
            except openai.OpenAIError as exc:
                raise map_openai_error(exc) from exc

        try:
            result = await with_retries(_call, attempts=2, what="audio.transcriptions.create")
        except LLMError as exc:
            log.warning("transcription failed: %s", exc)
            return None
        text = getattr(result, "text", None)
        return text.strip() if isinstance(text, str) else None

    async def aclose(self) -> None:
        await self.client.close()

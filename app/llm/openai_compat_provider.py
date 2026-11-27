"""Provider for any OpenAI-compatible Chat Completions endpoint.

Use this when you point LLM_BASE_URL at another provider or a local server
(OpenRouter, vLLM, LM Studio, Ollama's OpenAI endpoint, ...). Many of those
implement Chat Completions but not the Responses API. Set
LLM_JSON_MODE=json_object if the endpoint doesn't support json_schema.
"""

from __future__ import annotations

import base64
import json
import time
from typing import TYPE_CHECKING, Any

import openai
from openai import AsyncOpenAI

from app.llm.openai_provider import map_openai_error
from app.llm.provider import ChatMessage, LLMError, LLMProvider, LLMResult, with_retries
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config import Settings

log = get_logger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        self.supports_vision = settings.vision_enabled

    def _convert(self, message: ChatMessage) -> dict[str, Any]:
        # Most compatible servers don't know the "developer" role.
        role = "system" if message.role == "developer" else message.role
        if not message.images:
            return {"role": role, "content": message.text}
        parts: list[dict[str, Any]] = []
        if message.text:
            parts.append({"type": "text", "text": message.text})
        for image in message.images:
            b64 = base64.b64encode(image.data).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{image.mime};base64,{b64}"}})
        return {"role": role, "content": parts}

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
        system = instructions
        if self.settings.llm_json_mode == "json_object":
            response_format: dict[str, Any] = {"type": "json_object"}
            system += "\n\nRespond with a single JSON object that follows this JSON schema exactly:\n" + json.dumps(
                schema, ensure_ascii=False
            )
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }

        kwargs: dict[str, Any] = {
            "model": model or self.settings.llm_model,
            "messages": [{"role": "system", "content": system}, *[self._convert(m) for m in messages]],
            "response_format": response_format,
            "max_completion_tokens": max_output_tokens or self.settings.llm_max_output_tokens,
        }
        if self.settings.llm_temperature is not None:
            kwargs["temperature"] = self.settings.llm_temperature
        if self.settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.llm_reasoning_effort

        async def _call() -> Any:
            try:
                return await self.client.chat.completions.create(**kwargs)
            except openai.OpenAIError as exc:
                raise map_openai_error(exc) from exc

        started = time.monotonic()
        response = await with_retries(_call, what="chat.completions.create")
        elapsed = time.monotonic() - started
        if not response.choices:
            raise LLMError("empty choices")
        choice = response.choices[0]
        content = choice.message.content or ""
        refusal = getattr(choice.message, "refusal", None)
        usage = {}
        if response.usage is not None:
            usage = {"input": response.usage.prompt_tokens or 0, "output": response.usage.completion_tokens or 0}
        log.info(
            "llm call", extra={"model": kwargs["model"], "schema": schema_name, "elapsed": round(elapsed, 2), **usage}
        )
        return LLMResult(
            text=content,
            refusal=refusal,
            incomplete=choice.finish_reason == "length",
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
        try:
            result = await self.client.embeddings.create(model=self.settings.embedding_model, input=texts)
        except openai.OpenAIError as exc:
            log.warning("embedding failed; falling back to lexical retrieval: %s", exc)
            return None
        return [list(item.embedding) for item in result.data]

    async def transcribe(self, audio: bytes, filename: str) -> str | None:
        if not self.settings.transcription_model:
            return None
        try:
            result = await self.client.audio.transcriptions.create(
                model=self.settings.transcription_model, file=(filename, audio)
            )
        except openai.OpenAIError as exc:
            log.warning("transcription failed: %s", exc)
            return None
        text = getattr(result, "text", None)
        return text.strip() if isinstance(text, str) else None

    async def aclose(self) -> None:
        await self.client.close()

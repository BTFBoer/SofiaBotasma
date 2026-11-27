"""Test doubles."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.llm.provider import ChatMessage, LLMProvider, LLMResult, LLMTransientError


def turn_json(messages: list[str] | None = None, **overrides: Any) -> str:
    data: dict[str, Any] = {
        "messages": messages if messages is not None else ["morning", "you sound suspiciously awake for this hour"],
        "reaction": None,
        "image_note": None,
        "mood_update": None,
        "relationship_update": {
            "familiarity": 0,
            "trust": 0,
            "affection": 0,
            "attraction": 0,
            "playfulness": 0,
            "emotional_openness": 0,
            "sexual_comfort": 0,
            "irritation": 0,
        },
        "dynamic_note": None,
        "established_dynamics": [],
        "memory_candidates": [],
        "sofia_facts": [],
        "unresolved_threads": [],
        "used_memory_ids": [],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class FakeProvider(LLMProvider):
    """Returns scripted outputs (str, Exception or callable(messages) -> str) in order."""

    name = "fake"

    def __init__(self, outputs: list[Any] | None = None, *, embeddings: bool = False) -> None:
        self.outputs = list(outputs or [])
        self.calls: list[dict[str, Any]] = []
        self._embeddings = embeddings
        self.supports_vision = True

    def queue(self, *outputs: Any) -> None:
        self.outputs.extend(outputs)

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
        self.calls.append({"instructions": instructions, "messages": messages, "schema_name": schema_name})
        if not self.outputs:
            return LLMResult(text=turn_json(), elapsed=0.01)
        item = self.outputs.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(messages)
        if isinstance(item, LLMResult):
            return item
        return LLMResult(text=str(item), elapsed=0.01)

    @property
    def can_embed(self) -> bool:
        return self._embeddings

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self._embeddings:
            return None
        # Deterministic toy embedding: bag of a few keywords.
        vocab = ["techno", "mulero", "levenslang", "olive", "work", "sister", "rice", "music"]
        return [[1.0 if w in t.lower() else 0.0 for w in vocab] + [0.1] for t in texts]


class Clock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 10, 2, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


def transient() -> LLMTransientError:
    return LLMTransientError("rate limited")


Factory = Callable[[], Any]

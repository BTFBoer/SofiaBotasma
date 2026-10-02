"""Structured output contract between the model and the engine.

The JSON schemas are written by hand so they stay inside the subset that
strict Structured Outputs accepts (every property required, nullable via
type unions, no defaults). Parsing is deliberately lenient: values are
clamped, lists truncated, and malformed output is recovered where possible.
Nothing in this module is ever shown to Bram except `messages`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

DIMENSIONS = (
    "familiarity",
    "trust",
    "affection",
    "attraction",
    "playfulness",
    "emotional_openness",
    "sexual_comfort",
    "irritation",
)

# Subset of Telegram's allowed reaction emoji that fits Sofia.
ALLOWED_REACTIONS = (
    "❤",
    "🔥",
    "😁",
    "🤣",
    "👀",
    "🙈",
    "🤨",
    "😐",
    "💋",
    "🥱",
    "😈",
    "🫡",
    "🤔",
    "👍",
    "😭",
    "🗿",
    "💅",
    "😘",
    "🤯",
    "😴",
)

MAX_BUBBLES = 4


# --------------------------------------------------------------------------- JSON schema helpers
def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_NSTR = {"type": ["string", "null"]}
_NUM = {"type": "number"}
_NUDGE = {"type": "integer", "enum": [-2, -1, 0, 1, 2]}

_MEMORY_CANDIDATE = _obj(
    {
        "subject": {"type": "string", "enum": ["bram", "relationship"]},
        "content": _STR,
        "category": _STR,
        "importance": _NUM,
        "confidence": _NUM,
        "event_date": _NSTR,
    }
)
_SOFIA_FACT = _obj({"content": _STR, "category": _STR, "durable": {"type": "boolean"}})
_THREAD = _obj(
    {
        "action": {"type": "string", "enum": ["open", "resolve"]},
        "id": {"type": ["integer", "null"]},
        "content": _STR,
        "due_date": _NSTR,
    }
)

_TURN_PROPERTIES: dict[str, Any] = {
    "messages": {"type": "array", "items": _STR},
    "reaction": {"anyOf": [{"type": "string", "enum": list(ALLOWED_REACTIONS)}, {"type": "null"}]},
    "image_note": _NSTR,
    "mood_update": {
        "anyOf": [
            _obj({"label": _STR, "intensity": _NUM, "cause": _STR}),
            {"type": "null"},
        ]
    },
    "relationship_update": _obj({dim: _NUDGE for dim in DIMENSIONS}),
    "dynamic_note": _NSTR,
    "established_dynamics": {"type": "array", "items": _STR},
    "memory_candidates": {"type": "array", "items": _MEMORY_CANDIDATE},
    "sofia_facts": {"type": "array", "items": _SOFIA_FACT},
    "unresolved_threads": {"type": "array", "items": _THREAD},
    "used_memory_ids": {"type": "array", "items": {"type": "integer"}},
}

TURN_SCHEMA: dict[str, Any] = _obj(_TURN_PROPERTIES)
PROACTIVE_SCHEMA: dict[str, Any] = _obj({"send": {"type": "boolean"}, **_TURN_PROPERTIES})

SUMMARY_SCHEMA: dict[str, Any] = _obj(
    {
        "episodes": {
            "type": "array",
            "items": _obj(
                {
                    "title": _STR,
                    "summary": _STR,
                    "tone": _STR,
                    "importance": _NUM,
                    "tags": {"type": "array", "items": _STR},
                }
            ),
        },
        "memory_candidates": {"type": "array", "items": _MEMORY_CANDIDATE},
        "sofia_facts": {"type": "array", "items": _SOFIA_FACT},
        "resolved_thread_ids": {"type": "array", "items": {"type": "integer"}},
    }
)

CONSOLIDATION_SCHEMA: dict[str, Any] = _obj(
    {
        "merges": {
            "type": "array",
            "items": _obj(
                {"ids": {"type": "array", "items": {"type": "integer"}}, "content": _STR, "importance": _NUM}
            ),
        },
        "retire_ids": {"type": "array", "items": {"type": "integer"}},
    }
)


# --------------------------------------------------------------------------- pydantic models
def _clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


class MoodUpdate(BaseModel):
    label: str = Field(max_length=80)
    intensity: float = 0.5
    cause: str = ""

    @field_validator("intensity", mode="before")
    @classmethod
    def _intensity(cls, v: Any) -> float:
        return _clamp01(v)

    @field_validator("label", "cause", mode="before")
    @classmethod
    def _short(cls, v: Any) -> str:
        return str(v or "").strip()[:200]


class MemoryCandidate(BaseModel):
    subject: str = "bram"
    content: str
    category: str = "other"
    importance: float = 0.5
    confidence: float = 0.7
    event_date: str | None = None

    @field_validator("importance", "confidence", mode="before")
    @classmethod
    def _unit(cls, v: Any) -> float:
        return _clamp01(v)

    @field_validator("subject", mode="before")
    @classmethod
    def _subject(cls, v: Any) -> str:
        v = str(v or "bram").lower().strip()
        return v if v in {"bram", "relationship"} else "bram"


class SofiaFact(BaseModel):
    content: str
    category: str = "other"
    durable: bool = True


class ThreadUpdate(BaseModel):
    action: str = "open"
    id: int | None = None
    content: str = ""
    due_date: str | None = None

    @field_validator("action", mode="before")
    @classmethod
    def _action(cls, v: Any) -> str:
        v = str(v or "open").lower()
        return v if v in {"open", "resolve"} else "open"


class RelationshipNudges(BaseModel):
    familiarity: int = 0
    trust: int = 0
    affection: int = 0
    attraction: int = 0
    playfulness: int = 0
    emotional_openness: int = 0
    sexual_comfort: int = 0
    irritation: int = 0

    @field_validator(*DIMENSIONS, mode="before")
    @classmethod
    def _nudge(cls, v: Any) -> int:
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            return 0
        return max(-2, min(2, n))

    def as_dict(self) -> dict[str, int]:
        return {dim: getattr(self, dim) for dim in DIMENSIONS}


class TurnOutput(BaseModel):
    messages: list[str] = Field(default_factory=list)
    reaction: str | None = None
    image_note: str | None = None
    mood_update: MoodUpdate | None = None
    relationship_update: RelationshipNudges = Field(default_factory=RelationshipNudges)
    dynamic_note: str | None = None
    established_dynamics: list[str] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    sofia_facts: list[SofiaFact] = Field(default_factory=list)
    unresolved_threads: list[ThreadUpdate] = Field(default_factory=list)
    used_memory_ids: list[int] = Field(default_factory=list)
    send: bool = True  # only meaningful for proactive turns

    @field_validator("messages", mode="before")
    @classmethod
    def _messages(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        cleaned = [str(m).strip() for m in v if str(m or "").strip()]
        if len(cleaned) > MAX_BUBBLES:
            cleaned = cleaned[: MAX_BUBBLES - 1] + ["\n".join(cleaned[MAX_BUBBLES - 1 :])]
        return cleaned

    @field_validator("reaction", mode="before")
    @classmethod
    def _reaction(cls, v: Any) -> str | None:
        if not v:
            return None
        v = str(v).replace("️", "").strip()
        return v if v in ALLOWED_REACTIONS else None

    @field_validator("relationship_update", mode="before")
    @classmethod
    def _nudges(cls, v: Any) -> Any:
        return v if isinstance(v, dict) else {}

    @field_validator("memory_candidates", "sofia_facts", "unresolved_threads", mode="before")
    @classmethod
    def _cap_lists(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return []
        return v[:8]

    @field_validator("used_memory_ids", mode="before")
    @classmethod
    def _ids(cls, v: Any) -> list[int]:
        out: list[int] = []
        for item in v or []:
            try:
                out.append(int(str(item).lstrip("MmEe")))
            except (TypeError, ValueError):
                continue
        return out[:20]

    @field_validator("established_dynamics", mode="before")
    @classmethod
    def _dyn(cls, v: Any) -> list[str]:
        return [str(x).strip().lower() for x in (v or []) if str(x).strip()][:5]


class SummaryEpisode(BaseModel):
    title: str
    summary: str
    tone: str = ""
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)

    @field_validator("importance", mode="before")
    @classmethod
    def _unit(cls, v: Any) -> float:
        return _clamp01(v)


class SummaryOutput(BaseModel):
    episodes: list[SummaryEpisode] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    sofia_facts: list[SofiaFact] = Field(default_factory=list)
    resolved_thread_ids: list[int] = Field(default_factory=list)


class ConsolidationMerge(BaseModel):
    ids: list[int]
    content: str
    importance: float = 0.5

    @field_validator("importance", mode="before")
    @classmethod
    def _unit(cls, v: Any) -> float:
        return _clamp01(v)


class ConsolidationOutput(BaseModel):
    merges: list[ConsolidationMerge] = Field(default_factory=list)
    retire_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- parsing / recovery
class ParseError(ValueError):
    pass


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_MESSAGES_RE = re.compile(r'"messages"\s*:\s*\[(.*?)\]', re.DOTALL)
_JSON_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _load_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    fence = _FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _salvage_messages(raw: str) -> list[str]:
    """Pull the messages array out of truncated/broken JSON."""
    match = _MESSAGES_RE.search(raw)
    if match:
        body = match.group(1)
    else:
        # Truncated before the closing bracket.
        idx = raw.find('"messages"')
        if idx == -1:
            return []
        bracket = raw.find("[", idx)
        if bracket == -1:
            return []
        body = raw[bracket + 1 :]
    out: list[str] = []
    for m in _JSON_STRING_RE.finditer(body):
        try:
            out.append(json.loads(f'"{m.group(1)}"'))
        except json.JSONDecodeError:
            continue
    return [s for s in out if s.strip()]


def parse_turn_output(raw: str) -> TurnOutput:
    """Parse model output into a TurnOutput, recovering where reasonable.

    Raises ParseError only when nothing usable can be extracted.
    """
    if not raw or not raw.strip():
        raise ParseError("empty output")

    data = _load_json_object(raw)
    if data is not None:
        try:
            return TurnOutput.model_validate(data)
        except ValidationError:
            # Keep whatever messages there are; drop the rest.
            messages = data.get("messages")
            if isinstance(messages, list | str):
                try:
                    return TurnOutput.model_validate({"messages": messages})
                except ValidationError:
                    pass
            raise ParseError("invalid structure") from None

    salvaged = _salvage_messages(raw)
    if salvaged:
        return TurnOutput(messages=salvaged)

    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        raise ParseError("unrecoverable JSON")

    # The model ignored the format and wrote plain text: treat it as the reply.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", stripped) if p.strip()]
    return TurnOutput(messages=paragraphs or [stripped])


def parse_model(raw: str, model: type[BaseModel]) -> Any:
    data = _load_json_object(raw)
    if data is None:
        raise ParseError("not a JSON object")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ParseError(str(exc)) from exc

"""Structured response parsing, recovery, and schema strictness."""

from __future__ import annotations

import json

import pytest

from app.companion.schemas import (
    CONSOLIDATION_SCHEMA,
    PROACTIVE_SCHEMA,
    SUMMARY_SCHEMA,
    TURN_SCHEMA,
    ParseError,
    parse_turn_output,
)
from tests.fakes import turn_json


def test_parses_valid_output():
    out = parse_turn_output(
        turn_json(
            ["bold assumption", "…but unfortunately yes"],
            memory_candidates=[
                {
                    "subject": "bram",
                    "content": "Bram is going to Levenslang on 23 October.",
                    "category": "plan",
                    "importance": 0.8,
                    "confidence": 0.95,
                    "event_date": "2026-10-23",
                }
            ],
            relationship_update={
                "affection": 1,
                "irritation": 0,
                "familiarity": 0,
                "trust": 0,
                "attraction": 0,
                "playfulness": 1,
                "emotional_openness": 0,
                "sexual_comfort": 0,
            },
        )
    )
    assert out.messages == ["bold assumption", "…but unfortunately yes"]
    assert out.memory_candidates[0].event_date == "2026-10-23"
    assert out.relationship_update.affection == 1


def test_recovers_from_code_fences_and_chatter():
    raw = "Sure!\n```json\n" + turn_json(["shut up"]) + "\n```"
    assert parse_turn_output(raw).messages == ["shut up"]
    assert parse_turn_output("here you go " + turn_json(["😂"]) + " done").messages == ["😂"]


def test_salvages_messages_from_truncated_json():
    full = turn_json(["yeah no you're not getting away with that one"])
    truncated = full[: full.index('"memory_candidates"') + 10]
    assert parse_turn_output(truncated).messages == ["yeah no you're not getting away with that one"]


def test_plain_text_fallback_becomes_messages():
    out = parse_turn_output("okay that was suspiciously specific 😂\n\nwait")
    assert out.messages == ["okay that was suspiciously specific 😂", "wait"]


def test_values_are_clamped_and_lists_capped():
    raw = json.dumps(
        {
            "messages": ["a", "b", "c", "d", "e", "f"],
            "reaction": "🦄",  # not in Sofia's allowed set
            "relationship_update": {"trust": 9, "irritation": -7, "affection": "x"},
            "memory_candidates": [{"content": "Bram x", "importance": 4, "confidence": -1}],
            "used_memory_ids": ["M12", 3, "nope"],
        }
    )
    out = parse_turn_output(raw)
    assert len(out.messages) == 4 and out.messages[-1] == "d\ne\nf"
    assert out.reaction is None
    assert out.relationship_update.trust == 2 and out.relationship_update.irritation == -2
    assert out.relationship_update.affection == 0
    assert out.memory_candidates[0].importance == 1.0 and out.memory_candidates[0].confidence == 0.0
    assert out.used_memory_ids == [12, 3]


def test_unrecoverable_output_raises():
    with pytest.raises(ParseError):
        parse_turn_output("")
    with pytest.raises(ParseError):
        parse_turn_output('{"oops": [1, 2')


def _walk(schema: dict) -> None:
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            _walk(sub)
        return
    types = schema.get("type")
    types = types if isinstance(types, list) else [types]
    if "object" in types:
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        for sub in schema["properties"].values():
            _walk(sub)
    if "array" in types:
        _walk(schema["items"])


@pytest.mark.parametrize("schema", [TURN_SCHEMA, PROACTIVE_SCHEMA, SUMMARY_SCHEMA, CONSOLIDATION_SCHEMA])
def test_schemas_are_strict_mode_compatible(schema):
    _walk(schema)

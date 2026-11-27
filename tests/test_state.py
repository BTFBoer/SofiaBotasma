"""Relationship state changes slowly and plausibly."""

from __future__ import annotations

import re
from datetime import timedelta

from app.companion.state import RelationshipState, apply_nudges, apply_time_decay, describe


def test_nudges_are_small_and_bounded():
    state = RelationshipState()
    before = state.dims["trust"]
    apply_nudges(state, {"trust": 2}, "2026-10-02")
    assert 0 < state.dims["trust"] - before < 0.03
    for _ in range(500):
        apply_nudges(state, {"trust": 2, "irritation": -2}, "2026-10-02")
    assert state.dims["trust"] <= 1.0 and state.dims["irritation"] >= 0.0


def test_daily_gain_cap():
    state = RelationshipState()
    start = state.dims["sexual_comfort"]
    for _ in range(100):
        apply_nudges(state, {"sexual_comfort": 2}, "2026-10-02")
    assert state.dims["sexual_comfort"] - start <= 0.0401
    apply_nudges(state, {"sexual_comfort": 2}, "2026-10-03")  # new day, new allowance
    assert state.dims["sexual_comfort"] - start > 0.04


def test_irritation_rises_fast_and_fades_with_time_not_one_message(clock):
    state = RelationshipState()
    state.last_decay_at = clock()
    apply_nudges(state, {"irritation": 2}, "2026-10-02", cause="he called her job 'basically colouring in'")
    high = state.dims["irritation"]
    assert high >= 0.15
    apply_nudges(state, {"irritation": -2}, "2026-10-02")
    assert state.dims["irritation"] > high * 0.4  # one apology doesn't wipe it
    clock.advance(hours=3)
    apply_time_decay(state, clock())
    assert 0 < state.dims["irritation"] < high
    clock.advance(hours=48)
    apply_time_decay(state, clock())
    assert state.dims["irritation"] == 0.0 and state.irritation_cause == ""


def test_description_is_qualitative():
    state = RelationshipState()
    state.dims["irritation"] = 0.5
    state.irritation_cause = "a comment about her job"
    text = "\n".join(describe(state))
    assert not re.search(r"\d", text)
    assert "annoyed" in text


def test_roundtrip_serialization(clock):
    state = RelationshipState()
    state.dynamic("example").stage = "emerging"
    state.last_decay_at = clock() - timedelta(hours=1)
    restored = RelationshipState.from_dict(state.to_dict())
    assert restored.dims == state.dims
    assert restored.dynamics["example"].stage == "emerging"

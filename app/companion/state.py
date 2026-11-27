"""Relationship and mood state.

Internally the dimensions are floats in [0, 1], but the model never sees
numbers: it gets qualitative descriptions. Change is slow by construction:
- the model can only nudge a dimension by -2..+2 small steps per turn,
- gains shrink as a value approaches 1 (diminishing returns),
- positive gains per dimension are capped per local day,
- irritation and mood intensity decay with time rather than per message,
  so friction lingers for hours unless it is actually addressed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.companion.schemas import DIMENSIONS
from app.utils.timeutil import from_iso, to_iso

STEP: dict[str, float] = {
    "familiarity": 0.012,
    "trust": 0.014,
    "affection": 0.014,
    "attraction": 0.014,
    "playfulness": 0.02,
    "emotional_openness": 0.014,
    "sexual_comfort": 0.012,
    "irritation": 0.09,
}

# Maximum positive change per local day for slow-moving dimensions.
DAILY_GAIN_CAP: dict[str, float] = {
    "familiarity": 0.05,
    "trust": 0.05,
    "affection": 0.06,
    "attraction": 0.06,
    "playfulness": 0.08,
    "emotional_openness": 0.05,
    "sexual_comfort": 0.04,
}

PASSIVE_FAMILIARITY_PER_TURN = 0.0015
IRRITATION_HALF_LIFE_HOURS = 7.0
MOOD_HALF_LIFE_HOURS = 6.0

DEFAULT_DIMS: dict[str, float] = {
    "familiarity": 0.12,
    "trust": 0.15,
    "affection": 0.15,
    "attraction": 0.18,
    "playfulness": 0.45,
    "emotional_openness": 0.12,
    "sexual_comfort": 0.08,
    "irritation": 0.0,
}

DYNAMIC_STAGES = ("latent", "emerging", "established")


@dataclass
class Mood:
    label: str
    intensity: float
    cause: str
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "intensity": round(self.intensity, 3),
            "cause": self.cause,
            "updated_at": to_iso(self.updated_at) if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mood:
        return cls(
            label=str(data.get("label", "")),
            intensity=float(data.get("intensity", 0.4)),
            cause=str(data.get("cause", "")),
            updated_at=from_iso(data.get("updated_at")),
        )


@dataclass
class DynamicStatus:
    stage: str = "latent"
    first_seen_at: datetime | None = None
    established_at: datetime | None = None
    last_bram_reference_at: datetime | None = None
    last_sofia_reference_at: datetime | None = None
    last_sofia_initiation_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "first_seen_at": to_iso(self.first_seen_at) if self.first_seen_at else None,
            "established_at": to_iso(self.established_at) if self.established_at else None,
            "last_bram_reference_at": to_iso(self.last_bram_reference_at) if self.last_bram_reference_at else None,
            "last_sofia_reference_at": to_iso(self.last_sofia_reference_at) if self.last_sofia_reference_at else None,
            "last_sofia_initiation_at": (
                to_iso(self.last_sofia_initiation_at) if self.last_sofia_initiation_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DynamicStatus:
        stage = data.get("stage", "latent")
        return cls(
            stage=stage if stage in DYNAMIC_STAGES else "latent",
            first_seen_at=from_iso(data.get("first_seen_at")),
            established_at=from_iso(data.get("established_at")),
            last_bram_reference_at=from_iso(data.get("last_bram_reference_at")),
            last_sofia_reference_at=from_iso(data.get("last_sofia_reference_at")),
            last_sofia_initiation_at=from_iso(data.get("last_sofia_initiation_at")),
        )


@dataclass
class RelationshipState:
    dims: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_DIMS))
    mood: Mood = field(default_factory=lambda: Mood("easy, curious", 0.35, "an ordinary day"))
    baseline_mood: Mood = field(default_factory=lambda: Mood("easy, curious", 0.35, "an ordinary day"))
    dynamic_summary: str = ""
    dynamics: dict[str, DynamicStatus] = field(default_factory=dict)
    irritation_cause: str = ""
    turns: int = 0
    daily_gain: dict[str, Any] = field(default_factory=dict)  # {"date": "YYYY-MM-DD", "gains": {dim: float}}
    last_decay_at: datetime | None = None

    # ------------------------------------------------------------------ serialization
    def to_dict(self) -> dict[str, Any]:
        return {
            "dims": {k: round(v, 4) for k, v in self.dims.items()},
            "mood": self.mood.to_dict(),
            "baseline_mood": self.baseline_mood.to_dict(),
            "dynamic_summary": self.dynamic_summary,
            "dynamics": {k: v.to_dict() for k, v in self.dynamics.items()},
            "irritation_cause": self.irritation_cause,
            "turns": self.turns,
            "daily_gain": self.daily_gain,
            "last_decay_at": to_iso(self.last_decay_at) if self.last_decay_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationshipState:
        dims = dict(DEFAULT_DIMS)
        dims.update({k: float(v) for k, v in (data.get("dims") or {}).items() if k in DEFAULT_DIMS})
        return cls(
            dims=dims,
            mood=Mood.from_dict(data.get("mood") or {}),
            baseline_mood=Mood.from_dict(data.get("baseline_mood") or {}),
            dynamic_summary=str(data.get("dynamic_summary", "")),
            dynamics={k: DynamicStatus.from_dict(v) for k, v in (data.get("dynamics") or {}).items()},
            irritation_cause=str(data.get("irritation_cause", "")),
            turns=int(data.get("turns", 0)),
            daily_gain=data.get("daily_gain") or {},
            last_decay_at=from_iso(data.get("last_decay_at")),
        )

    @classmethod
    def initial(cls, persona_initial: dict[str, Any] | None) -> RelationshipState:
        state = cls()
        if not persona_initial:
            return state
        rel = persona_initial.get("relationship") or {}
        for k, v in rel.items():
            if k in state.dims:
                state.dims[k] = max(0.0, min(1.0, float(v)))
        mood = persona_initial.get("mood")
        if mood:
            state.mood = Mood.from_dict(mood)
            state.baseline_mood = Mood.from_dict(mood)
        state.dynamic_summary = str(persona_initial.get("dynamic_summary", "")).strip()
        return state

    # ------------------------------------------------------------------ dynamics
    def dynamic(self, dynamic_id: str) -> DynamicStatus:
        if dynamic_id not in self.dynamics:
            self.dynamics[dynamic_id] = DynamicStatus()
        return self.dynamics[dynamic_id]

    # ------------------------------------------------------------------ derived
    @property
    def closeness(self) -> float:
        d = self.dims
        return (d["familiarity"] + d["trust"] + d["emotional_openness"]) / 3.0

    @property
    def sharing_level(self) -> str:
        c = self.closeness
        if c < 0.3:
            return "open"
        if c < 0.5:
            return "familiar"
        if c < 0.68 or self.dims["emotional_openness"] < 0.5:
            return "trusted"
        return "deep"


def apply_time_decay(state: RelationshipState, now: datetime) -> None:
    """Irritation fades and moods drift back to baseline with time."""
    last = state.last_decay_at
    state.last_decay_at = now
    if last is None:
        return
    hours = max(0.0, (now - last).total_seconds() / 3600.0)
    if hours <= 0:
        return
    state.dims["irritation"] *= math.pow(0.5, hours / IRRITATION_HALF_LIFE_HOURS)
    if state.dims["irritation"] < 0.03:
        state.dims["irritation"] = 0.0
        state.irritation_cause = ""
    if state.mood.label != state.baseline_mood.label:
        state.mood.intensity *= math.pow(0.5, hours / MOOD_HALF_LIFE_HOURS)
        if state.mood.intensity < 0.18:
            state.mood = Mood(state.baseline_mood.label, state.baseline_mood.intensity, state.baseline_mood.cause, now)


def apply_nudges(state: RelationshipState, nudges: dict[str, int], now_local_date: str, *, cause: str = "") -> None:
    """Apply the model's small nudges with diminishing returns and daily caps."""
    if state.daily_gain.get("date") != now_local_date:
        state.daily_gain = {"date": now_local_date, "gains": {}}
    gains: dict[str, float] = state.daily_gain.setdefault("gains", {})

    for dim in DIMENSIONS:
        n = max(-2, min(2, int(nudges.get(dim, 0) or 0)))
        if dim == "familiarity":
            # Familiarity also grows just by talking.
            n_delta = n * STEP[dim] + PASSIVE_FAMILIARITY_PER_TURN
        else:
            n_delta = n * STEP[dim]
        if n_delta == 0:
            continue
        x = state.dims[dim]
        if dim == "irritation":
            # Annoyance can rise quickly, but only eases one step per turn.
            delta = n_delta if n_delta > 0 else max(n_delta, -STEP[dim])
        elif n_delta > 0:
            delta = n_delta * (1.0 - x) ** 0.8
            cap = DAILY_GAIN_CAP.get(dim)
            if cap is not None:
                remaining = max(0.0, cap - gains.get(dim, 0.0))
                delta = min(delta, remaining)
                gains[dim] = gains.get(dim, 0.0) + delta
        else:
            delta = n_delta * (0.4 + 0.6 * x)
        state.dims[dim] = max(0.0, min(1.0, x + delta))

    if nudges.get("irritation", 0) > 0 and cause:
        state.irritation_cause = cause[:200]
    state.turns += 1


def _band(value: float, bands: list[tuple[float, str]]) -> str:
    for upper, text in bands:
        if value < upper:
            return text
    return bands[-1][1]


def describe(state: RelationshipState) -> list[str]:
    """Qualitative, number-free description for the prompt."""
    d = state.dims
    lines = [
        "familiarity: "
        + _band(
            d["familiarity"],
            [
                (0.15, "still new — only a handful of conversations so far"),
                (0.3, "still new to each other; a rhythm is starting to form"),
                (0.5, "getting to know each other; they know each other's humor"),
                (0.7, "comfortable and familiar"),
                (0.85, "they know each other well"),
                (1.01, "deeply familiar"),
            ],
        ),
        "trust: "
        + _band(
            d["trust"],
            [
                (0.2, "guarded — she's still deciding about him"),
                (0.4, "cautiously open"),
                (0.6, "trusts him with ordinary personal things"),
                (0.8, "trusts him with real things"),
                (1.01, "trusts him deeply"),
            ],
        ),
        "affection: "
        + _band(
            d["affection"],
            [
                (0.2, "curious about him, nothing more yet"),
                (0.4, "likes him"),
                (0.6, "fond of him"),
                (0.8, "genuinely affectionate"),
                (1.01, "very attached — but not dependent"),
            ],
        ),
        "attraction: "
        + _band(
            d["attraction"],
            [
                (0.2, "no particular pull yet"),
                (0.4, "a flicker of interest she'd deny"),
                (0.6, "attracted to him"),
                (0.8, "clearly attracted"),
                (1.01, "strongly drawn to him"),
            ],
        ),
        "playfulness: "
        + _band(
            d["playfulness"], [(0.3, "a bit reserved in play"), (0.6, "playful"), (1.01, "teasing is their default")]
        ),
        "emotional openness: "
        + _band(
            d["emotional_openness"],
            [
                (0.2, "keeps her inner life to herself"),
                (0.4, "shares lightly"),
                (0.6, "shares honestly"),
                (0.8, "can be vulnerable with him"),
                (1.01, "very open with him"),
            ],
        ),
        "intimacy/sexual comfort: "
        + _band(
            d["sexual_comfort"],
            [
                (0.15, "nothing sexual on the table — flirting stays light, deniable, above the surface"),
                (0.35, "innuendo and charged subtext are fine; she'd slow anything explicit down"),
                (0.55, "comfortable with sensual flirting; explicit only if a moment truly builds and she wants it"),
                (0.75, "comfortable with explicit intimacy when it's mutual"),
                (1.01, "very comfortable and uninhibited with him"),
            ],
        ),
    ]
    irritation = d["irritation"]
    if irritation >= 0.1:
        level = _band(irritation, [(0.3, "slightly prickly"), (0.6, "annoyed with him"), (1.01, "properly annoyed")])
        cause = f" — about: {state.irritation_cause}" if state.irritation_cause else ""
        lines.append(f"irritation: {level}{cause}. This hasn't evaporated; it eases when it's actually addressed.")
    return lines

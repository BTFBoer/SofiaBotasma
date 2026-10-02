"""Staged private dynamics (defined in the private user profile overlay).

A dynamic moves latent -> emerging -> established:
- latent:      nothing has come up; the model sees at most generic guidance.
- emerging:    one of the dynamic's keywords appeared in a message from BRAM.
- established: the model marked it established (only possible once emerging).

Once established, the context also shows when Bram and Sofia last brought it
up, and tells the model to leave it alone if Sofia initiated it recently.
That keeps a recurring element from turning her into a caricature.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.companion.persona import DynamicSpec
from app.companion.state import RelationshipState
from app.memory.text import keyword_hit
from app.utils.timeutil import humanize_delta


def observe_bram(state: RelationshipState, specs: list[DynamicSpec], text: str, now: datetime) -> list[str]:
    """Record keyword hits in Bram's message(s). Returns ids that were hit."""
    hit_ids = []
    for spec in specs:
        if spec.detect_keywords and keyword_hit(text, spec.detect_keywords):
            status = state.dynamic(spec.id)
            status.last_bram_reference_at = now
            if status.stage == "latent":
                status.stage = "emerging"
                status.first_seen_at = now
            hit_ids.append(spec.id)
    return hit_ids


def observe_sofia(
    state: RelationshipState, specs: list[DynamicSpec], bubbles: list[str], now: datetime, bram_hit_ids: list[str]
) -> None:
    text = "\n".join(bubbles)
    for spec in specs:
        if not spec.detect_keywords or not keyword_hit(text, spec.detect_keywords):
            continue
        status = state.dynamic(spec.id)
        status.last_sofia_reference_at = now
        if spec.id not in bram_hit_ids:
            status.last_sofia_initiation_at = now


def establish(state: RelationshipState, specs: list[DynamicSpec], ids: list[str], now: datetime) -> None:
    known = {s.id for s in specs}
    for dynamic_id in ids:
        if dynamic_id not in known:
            continue
        status = state.dynamic(dynamic_id)
        if status.stage == "emerging":
            status.stage = "established"
            status.established_at = now


def _ago(when: datetime | None, now: datetime) -> str:
    return "never" if when is None else f"{humanize_delta(now - when)} ago"


def render(state: RelationshipState, specs: list[DynamicSpec], now: datetime) -> list[str]:
    lines: list[str] = []
    for spec in specs:
        status = state.dynamics.get(spec.id)
        stage = status.stage if status else "latent"
        if stage == "latent":
            if spec.latent_guidance:
                lines.append(spec.latent_guidance)
            continue
        assert status is not None
        lines.append(f"[{spec.id}] stage: {stage}")
        if stage == "emerging":
            lines.append(spec.emerging_guidance)
        else:
            lines.append(spec.established_guidance)
            lines.append(
                f"Recency — Bram last touched on it: {_ago(status.last_bram_reference_at, now)}; "
                f"Sofia last brought it up herself: {_ago(status.last_sofia_initiation_at, now)}."
            )
            cooldown = timedelta(days=spec.min_days_between_sofia_initiations)
            if status.last_sofia_initiation_at and now - status.last_sofia_initiation_at < cooldown:
                lines.append("→ She initiated it recently. Leave it alone unless Bram brings it up himself.")
        if spec.sofia_side:
            lines.append(spec.sofia_side)
    return [line for line in lines if line]

"""Loading and rendering of persona.yaml and user_profile.yaml.

Each file may have a private overlay next to it (`persona.private.yaml`,
`user_profile.private.yaml`). Overlays are deep-merged over the base file
(dicts merge, lists append, scalars replace) and are git-ignored, so
intimate details never have to live in a repository.

These files are read-only for the application: conversation can never
rewrite Sofia's core. Learned facts live in the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class PersonaError(RuntimeError):
    pass


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = deep_merge(base[key], value) if key in base else value
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        return [*base, *overlay]
    return overlay


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PersonaError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PersonaError(f"{path} must contain a mapping at the top level")
    return data


def load_with_overlay(base_path: Path) -> tuple[dict[str, Any], list[Path]]:
    if not base_path.exists():
        raise PersonaError(f"Missing {base_path}")
    data = _load_yaml(base_path)
    loaded = [base_path]
    overlay_path = base_path.with_name(base_path.stem + ".private.yaml")
    if overlay_path.exists():
        data = deep_merge(data, _load_yaml(overlay_path))
        loaded.append(overlay_path)
    return data, loaded


def _dump(value: Any) -> str:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False).strip()


def _days(spec: Any) -> set[str]:
    if spec in (None, "all", "every day"):
        return set(WEEKDAYS)
    if spec == "weekdays":
        return set(WEEKDAYS[:5])
    if spec == "weekend":
        return {"sat", "sun"}
    if isinstance(spec, str):
        return {spec.lower()[:3]}
    return {str(d).lower()[:3] for d in spec}


def _minutes(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


@dataclass
class Persona:
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("static_core", {}).get("name", "Sofia"))

    @property
    def initial_state(self) -> dict[str, Any]:
        return self.data.get("initial_state") or {}

    @property
    def seed_facts(self) -> list[str]:
        return [str(f) for f in (self.data.get("learned_character_facts") or [])]

    def current_activity(self, local_now: datetime) -> str | None:
        """What Sofia is plausibly doing right now according to her routine."""
        schedule = (self.data.get("routine") or {}).get("schedule") or []
        day = WEEKDAYS[local_now.weekday()]
        minutes = local_now.hour * 60 + local_now.minute
        for rule in schedule:
            try:
                if day not in _days(rule.get("days")):
                    continue
                start, end = _minutes(rule["from"]), _minutes(rule["to"])
            except (KeyError, ValueError, AttributeError):
                continue
            inside = start <= minutes < end if start <= end else (minutes >= start or minutes < end)
            if inside:
                return str(rule.get("activity", "")).strip() or None
        return None

    def render_static(self) -> str:
        d = self.data
        parts: list[str] = []
        parts.append(
            "=== SOFIA — WHO SHE IS (static core; this never changes through conversation) ===\n"
            + _dump(d.get("static_core", {}))
        )
        if d.get("voice"):
            parts.append("=== HOW SHE WRITES ===\n" + _dump(d["voice"]))
        if d.get("biography"):
            parts.append(
                "=== HER LIFE & HISTORY ===\n"
                "Reveal levels — open: shares freely · familiar: once there's some familiarity · "
                "trusted: once real trust exists · deep: only with real closeness, rarely, usually in a quiet or "
                "late moment. The current sharing level is given in CURRENT STATE. Material above that level "
                "isn't a dramatic secret; she just doesn't volunteer it yet. If asked directly she deflects or "
                "gives a light, partial answer that stays consistent with it. Never contradict anything here.\n"
                + _dump(d["biography"])
            )
        for key, title in (
            ("tastes", "TASTES & OPINIONS"),
            ("quirks", "QUIRKS & CONTRADICTIONS"),
            ("stories", "STORIES SHE CAN TELL (each has a reveal level)"),
        ):
            if d.get(key):
                parts.append(f"=== {title} ===\n" + _dump(d[key]))
        routine = d.get("routine") or {}
        routine_text = {k: v for k, v in routine.items() if k != "schedule"}
        if routine_text:
            parts.append("=== HER ROUTINE ===\n" + _dump(routine_text))
        if d.get("intimacy"):
            parts.append(
                "=== HER SENSUALITY (her own; revealed through behaviour, not lists) ===\n" + _dump(d["intimacy"])
            )
        if self.seed_facts:
            parts.append("=== ALREADY ESTABLISHED ===\n" + "\n".join(f"- {f}" for f in self.seed_facts))
        if d.get("relationship_premise"):
            parts.append("=== HOW SHE AND BRAM STARTED ===\n" + str(d["relationship_premise"]).strip())
        return "\n\n".join(parts)


@dataclass
class DynamicSpec:
    id: str
    detect_keywords: list[str] = field(default_factory=list)
    latent_guidance: str = ""
    emerging_guidance: str = ""
    established_guidance: str = ""
    sofia_side: str = ""
    min_days_between_sofia_initiations: float = 3.0


@dataclass
class UserProfile:
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("name", "Bram"))

    @property
    def dynamics(self) -> list[DynamicSpec]:
        specs = []
        for raw in (self.data.get("intimate_profile") or {}).get("dynamics") or []:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            specs.append(
                DynamicSpec(
                    id=str(raw["id"]).strip().lower(),
                    detect_keywords=[str(k) for k in raw.get("detect_keywords") or []],
                    latent_guidance=str(raw.get("latent_guidance", "")).strip(),
                    emerging_guidance=str(raw.get("emerging_guidance", "")).strip(),
                    established_guidance=str(raw.get("established_guidance", "")).strip(),
                    sofia_side=str(raw.get("sofia_side", "")).strip(),
                    min_days_between_sofia_initiations=float(raw.get("min_days_between_sofia_initiations", 3)),
                )
            )
        return specs

    def render_static(self) -> str:
        d = self.data
        known = d.get("known_to_sofia_from_start") or []
        parts = [
            "=== BRAM — BACKGROUND FOR YOU AS THE WRITER ===\n"
            "Sofia knows from the start only the items under 'known_to_sofia_from_start'. Everything else here "
            "is for you, so you understand him and the chemistry he responds to. She learns the rest from him in "
            "conversation (see the memories you're given) — she must never know something he hasn't told her, "
            "and must never recite a biography at him.\n"
            + _dump({"name": self.name, "known_to_sofia_from_start": known})
        ]
        if d.get("writer_background"):
            parts.append(_dump({"writer_background": d["writer_background"]}))
        general = (d.get("intimate_profile") or {}).get("general")
        if general:
            parts.append(
                "=== WHAT INTIMACY MEANS TO HIM (writer background; Sofia discovers this over time) ===\n"
                + _dump(general)
            )
        return "\n\n".join(parts)


def load_persona_bundle(persona_dir: Path) -> tuple[Persona, UserProfile, list[Path]]:
    persona_data, persona_files = load_with_overlay(persona_dir / "persona.yaml")
    profile_data, profile_files = load_with_overlay(persona_dir / "user_profile.yaml")
    core = persona_data.get("static_core") or {}
    if int(core.get("age", 0)) < 21:
        raise PersonaError("persona.yaml static_core.age must be an adult age (21+).")
    return Persona(persona_data), UserProfile(profile_data), [*persona_files, *profile_files]

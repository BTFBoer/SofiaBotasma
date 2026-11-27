"""Proactive messages: rare, never at night, never double-texting."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.scheduler.proactive import Hook, ProactiveInputs, evaluate, in_quiet_hours

TZ = ZoneInfo("Europe/Amsterdam")


def inputs(**kw) -> ProactiveInputs:
    now = datetime(2026, 10, 2, 14, 0, tzinfo=TZ)
    base = dict(
        now_local=now,
        enabled=True,
        last_message_at=now - timedelta(hours=6),
        last_message_role="user",
        sent_today=0,
        last_proactive_at=None,
        familiarity=0.4,
        hooks=[],
    )
    base.update(kw)
    return ProactiveInputs(**base)


def test_disabled_by_default_rules(settings):
    assert settings.proactive_default is False
    assert not evaluate(inputs(enabled=False), settings).allowed


def test_quiet_hours(settings):
    night = datetime(2026, 10, 2, 2, 30, tzinfo=TZ)
    assert in_quiet_hours(night, (23, 30), (8, 30))
    assert not in_quiet_hours(datetime(2026, 10, 2, 12, 0, tzinfo=TZ), (23, 30), (8, 30))
    assert not evaluate(inputs(now_local=night, last_message_at=night - timedelta(hours=5)), settings).allowed


def test_never_double_texts(settings):
    assert not evaluate(inputs(last_message_role="assistant"), settings).allowed


def test_daily_cap_and_spacing(settings):
    assert not evaluate(inputs(sent_today=2), settings).allowed
    now = inputs().now_local
    assert not evaluate(inputs(last_proactive_at=now - timedelta(hours=2)), settings).allowed


def test_not_right_after_a_conversation(settings):
    now = inputs().now_local
    assert not evaluate(inputs(last_message_at=now - timedelta(minutes=40)), settings).allowed


def test_new_relationship_needs_a_reason(settings):
    assert not evaluate(inputs(familiarity=0.1), settings).allowed
    assert evaluate(inputs(familiarity=0.1, hooks=[Hook("big meeting today", strong=True)]), settings).allowed


def test_probability_is_low_and_higher_with_hooks(settings):
    plain = evaluate(inputs(), settings)
    hooked = evaluate(inputs(hooks=[Hook("Levenslang tonight", strong=True)]), settings)
    assert plain.allowed and hooked.allowed
    assert plain.probability < 0.05 < hooked.probability <= 0.25

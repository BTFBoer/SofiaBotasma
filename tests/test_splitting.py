"""Bubble cleanup, Telegram message splitting and timing."""

from __future__ import annotations

import random

from app.companion.style import (
    TELEGRAM_LIMIT,
    finalize_bubbles,
    find_assistant_phrases,
    sanitize_bubble,
    split_for_telegram,
    style_notes,
)
from app.utils.timing import plan_timings


def test_split_long_text_under_limit_and_lossless():
    paragraph = ("This is a sentence that goes on for a while. " * 30).strip()
    text = "\n\n".join([paragraph] * 6)
    chunks = split_for_telegram(text)
    assert len(chunks) > 1
    assert all(len(c) <= TELEGRAM_LIMIT for c in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(text.split())


def test_split_handles_text_without_spaces():
    chunks = split_for_telegram("x" * 9000)
    assert all(len(c) <= TELEGRAM_LIMIT for c in chunks)
    assert "".join(chunks) == "x" * 9000


def test_short_text_is_single_chunk():
    assert split_for_telegram("shut up") == ["shut up"]
    assert split_for_telegram("   ") == []


def test_finalize_limits_bubbles_and_strips_artifacts():
    bubbles = finalize_bubbles(
        ["Sofia: bold assumption", "*smiles softly* …but unfortunately yes", "", '"third"', "four", "five"]
    )
    assert bubbles == ["bold assumption", "…but unfortunately yes", "third", "four\nfive"]


def test_emphasis_is_kept_but_actions_removed():
    assert sanitize_bubble("that was *not* what I said") == "that was *not* what I said"
    assert sanitize_bubble("*leans closer* hi") == "hi"
    assert sanitize_bubble("(giggles) okay") == "okay"
    assert sanitize_bubble("*leans closer* hi", allow_actions=True) == "*leans closer* hi"


def test_leaked_json_never_sent():
    assert finalize_bubbles(['{"messages": ["x"], "relationship_update": {}}', "real one"]) == ["real one"]


def test_assistant_phrases_detected():
    assert find_assistant_phrases(["That's a great question! How can I help?"])
    assert find_assistant_phrases(["Goede vraag, hoe kan ik je helpen"])
    assert not find_assistant_phrases(["yeah no you're not getting away with that one"])


def test_style_notes_flag_question_habit():
    turns = [["hm?"], ["really?"], ["and then?"], ["okay"]]
    notes = style_notes(turns)
    assert any("question" in n for n in notes)
    assert style_notes([["ok"], ["fine."]]) == []


def test_timings_are_human_and_bounded():
    rng = random.Random(1)
    t = plan_timings("morning", ["morning", "you sound suspiciously awake"], rng=rng)
    assert 1.0 <= t[0].typing <= 8.0
    assert all(0.7 <= x.typing <= 6.0 for x in t[1:])
    slow_model = plan_timings("morning", ["morning"], already_elapsed=7.5, rng=rng)
    assert slow_model[0].typing < 1.0  # model latency already counted

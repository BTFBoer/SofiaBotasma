"""Bubble post-processing, Telegram splitting and lightweight style feedback.

Realism comes from the prompt and the model, not from post-hoc tricks: this
module never injects typos or random lowercase. It only removes things that
must never reach Telegram (stage directions, name prefixes, leaked JSON) and
computes gentle feedback about recent habits that is fed back into context.
"""

from __future__ import annotations

import re
from collections import Counter

TELEGRAM_LIMIT = 4096
SAFE_LIMIT = 4000

_NAME_PREFIX_RE = re.compile(r"^\s*(?:sofia|sofía)\s*:\s*", re.IGNORECASE)
_ACTION_STAR_RE = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]{1,60}?)(?<!\s)\*(?![\w*])")
_ACTION_PAREN_RE = re.compile(
    r"\((?:smiles?|grins?|laughs?|giggles?|winks?|sighs?|blushes?|leans?[^)]*|bites?[^)]*|"
    r"lacht|glimlacht|knipoogt|zucht|giechelt|bloost)\)",
    re.IGNORECASE,
)
_ACTION_WORDS = re.compile(
    r"\b(smiles?|grins?|laughs?|giggles?|winks?|sighs?|blushes?|leans?|bites?|smirks?|rolls?|tilts?|whispers?|"
    r"glimlach\w*|lacht|knipoog\w*|zucht|giechel\w*|bloost|grijns\w*|fluister\w*)\b",
    re.IGNORECASE,
)
_EMOJI_RE = re.compile("[\U0001f300-\U0001faff☀-➿]")

ASSISTANT_PHRASES = [
    r"\bhow can i (?:help|assist)\b",
    r"\bhow may i (?:help|assist)\b",
    r"\bis there anything else\b",
    r"\b(?:that'?s|what) a great question\b",
    r"\bgreat question\b",
    r"\bi appreciate you sharing\b",
    r"\bthank you for sharing\b",
    r"\bi understand how you feel\b",
    r"\bit sounds like you(?:'re| are)\b",
    r"\bwould you like me to\b",
    r"\bfeel free to\b",
    r"\bas an ai\b",
    r"\bas a language model\b",
    r"\bi'?m here (?:for you|to help)\b",
    r"\bhoe kan ik je helpen\b",
    r"\bgoede vraag\b",
    r"\bik begrijp hoe je je voelt\b",
    r"\bhet klinkt alsof je\b",
    r"\bbedankt voor het delen\b",
    r"\bwil je dat ik\b",
]
_ASSISTANT_RE = [re.compile(p, re.IGNORECASE) for p in ASSISTANT_PHRASES]


def bram_uses_action_format(recent_user_texts: list[str]) -> bool:
    """True if Bram himself writes *actions* — then Sofia may mirror it."""
    hits = 0
    for text in recent_user_texts[-12:]:
        for match in _ACTION_STAR_RE.finditer(text):
            if _ACTION_WORDS.search(match.group(1)) or len(match.group(1).split()) >= 2:
                hits += 1
    return hits >= 2


def sanitize_bubble(text: str, *, allow_actions: bool = False) -> str:
    text = text.replace("\r\n", "\n").strip()
    text = _NAME_PREFIX_RE.sub("", text)
    # A whole bubble wrapped in quotes is a model artifact, not a quote.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"“”'" and text.count(text[0]) == 2:
        text = text[1:-1].strip()
    if not allow_actions:
        text = _ACTION_PAREN_RE.sub("", text)

        def _drop_action(match: re.Match[str]) -> str:
            inner = match.group(1)
            # Keep *emphasis* of a single word; drop "*smiles softly*"-style narration.
            if _ACTION_WORDS.search(inner) and len(inner.split()) <= 8:
                return ""
            return match.group(0)

        text = _ACTION_STAR_RE.sub(_drop_action, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_like_leaked_json(text: str) -> bool:
    stripped = text.strip()
    return (stripped.startswith("{") and '"messages"' in stripped) or '"relationship_update"' in stripped


def split_for_telegram(text: str, limit: int = SAFE_LIMIT) -> list[str]:
    """Split text into chunks under Telegram's 4096-character limit at natural boundaries."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n\n")
        if cut < limit * 0.4:
            cut = window.rfind("\n")
        if cut < limit * 0.4:
            sentence_ends = [m.end() for m in re.finditer(r"[.!?…](?:\s|$)", window)]
            cut = sentence_ends[-1] if sentence_ends and sentence_ends[-1] > limit * 0.4 else -1
        if cut < limit * 0.4:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


def finalize_bubbles(messages: list[str], *, allow_actions: bool = False, max_bubbles: int = 4) -> list[str]:
    cleaned = []
    for message in messages:
        if looks_like_leaked_json(message):
            continue
        bubble = sanitize_bubble(message, allow_actions=allow_actions)
        if bubble:
            cleaned.append(bubble)
    if len(cleaned) > max_bubbles:
        cleaned = cleaned[: max_bubbles - 1] + ["\n".join(cleaned[max_bubbles - 1 :])]
    out: list[str] = []
    for bubble in cleaned:
        out.extend(split_for_telegram(bubble))
    return out


def find_assistant_phrases(bubbles: list[str]) -> list[str]:
    found = []
    joined = "\n".join(bubbles)
    for pattern in _ASSISTANT_RE:
        match = pattern.search(joined)
        if match:
            found.append(match.group(0))
    return found


def style_notes(recent_turns: list[list[str]]) -> list[str]:
    """Gentle, factual feedback about Sofia's recent habits (fed back into context)."""
    notes: list[str] = []
    if not recent_turns:
        return notes
    last = recent_turns[-5:]

    ending_q = sum(1 for turn in last if turn and turn[-1].rstrip().endswith("?"))
    if len(last) >= 3 and ending_q >= 3:
        notes.append(
            f"{ending_q} of her last {len(last)} replies ended with a question. This time, don't — make a statement and let it sit."
        )

    lengths = [sum(len(b) for b in turn) for turn in last]
    if len(lengths) >= 3 and sum(lengths[-3:]) / 3 > 260:
        notes.append("Her recent replies have been long. Unless this moment needs it, go shorter.")

    multi = sum(1 for turn in last if len(turn) >= 3)
    if multi >= 2:
        notes.append("She has sent 3+ bubbles several times recently. One or two is usually enough.")

    openers = [turn[0].split()[0].lower().strip(".,!?…") for turn in last if turn and turn[0].split()]
    common = Counter(openers).most_common(1)
    if common and common[0][1] >= 3 and len(common[0][0]) > 0:
        notes.append(f'She opened several recent replies with "{common[0][0]}". Vary it.')

    emojis = [e for turn in last for b in turn for e in _EMOJI_RE.findall(b)]
    if emojis:
        top, count = Counter(emojis).most_common(1)[0]
        if count >= 3:
            notes.append(f"She has used {top} {count} times recently. Give it a rest.")
        with_emoji = sum(1 for turn in last if any(_EMOJI_RE.search(b) for b in turn))
        if with_emoji >= 4:
            notes.append("Most recent replies had emoji. Plain text this time.")

    haha = sum(1 for turn in last for b in turn if re.match(r"^\s*(ha){2,}|^\s*hah", b, re.IGNORECASE))
    if haha >= 3:
        notes.append('Too many replies starting with "haha". Drop it.')
    return notes

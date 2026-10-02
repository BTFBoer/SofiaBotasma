"""Time helpers. Everything is stored in UTC and rendered in local time."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def humanize_delta(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 90:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    if hours < 2:
        return "about an hour"
    if hours < 24:
        return f"about {hours} hours"
    days = hours // 24
    if days == 1:
        return "a day"
    if days < 14:
        return f"{days} days"
    weeks = days // 7
    if weeks < 9:
        return f"{weeks} weeks"
    return f"{days // 30} months"


def part_of_day(local: datetime) -> str:
    minutes = local.hour * 60 + local.minute
    if minutes < 5 * 60:
        return "middle of the night"
    if minutes < 7 * 60:
        return "very early morning"
    if minutes < 10 * 60:
        return "morning"
    if minutes < 12 * 60:
        return "late morning"
    if minutes < 14 * 60:
        return "around lunch"
    if minutes < 17 * 60 + 30:
        return "afternoon"
    if minutes < 19 * 60 + 30:
        return "early evening"
    if minutes < 22 * 60 + 30:
        return "evening"
    return "late evening"


def format_local(dt: datetime, tz: ZoneInfo, *, with_date: bool = True) -> str:
    local = dt.astimezone(tz)
    if with_date:
        return local.strftime("%A %-d %B %Y, %H:%M") if _supports_dash() else local.strftime("%A %d %B %Y, %H:%M")
    return local.strftime("%H:%M")


def format_short_date(d: date | datetime) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def relative_day(target: date, today: date) -> str:
    diff = (target - today).days
    if diff == 0:
        return "today"
    if diff == 1:
        return "tomorrow"
    if diff == -1:
        return "yesterday"
    if 1 < diff < 7:
        return f"in {diff} days ({target.strftime('%A')})"
    if diff >= 7:
        weeks = diff // 7
        return f"in {diff} days" if weeks < 2 else f"in about {weeks} weeks"
    return f"{-diff} days ago"


_DASH_SUPPORTED: bool | None = None


def _supports_dash() -> bool:
    """`%-d` works on glibc/macOS but not on Windows."""
    global _DASH_SUPPORTED
    if _DASH_SUPPORTED is None:
        try:
            _DASH_SUPPORTED = datetime(2020, 1, 5).strftime("%-d") == "5"
        except ValueError:
            _DASH_SUPPORTED = False
    return _DASH_SUPPORTED

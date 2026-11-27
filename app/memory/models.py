"""Plain data objects for rows in the database."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.utils.timeutil import from_iso, parse_date

SUBJECTS = ("bram", "sofia", "relationship")

BRAM_CATEGORIES = {
    "preference",
    "dislike",
    "person",
    "event",
    "plan",
    "story",
    "interest",
    "emotional",
    "boundary",
    "request",
    "work",
    "habit",
    "health",
    "intimacy",
    "communication",
    "other",
}
RELATIONSHIP_CATEGORIES = {
    "inside_joke",
    "pet_name",
    "dynamic",
    "boundary",
    "shared_theme",
    "emotional_event",
    "flirtation",
    "conflict",
    "ritual",
    "intimacy",
    "other",
}
SOFIA_CATEGORIES = {
    "biography",
    "preference",
    "opinion",
    "story",
    "habit",
    "today",
    "body",
    "relationship",
    "other",
}


@dataclass
class Message:
    id: int
    chat_id: int
    role: str
    kind: str
    content: str
    telegram_message_id: int | None
    reply_to_telegram_message_id: int | None
    meta: dict[str, Any]
    turn_id: str | None
    created_at: datetime
    summarized: bool = False
    excluded: bool = False

    @classmethod
    def from_row(cls, row: Any) -> Message:
        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            role=row["role"],
            kind=row["kind"],
            content=row["content"],
            telegram_message_id=row["telegram_message_id"],
            reply_to_telegram_message_id=row["reply_to_telegram_message_id"],
            meta=json.loads(row["meta"] or "{}"),
            turn_id=row["turn_id"],
            created_at=from_iso(row["created_at"]),  # type: ignore[arg-type]
            summarized=bool(row["summarized"]),
            excluded=bool(row["excluded"]),
        )


@dataclass
class Memory:
    id: int
    subject: str
    category: str
    content: str
    normalized: str
    importance: float
    confidence: float
    created_at: datetime
    updated_at: datetime
    last_referenced_at: datetime | None = None
    reference_count: int = 0
    source_message_id: int | None = None
    event_date: date | None = None
    expires_at: datetime | None = None
    embedding: list[float] | None = None
    active: bool = True
    consolidated: bool = False

    @classmethod
    def from_row(cls, row: Any) -> Memory:
        from app.memory.text import unpack_embedding

        return cls(
            id=row["id"],
            subject=row["subject"],
            category=row["category"],
            content=row["content"],
            normalized=row["normalized"],
            importance=float(row["importance"]),
            confidence=float(row["confidence"]),
            created_at=from_iso(row["created_at"]),  # type: ignore[arg-type]
            updated_at=from_iso(row["updated_at"]),  # type: ignore[arg-type]
            last_referenced_at=from_iso(row["last_referenced_at"]),
            reference_count=int(row["reference_count"] or 0),
            source_message_id=row["source_message_id"],
            event_date=parse_date(row["event_date"]),
            expires_at=from_iso(row["expires_at"]),
            embedding=unpack_embedding(row["embedding"]),
            active=bool(row["active"]),
            consolidated=bool(row["consolidated"]),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "category": self.category,
            "content": self.content,
            "importance": round(self.importance, 2),
            "confidence": round(self.confidence, 2),
            "created_at": self.created_at.isoformat(),
            "last_referenced_at": self.last_referenced_at.isoformat() if self.last_referenced_at else None,
            "reference_count": self.reference_count,
            "source_message_id": self.source_message_id,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "active": self.active,
        }


@dataclass
class Episode:
    id: int
    title: str
    summary: str
    tone: str
    importance: float
    tags: list[str]
    started_at: datetime
    ended_at: datetime
    created_at: datetime
    last_referenced_at: datetime | None = None
    embedding: list[float] | None = None

    @classmethod
    def from_row(cls, row: Any) -> Episode:
        from app.memory.text import unpack_embedding

        return cls(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            tone=row["tone"] or "",
            importance=float(row["importance"]),
            tags=json.loads(row["tags"] or "[]"),
            started_at=from_iso(row["started_at"]),  # type: ignore[arg-type]
            ended_at=from_iso(row["ended_at"]),  # type: ignore[arg-type]
            created_at=from_iso(row["created_at"]),  # type: ignore[arg-type]
            last_referenced_at=from_iso(row["last_referenced_at"]),
            embedding=unpack_embedding(row["embedding"]),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "tone": self.tone,
            "importance": round(self.importance, 2),
            "tags": self.tags,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
        }


@dataclass
class Thread:
    id: int
    content: str
    status: str
    importance: float
    due_date: date | None
    created_at: datetime
    updated_at: datetime
    source_message_id: int | None = None

    @classmethod
    def from_row(cls, row: Any) -> Thread:
        return cls(
            id=row["id"],
            content=row["content"],
            status=row["status"],
            importance=float(row["importance"]),
            due_date=parse_date(row["due_date"]),
            created_at=from_iso(row["created_at"]),  # type: ignore[arg-type]
            updated_at=from_iso(row["updated_at"]),  # type: ignore[arg-type]
            source_message_id=row["source_message_id"],
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "importance": round(self.importance, 2),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class NewMemory:
    """A memory about to be written (validated candidate)."""

    subject: str
    category: str
    content: str
    importance: float
    confidence: float
    source_message_id: int | None = None
    event_date: date | None = None
    expires_at: datetime | None = None
    embedding: list[float] | None = field(default=None, repr=False)

"""Data access for messages, memories, episodes, threads, state and settings."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from app.memory.database import Database
from app.memory.models import Episode, Memory, Message, NewMemory, Thread
from app.memory.text import normalize, pack_embedding
from app.utils.timeutil import from_iso, to_iso, utcnow


class MemoryStore:
    def __init__(self, db: Database, clock: Callable[[], datetime] = utcnow) -> None:
        self.db = db
        self.clock = clock

    # ------------------------------------------------------------------ messages
    async def add_message(
        self,
        *,
        chat_id: int,
        role: str,
        content: str,
        kind: str = "text",
        telegram_message_id: int | None = None,
        reply_to_telegram_message_id: int | None = None,
        meta: dict[str, Any] | None = None,
        turn_id: str | None = None,
        created_at: datetime | None = None,
        excluded: bool = False,
    ) -> int | None:
        """Insert a message. Returns the new id, or None if it was a duplicate."""
        lastrowid, rowcount = await self.db.execute(
            """
            INSERT OR IGNORE INTO messages
                (chat_id, role, kind, content, telegram_message_id, reply_to_telegram_message_id,
                 meta, turn_id, created_at, excluded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                role,
                kind,
                content,
                telegram_message_id,
                reply_to_telegram_message_id,
                json.dumps(meta or {}, ensure_ascii=False),
                turn_id,
                to_iso(created_at or self.clock()),
                int(excluded),
            ),
        )
        return lastrowid if rowcount else None

    async def get_messages(self, ids: Sequence[int]) -> list[Message]:
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = await self.db.fetchall(f"SELECT * FROM messages WHERE id IN ({marks}) ORDER BY id", tuple(ids))
        return [Message.from_row(r) for r in rows]

    async def get_message_by_telegram_id(self, chat_id: int, telegram_message_id: int) -> Message | None:
        row = await self.db.fetchone(
            "SELECT * FROM messages WHERE chat_id = ? AND telegram_message_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, telegram_message_id),
        )
        return Message.from_row(row) if row else None

    async def recent_messages(self, chat_id: int, limit: int, before_id: int | None = None) -> list[Message]:
        """Most recent non-excluded messages, oldest first."""
        if before_id is None:
            rows = await self.db.fetchall(
                "SELECT * FROM messages WHERE chat_id = ? AND excluded = 0 ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM messages WHERE chat_id = ? AND excluded = 0 AND id < ? ORDER BY id DESC LIMIT ?",
                (chat_id, before_id, limit),
            )
        return [Message.from_row(r) for r in reversed(rows)]

    async def unsummarized_before(self, chat_id: int, before_id: int, limit: int) -> list[Message]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM messages
            WHERE chat_id = ? AND excluded = 0 AND summarized = 0 AND id < ?
            ORDER BY id ASC LIMIT ?
            """,
            (chat_id, before_id, limit),
        )
        return [Message.from_row(r) for r in rows]

    async def count_unsummarized_before(self, chat_id: int, before_id: int) -> int:
        return int(
            await self.db.scalar(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND excluded = 0 AND summarized = 0 AND id < ?",
                (chat_id, before_id),
            )
            or 0
        )

    async def mark_summarized(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        await self.db.execute(f"UPDATE messages SET summarized = 1 WHERE id IN ({marks})", tuple(ids))

    async def mark_excluded(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        await self.db.execute(f"UPDATE messages SET excluded = 1 WHERE id IN ({marks})", tuple(ids))

    async def update_message_meta(self, message_id: int, updates: dict[str, Any]) -> None:
        row = await self.db.fetchone("SELECT meta FROM messages WHERE id = ?", (message_id,))
        if row is None:
            return
        meta = json.loads(row["meta"] or "{}")
        meta.update(updates)
        await self.db.execute(
            "UPDATE messages SET meta = ? WHERE id = ?", (json.dumps(meta, ensure_ascii=False), message_id)
        )

    async def last_message(self, chat_id: int, role: str | None = None) -> Message | None:
        if role is None:
            row = await self.db.fetchone(
                "SELECT * FROM messages WHERE chat_id = ? AND excluded = 0 AND kind != 'reaction' "
                "ORDER BY id DESC LIMIT 1",
                (chat_id,),
            )
        else:
            row = await self.db.fetchone(
                "SELECT * FROM messages WHERE chat_id = ? AND role = ? AND excluded = 0 AND kind != 'reaction' "
                "ORDER BY id DESC LIMIT 1",
                (chat_id, role),
            )
        return Message.from_row(row) if row else None

    async def count_messages(self, chat_id: int | None = None) -> int:
        if chat_id is None:
            return int(await self.db.scalar("SELECT COUNT(*) FROM messages") or 0)
        return int(await self.db.scalar("SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,)) or 0)

    async def recent_assistant_turns(self, chat_id: int, turns: int = 6) -> list[list[str]]:
        """Sofia's last N turns, each as a list of bubbles (oldest first)."""
        rows = await self.db.fetchall(
            """
            SELECT turn_id, content FROM messages
            WHERE chat_id = ? AND role = 'assistant' AND excluded = 0 AND kind != 'reaction'
            ORDER BY id DESC LIMIT ?
            """,
            (chat_id, turns * 4),
        )
        grouped: list[tuple[str | None, list[str]]] = []
        for row in rows:
            if grouped and grouped[-1][0] == row["turn_id"] and row["turn_id"] is not None:
                grouped[-1][1].insert(0, row["content"])
            else:
                grouped.append((row["turn_id"], [row["content"]]))
        return [bubbles for _, bubbles in reversed(grouped[:turns])]

    async def messages_with_keywords_since(self, chat_id: int, role: str, since: datetime) -> list[Message]:
        rows = await self.db.fetchall(
            "SELECT * FROM messages WHERE chat_id = ? AND role = ? AND created_at >= ? AND excluded = 0",
            (chat_id, role, to_iso(since)),
        )
        return [Message.from_row(r) for r in rows]

    async def all_messages(self) -> list[Message]:
        rows = await self.db.fetchall("SELECT * FROM messages ORDER BY id")
        return [Message.from_row(r) for r in rows]

    # ------------------------------------------------------------------ memories
    async def add_memory(self, mem: NewMemory) -> int:
        now = to_iso(self.clock())
        lastrowid, _ = await self.db.execute(
            """
            INSERT INTO memories
                (subject, category, content, normalized, importance, confidence, created_at, updated_at,
                 source_message_id, event_date, expires_at, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mem.subject,
                mem.category,
                mem.content,
                normalize(mem.content),
                float(mem.importance),
                float(mem.confidence),
                now,
                now,
                mem.source_message_id,
                mem.event_date.isoformat() if mem.event_date else None,
                to_iso(mem.expires_at) if mem.expires_at else None,
                pack_embedding(mem.embedding),
            ),
        )
        assert lastrowid is not None
        return lastrowid

    async def update_memory(
        self,
        memory_id: int,
        *,
        content: str | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        event_date: date | None = None,
        embedding: list[float] | None = None,
        category: str | None = None,
        consolidated: bool | None = None,
    ) -> None:
        sets: list[str] = ["updated_at = ?"]
        params: list[Any] = [to_iso(self.clock())]
        if content is not None:
            sets += ["content = ?", "normalized = ?"]
            params += [content, normalize(content)]
            if embedding is None:
                sets.append("embedding = NULL")
        if importance is not None:
            sets.append("importance = ?")
            params.append(float(importance))
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(float(confidence))
        if event_date is not None:
            sets.append("event_date = ?")
            params.append(event_date.isoformat())
        if embedding is not None:
            sets.append("embedding = ?")
            params.append(pack_embedding(embedding))
        if category is not None:
            sets.append("category = ?")
            params.append(category)
        if consolidated is not None:
            sets.append("consolidated = ?")
            params.append(int(consolidated))
        params.append(memory_id)
        await self.db.execute(f"UPDATE memories SET {', '.join(sets)} WHERE id = ?", tuple(params))

    async def get_memory(self, memory_id: int) -> Memory | None:
        row = await self.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return Memory.from_row(row) if row else None

    async def list_memories(self, subject: str | None = None, *, active_only: bool = True) -> list[Memory]:
        clauses, params = [], []
        if subject is not None:
            clauses.append("subject = ?")
            params.append(subject)
        if active_only:
            clauses.append("active = 1")
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(to_iso(self.clock()))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self.db.fetchall(f"SELECT * FROM memories {where} ORDER BY id", tuple(params))
        return [Memory.from_row(r) for r in rows]

    async def count_unconsolidated(self, subject: str) -> int:
        return int(
            await self.db.scalar(
                "SELECT COUNT(*) FROM memories WHERE subject = ? AND active = 1 AND consolidated = 0", (subject,)
            )
            or 0
        )

    async def deactivate_memories(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        await self.db.execute(
            f"UPDATE memories SET active = 0, updated_at = ? WHERE id IN ({marks})",
            (to_iso(self.clock()), *ids),
        )

    async def delete_memories(self, ids: Sequence[int]) -> int:
        """Hard delete (used by /forget — forgotten means gone)."""
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        _, rowcount = await self.db.execute(f"DELETE FROM memories WHERE id IN ({marks})", tuple(ids))
        return rowcount

    async def touch_memories(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        await self.db.execute(
            f"UPDATE memories SET last_referenced_at = ?, reference_count = reference_count + 1 WHERE id IN ({marks})",
            (to_iso(self.clock()), *ids),
        )

    async def purge_expired_memories(self) -> int:
        _, rowcount = await self.db.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (to_iso(self.clock()),)
        )
        return rowcount

    async def mark_all_consolidated(self, subject: str) -> None:
        await self.db.execute("UPDATE memories SET consolidated = 1 WHERE subject = ? AND active = 1", (subject,))

    # ------------------------------------------------------------------ episodes
    async def add_episode(
        self,
        *,
        title: str,
        summary: str,
        tone: str,
        importance: float,
        tags: list[str],
        started_at: datetime,
        ended_at: datetime,
        embedding: list[float] | None = None,
    ) -> int:
        lastrowid, _ = await self.db.execute(
            """
            INSERT INTO episodes (title, summary, tone, importance, tags, started_at, ended_at, created_at, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                summary,
                tone,
                float(importance),
                json.dumps(tags, ensure_ascii=False),
                to_iso(started_at),
                to_iso(ended_at),
                to_iso(self.clock()),
                pack_embedding(embedding),
            ),
        )
        assert lastrowid is not None
        return lastrowid

    async def list_episodes(self) -> list[Episode]:
        rows = await self.db.fetchall("SELECT * FROM episodes ORDER BY ended_at")
        return [Episode.from_row(r) for r in rows]

    async def delete_episodes(self, ids: Sequence[int]) -> int:
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        _, rowcount = await self.db.execute(f"DELETE FROM episodes WHERE id IN ({marks})", tuple(ids))
        return rowcount

    async def touch_episodes(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        await self.db.execute(
            f"UPDATE episodes SET last_referenced_at = ? WHERE id IN ({marks})", (to_iso(self.clock()), *ids)
        )

    # ------------------------------------------------------------------ threads
    async def open_thread(
        self,
        content: str,
        *,
        importance: float = 0.5,
        due_date: date | None = None,
        source_message_id: int | None = None,
    ) -> int:
        now = to_iso(self.clock())
        lastrowid, _ = await self.db.execute(
            """
            INSERT INTO threads (content, status, importance, due_date, created_at, updated_at, source_message_id)
            VALUES (?, 'open', ?, ?, ?, ?, ?)
            """,
            (content, importance, due_date.isoformat() if due_date else None, now, now, source_message_id),
        )
        assert lastrowid is not None
        return lastrowid

    async def set_thread_status(self, thread_id: int, status: str) -> bool:
        _, rowcount = await self.db.execute(
            "UPDATE threads SET status = ?, updated_at = ? WHERE id = ?", (status, to_iso(self.clock()), thread_id)
        )
        return rowcount > 0

    async def list_threads(self, status: str | None = "open") -> list[Thread]:
        if status is None:
            rows = await self.db.fetchall("SELECT * FROM threads ORDER BY id")
        else:
            rows = await self.db.fetchall("SELECT * FROM threads WHERE status = ? ORDER BY id", (status,))
        return [Thread.from_row(r) for r in rows]

    async def stale_old_threads(self, max_age: timedelta) -> int:
        cutoff = to_iso(self.clock() - max_age)
        today = self.clock().date().isoformat()
        _, rowcount = await self.db.execute(
            """
            UPDATE threads SET status = 'stale', updated_at = ?
            WHERE status = 'open' AND updated_at < ? AND (due_date IS NULL OR due_date < ?)
            """,
            (to_iso(self.clock()), cutoff, today),
        )
        return rowcount

    # ------------------------------------------------------------------ state
    async def load_state(self) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT data FROM relationship_state WHERE id = 1")
        return json.loads(row["data"]) if row else None

    async def save_state(self, data: dict[str, Any]) -> None:
        await self.db.execute(
            """
            INSERT INTO relationship_state (id, data, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
            """,
            (json.dumps(data, ensure_ascii=False), to_iso(self.clock())),
        )

    # ------------------------------------------------------------------ settings
    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        value = await self.db.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return default if value is None else str(value)

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ------------------------------------------------------------------ updates
    async def mark_update_processed(self, update_id: int) -> bool:
        """Returns True the first time an update id is seen, False for duplicates."""
        _, rowcount = await self.db.execute(
            "INSERT OR IGNORE INTO processed_updates (update_id, processed_at) VALUES (?, ?)",
            (update_id, to_iso(self.clock())),
        )
        return rowcount > 0

    async def prune_processed_updates(self, older_than: timedelta = timedelta(days=7)) -> None:
        await self.db.execute(
            "DELETE FROM processed_updates WHERE processed_at < ?", (to_iso(self.clock() - older_than),)
        )

    # ------------------------------------------------------------------ proactive
    async def log_proactive(self, reason: str) -> None:
        await self.db.execute(
            "INSERT INTO proactive_log (sent_at, reason) VALUES (?, ?)", (to_iso(self.clock()), reason)
        )

    async def proactive_sent_since(self, since: datetime) -> int:
        return int(await self.db.scalar("SELECT COUNT(*) FROM proactive_log WHERE sent_at >= ?", (to_iso(since),)) or 0)

    async def last_proactive_at(self) -> datetime | None:
        value = await self.db.scalar("SELECT sent_at FROM proactive_log ORDER BY id DESC LIMIT 1")
        return from_iso(value) if value else None

    # ------------------------------------------------------------------ reset / export
    async def reset_all(self) -> None:
        """Erase conversation history, memories, episodes, threads and relationship state.

        Settings (e.g. the proactive preference) are kept: they are preferences, not memories.
        """
        async with self.db.transaction():
            for table in ("messages", "memories", "episodes", "threads", "relationship_state", "proactive_log"):
                await self.db.execute(f"DELETE FROM {table}")
            await self.db.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('messages', 'memories', 'episodes', 'threads', 'proactive_log')"
            )
        await self.db.execute("VACUUM")

    async def export_all(self) -> dict[str, Any]:
        messages = [
            {
                "id": m.id,
                "chat_id": m.chat_id,
                "role": "bram" if m.role == "user" else "sofia",
                "kind": m.kind,
                "content": m.content,
                "telegram_message_id": m.telegram_message_id,
                "reply_to_telegram_message_id": m.reply_to_telegram_message_id,
                "meta": m.meta,
                "created_at": m.created_at.isoformat(),
                "summarized": m.summarized,
                "excluded": m.excluded,
            }
            for m in await self.all_messages()
        ]
        memories = [m.public_dict() for m in await self.list_memories(active_only=False)]
        episodes = [e.public_dict() for e in await self.list_episodes()]
        threads = [t.public_dict() for t in await self.list_threads(status=None)]
        settings_rows = await self.db.fetchall("SELECT key, value FROM settings ORDER BY key")
        proactive_rows = await self.db.fetchall("SELECT sent_at, reason FROM proactive_log ORDER BY id")
        return {
            "format": "sofia-export",
            "version": 1,
            "exported_at": to_iso(self.clock()),
            "messages": messages,
            "memories": memories,
            "episodes": episodes,
            "threads": threads,
            "relationship_state": await self.load_state(),
            "settings": {r["key"]: r["value"] for r in settings_rows},
            "proactive_log": [{"sent_at": r["sent_at"], "reason": r["reason"]} for r in proactive_rows],
        }

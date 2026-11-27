"""Thin async SQLite layer on top of aiosqlite.

One connection, autocommit mode, and a single asyncio lock that serializes
writes. Multi-statement operations use `transaction()`, which holds the lock
for the whole BEGIN..COMMIT block so concurrent coroutines can't interleave.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections.abc import AsyncIterator, Iterable, Sequence
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA_VERSION = 1
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_in_transaction: contextvars.ContextVar[bool] = contextvars.ContextVar("sofia_db_in_tx", default=False)


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def connect(self) -> None:
        if self._conn is not None:
            return
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode = WAL")
            await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self.init_schema()

    async def init_schema(self) -> None:
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        async with self._write_lock:
            await self.conn.executescript(sql)
            await self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # --- writes -------------------------------------------------------------
    async def execute(self, sql: str, params: Sequence[Any] = ()) -> tuple[int | None, int]:
        """Execute a write. Returns (lastrowid, rowcount)."""
        if _in_transaction.get():
            cursor = await self.conn.execute(sql, params)
            return cursor.lastrowid, cursor.rowcount
        async with self._write_lock:
            cursor = await self.conn.execute(sql, params)
            return cursor.lastrowid, cursor.rowcount

    async def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        if _in_transaction.get():
            await self.conn.executemany(sql, rows)
            return
        async with self._write_lock:
            await self.conn.executemany(sql, rows)

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        if _in_transaction.get():
            yield
            return
        async with self._write_lock:
            token = _in_transaction.set(True)
            await self.conn.execute("BEGIN")
            try:
                yield
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            else:
                await self.conn.execute("COMMIT")
            finally:
                _in_transaction.reset(token)

    # --- reads --------------------------------------------------------------
    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return list(rows)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = await self.fetchone(sql, params)
        return None if row is None else row[0]

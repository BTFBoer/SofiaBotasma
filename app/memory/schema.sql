-- Sofia companion database schema (SQLite).
-- All timestamps are ISO-8601 UTC strings; dates are YYYY-MM-DD.

-- A. Conversation log (verbatim). The recent window is sent to the model;
--    older messages are folded into episodes (summarized = 1) but kept for /export.
CREATE TABLE IF NOT EXISTS messages (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id                      INTEGER NOT NULL,
    role                         TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    kind                         TEXT    NOT NULL DEFAULT 'text',
    content                      TEXT    NOT NULL,
    telegram_message_id          INTEGER,
    reply_to_telegram_message_id INTEGER,
    meta                         TEXT    NOT NULL DEFAULT '{}',
    turn_id                      TEXT,
    created_at                   TEXT    NOT NULL,
    summarized                   INTEGER NOT NULL DEFAULT 0,
    excluded                     INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_telegram
    ON messages (chat_id, role, telegram_message_id)
    WHERE telegram_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_messages_chat ON messages (chat_id, id);

-- B/D/E. Long-term memories.
--   subject = 'bram'          facts learned about Bram
--   subject = 'sofia'         things Sofia has established about herself (consistency)
--   subject = 'relationship'  inside jokes, pet names, shared themes, boundaries, events between them
CREATE TABLE IF NOT EXISTS memories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    subject             TEXT    NOT NULL CHECK (subject IN ('bram', 'sofia', 'relationship')),
    category            TEXT    NOT NULL,
    content             TEXT    NOT NULL,
    normalized          TEXT    NOT NULL,
    importance          REAL    NOT NULL,
    confidence          REAL    NOT NULL,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    last_referenced_at  TEXT,
    reference_count     INTEGER NOT NULL DEFAULT 0,
    source_message_id   INTEGER,
    event_date          TEXT,
    expires_at          TEXT,
    embedding           BLOB,
    active              INTEGER NOT NULL DEFAULT 1,
    consolidated        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_memories_subject ON memories (subject, active);
CREATE INDEX IF NOT EXISTS ix_memories_event ON memories (event_date) WHERE event_date IS NOT NULL;

-- C. Episodic memory: summaries of conversations and moments.
CREATE TABLE IF NOT EXISTS episodes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT    NOT NULL,
    summary             TEXT    NOT NULL,
    tone                TEXT    NOT NULL DEFAULT '',
    importance          REAL    NOT NULL DEFAULT 0.5,
    tags                TEXT    NOT NULL DEFAULT '[]',
    started_at          TEXT    NOT NULL,
    ended_at            TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,
    last_referenced_at  TEXT,
    embedding           BLOB
);

-- Unresolved conversational threads.
CREATE TABLE IF NOT EXISTS threads (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    content             TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'stale')),
    importance          REAL    NOT NULL DEFAULT 0.5,
    due_date            TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    source_message_id   INTEGER
);
CREATE INDEX IF NOT EXISTS ix_threads_status ON threads (status);

-- Relationship + mood state (single row, JSON).
CREATE TABLE IF NOT EXISTS relationship_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    data        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Small key/value settings (e.g. proactive on/off).
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Telegram update de-duplication.
CREATE TABLE IF NOT EXISTS processed_updates (
    update_id     INTEGER PRIMARY KEY,
    processed_at  TEXT NOT NULL
);

-- Spontaneous messages that were actually sent (for rate limiting).
CREATE TABLE IF NOT EXISTS proactive_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at   TEXT NOT NULL,
    reason    TEXT NOT NULL DEFAULT ''
);

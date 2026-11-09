"""Ordered SQLite migrations. Statements must not drop existing user data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


INITIAL_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        provider TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_conversation
        ON messages(conversation_id, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]',
        source_conversation_id TEXT,
        source_message_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(source_conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
        FOREIGN KEY(source_message_id) REFERENCES messages(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)
    """,
)


MIGRATIONS = (
    Migration(1, "initial conversations messages and memories", INITIAL_TABLES),
    Migration(
        2,
        "model usage context metadata and connection test history",
        (
            """
            ALTER TABLE conversations
                ADD COLUMN provider TEXT NOT NULL DEFAULT 'mock'
            """,
            """
            ALTER TABLE conversations
                ADD COLUMN model TEXT NOT NULL DEFAULT 'mock-1'
            """,
            """ALTER TABLE messages ADD COLUMN model TEXT""",
            """ALTER TABLE messages ADD COLUMN input_tokens INTEGER""",
            """ALTER TABLE messages ADD COLUMN output_tokens INTEGER""",
            """ALTER TABLE messages ADD COLUMN truncated BOOLEAN NOT NULL DEFAULT 0""",
            """ALTER TABLE messages ADD COLUMN finish_reason TEXT""",
            """ALTER TABLE messages ADD COLUMN context_messages INTEGER""",
            """ALTER TABLE messages ADD COLUMN context_truncated BOOLEAN NOT NULL DEFAULT 0""",
            """ALTER TABLE messages ADD COLUMN retrieved_memory_count INTEGER""",
            """
            CREATE TABLE IF NOT EXISTS connection_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'local',
                external INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_connection_tests_created ON connection_tests(created_at, id)""",
        ),
    ),
)

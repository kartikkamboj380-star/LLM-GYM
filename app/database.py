"""SQLite persistence and transactional, data-preserving schema migrations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .migrations import MIGRATIONS, Migration


# Kept for compatibility with tools that inspected the original schema constant.
SCHEMA = ";\n".join(MIGRATIONS[0].statements) + ";"


class DatabaseMigrationError(RuntimeError):
    pass


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _has_table(connection: sqlite3.Connection, name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone() is not None

    @classmethod
    def _has_complete_legacy_schema(cls, connection: sqlite3.Connection) -> bool:
        return all(cls._has_table(connection, table) for table in ("conversations", "messages", "memories"))

    @classmethod
    def _has_any_legacy_table(cls, connection: sqlite3.Connection) -> bool:
        return any(cls._has_table(connection, table) for table in ("conversations", "messages", "memories"))

    @staticmethod
    def _apply(connection: sqlite3.Connection, migration: Migration) -> None:
        """Apply one migration atomically; executescript is intentionally avoided."""

        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                ),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise DatabaseMigrationError(
                f"Migration {migration.version} ({migration.name}) failed; transaction rolled back"
            ) from exc

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       version INTEGER PRIMARY KEY,
                       name TEXT NOT NULL,
                       applied_at TEXT NOT NULL
                   )"""
            )
            connection.commit()
            applied = {
                row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
            }
            if not applied and self._has_any_legacy_table(connection):
                if not self._has_complete_legacy_schema(connection):
                    raise DatabaseMigrationError(
                        "Partial legacy schema detected; automatic migration stopped to protect records"
                    )
                # Databases created by LLM-GYM 0.1 predate schema_migrations. Their
                # complete schema is version 1, so record it without rebuilding tables.
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (
                        1,
                        "baseline existing 0.1 schema",
                        datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    ),
                )
                connection.commit()
                applied.add(1)
            for migration in MIGRATIONS:
                if migration.version not in applied:
                    if migration.version <= max(applied, default=0):
                        raise DatabaseMigrationError(
                            f"Migration history is missing version {migration.version}"
                        )
                    self._apply(connection, migration)

    def schema_version(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]

    def healthcheck(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1

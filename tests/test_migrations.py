import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import SCHEMA, Database, DatabaseMigrationError
from app.migrations import MIGRATIONS, Migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "migration.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_new_database_is_versioned_and_initialization_is_idempotent(self):
        database = Database(self.path)
        self.assertEqual(MIGRATIONS[-1].version, database.schema_version())
        self.assertTrue(database.healthcheck())
        Database(self.path)
        with database.connect() as connection:
            versions = connection.execute("SELECT version FROM schema_migrations").fetchall()
        self.assertEqual([migration.version for migration in MIGRATIONS], [row[0] for row in versions])
        with database.connect() as connection:
            message_columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            conversation_columns = {row[1] for row in connection.execute("PRAGMA table_info(conversations)")}
            history_table = connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'connection_tests'").fetchone()
        self.assertTrue({
            "model", "input_tokens", "output_tokens", "truncated", "finish_reason",
            "context_messages", "context_truncated", "retrieved_memory_count",
        } <= message_columns)
        self.assertTrue({"provider", "model"} <= conversation_columns)
        self.assertIsNotNone(history_table)

    def test_complete_legacy_database_is_baselines_without_data_loss(self):
        with sqlite3.connect(self.path) as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at) VALUES ('legacy', 'Legacy chat', '2026-01-01', '2026-01-01')"
            )
            connection.execute(
                "INSERT INTO memories(id, content, tags, created_at, updated_at) VALUES ('fact', 'Keep me', '[]', '2026-01-01', '2026-01-01')"
            )
        database = Database(self.path)
        self.assertEqual(MIGRATIONS[-1].version, database.schema_version())
        with database.connect() as connection:
            title = connection.execute("SELECT title FROM conversations WHERE id = 'legacy'").fetchone()[0]
            content = connection.execute("SELECT content FROM memories WHERE id = 'fact'").fetchone()[0]
            migration_name = connection.execute("SELECT name FROM schema_migrations WHERE version = 1").fetchone()[0]
        self.assertEqual("Legacy chat", title)
        self.assertEqual("Keep me", content)
        self.assertIn("baseline", migration_name)

    def test_partial_legacy_schema_fails_closed(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY)")
        with self.assertRaises(DatabaseMigrationError):
            Database(self.path)

    def test_failed_migration_rolls_back_all_of_its_statements(self):
        database = Database(self.path)
        broken = Migration(
            MIGRATIONS[-1].version + 1,
            "deliberate test failure",
            ("CREATE TABLE migration_probe(id INTEGER)", "INSERT INTO missing_table VALUES (1)"),
        )
        with patch("app.database.MIGRATIONS", (*MIGRATIONS, broken)):
            with self.assertRaises(DatabaseMigrationError):
                Database(self.path)
        with database.connect() as connection:
            probe = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'migration_probe'"
            ).fetchone()
        self.assertIsNone(probe)
        self.assertEqual(MIGRATIONS[-1].version, database.schema_version())


if __name__ == "__main__":
    unittest.main()

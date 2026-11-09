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
        self.assertEqual(1, database.schema_version())
        self.assertTrue(database.healthcheck())
        Database(self.path)
        with database.connect() as connection:
            versions = connection.execute("SELECT version FROM schema_migrations").fetchall()
        self.assertEqual([1], [row[0] for row in versions])

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
        self.assertEqual(1, database.schema_version())
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
            2,
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
        self.assertEqual(1, database.schema_version())


if __name__ == "__main__":
    unittest.main()

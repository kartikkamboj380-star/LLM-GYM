from pathlib import Path

from app.config import Settings


def test_settings(directory: str) -> Settings:
    root = Path(directory)
    return Settings(data_dir=root, database_path=root / "test.db", default_provider="mock")

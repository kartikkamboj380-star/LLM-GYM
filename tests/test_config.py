import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings, load_env_file


class ConfigTests(unittest.TestCase):
    def test_env_file_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("AI_PROVIDER=gemini\nOPENAI_API_KEY=file-value\n")
            with patch.dict(os.environ, {"AI_PROVIDER": "mock"}, clear=True):
                load_env_file(path)
                self.assertEqual("mock", os.environ["AI_PROVIDER"])
                self.assertEqual("file-value", os.environ["OPENAI_API_KEY"])

    def test_invalid_timeout_is_rejected(self):
        with patch.dict(os.environ, {"AI_REQUEST_TIMEOUT": "999"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_database_path_defaults_to_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LLM_GYM_DATA_DIR": directory}, clear=True):
                settings = Settings.from_env()
                self.assertEqual(Path(directory) / "llm_gym.db", settings.database_path)


if __name__ == "__main__":
    unittest.main()

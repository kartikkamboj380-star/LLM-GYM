import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.automation import AutomationConfig, ExecutionLog
from app.designarena import DesignArenaClient
from app.providers.base import ProviderError


class AutomationConfigTests(unittest.TestCase):
    def test_valid_config(self):
        config = AutomationConfig.from_dict({"url": "https://example.com", "actions": [{"type": "wait_for", "selector": "h1"}], "timeout_seconds": 5, "retries": 1})
        self.assertEqual(5, config.timeout_seconds)
        self.assertEqual("wait_for", config.actions[0]["type"])

    def test_fixed_wait_and_unsupported_actions_are_not_available(self):
        with self.assertRaises(ValueError):
            AutomationConfig.from_dict({"url": "https://example.com", "actions": [{"type": "sleep", "selector": "h1"}]})

    def test_fill_requires_value_and_selector(self):
        with self.assertRaises(ValueError):
            AutomationConfig.from_dict({"url": "https://example.com", "actions": [{"type": "fill", "selector": "#email"}]})

    def test_execution_log_is_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            log = ExecutionLog()
            log.add("completed", count=1)
            log.write(path)
            self.assertEqual("completed", json.loads(path.read_text())["event"])


class DesignArenaTests(unittest.TestCase):
    @patch("app.designarena.client.request_json")
    def test_only_documented_get_paths_are_called(self, request):
        request.return_value = {"success": True, "data": []}
        client = DesignArenaClient("secret")
        client.list_arenas()
        client.list_models()
        client.leaderboard("models", "website")
        urls = [call.args[1] for call in request.call_args_list]
        self.assertEqual([
            "https://www.designarena.ai/api/v1/arenas",
            "https://www.designarena.ai/api/v1/models",
            "https://www.designarena.ai/api/v1/leaderboard/models/website",
        ], urls)
        self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))

    def test_key_is_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ProviderError):
                DesignArenaClient()

    def test_leaderboard_path_is_encoded(self):
        with patch("app.designarena.client.request_json", return_value={}) as request:
            DesignArenaClient("secret").leaderboard("models", "../private")
            self.assertTrue(request.call_args.args[1].endswith("/leaderboard/models/..%2Fprivate"))


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from app.providers.anthropic import AnthropicProvider
from app.providers.base import ProviderError
from app.providers.factory import available_providers, create_provider
from app.providers.gemini import GeminiProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

from tests.helpers import test_settings


class ProviderAdapterTests(unittest.TestCase):
    @patch("app.providers.openai_compatible.request_json")
    def test_openai_compatible_request_and_response(self, request):
        request.return_value = {"model": "test-model", "choices": [{"message": {"content": "Hello"}}], "usage": {"total_tokens": 3}}
        provider = OpenAICompatibleProvider("secret-key", "test-model")
        response = provider.generate([{"role": "user", "content": "Hi"}], "Be helpful")
        self.assertEqual("Hello", response.content)
        payload = request.call_args.kwargs["payload"]
        self.assertEqual("system", payload["messages"][0]["role"])
        self.assertEqual("Bearer secret-key", request.call_args.kwargs["headers"]["Authorization"])

    def test_custom_provider_rejects_insecure_remote_url(self):
        with self.assertRaises(ProviderError):
            OpenAICompatibleProvider("secret-key", "model", base_url="http://example.com/v1")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("app.providers.anthropic.request_json")
    def test_anthropic_adapter(self, request):
        request.return_value = {"model": "claude-test", "content": [{"type": "text", "text": "Claude response"}]}
        response = AnthropicProvider("claude-test").generate([{"role": "user", "content": "Hi"}])
        self.assertEqual("Claude response", response.content)
        self.assertNotIn("system", request.call_args.kwargs["payload"])

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("app.providers.gemini.request_json")
    def test_gemini_adapter_maps_assistant_role(self, request):
        request.return_value = {"candidates": [{"content": {"parts": [{"text": "Gemini response"}]}}]}
        provider = GeminiProvider("gemini-test")
        response = provider.generate([{"role": "assistant", "content": "Earlier"}, {"role": "user", "content": "Now"}])
        self.assertEqual("Gemini response", response.content)
        self.assertEqual("model", request.call_args.kwargs["payload"]["contents"][0]["role"])

    def test_missing_credentials_fail_safely(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError):
                create_provider("openai", test_settings("/tmp"))
            with self.assertRaises(ProviderError):
                create_provider("unknown", test_settings("/tmp"))

    def test_provider_status_contains_no_secrets(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-expose"}, clear=True):
            status = available_providers(test_settings("/tmp"))
            self.assertTrue(next(item for item in status if item["id"] == "openai")["configured"])
            self.assertNotIn("do-not-expose", str(status))


if __name__ == "__main__":
    unittest.main()

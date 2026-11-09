import io
import os
import unittest
import urllib.error
from unittest.mock import patch

from app.providers._http import request_json
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

    @patch("app.providers.factory.MockProvider")
    def test_missing_external_key_does_not_fall_back_to_mock(self, mock_provider):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError) as caught:
                create_provider("openai", test_settings("/tmp"))
        self.assertEqual("missing_key", caught.exception.category)
        mock_provider.assert_not_called()

    def test_provider_status_contains_no_secrets(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-expose"}, clear=True):
            status = available_providers(test_settings("/tmp"))
            self.assertTrue(next(item for item in status if item["id"] == "openai")["configured"])
            self.assertFalse(next(item for item in status if item["id"] == "openai")["capabilities"]["streaming"])
            self.assertNotIn("do-not-expose", str(status))

    @patch("app.providers.openai_compatible.request_json")
    def test_openai_connection_uses_documented_model_get(self, request):
        request.return_value = {"id": "test-model"}
        result = OpenAICompatibleProvider("secret-key", "test-model").test_connection()
        self.assertEqual("verified", result["status"])
        self.assertEqual("model-get", result["operation"])
        self.assertEqual("GET", request.call_args.args[0])
        self.assertTrue(request.call_args.args[1].endswith("/models/test-model"))
        self.assertNotIn("payload", request.call_args.kwargs)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("app.providers.anthropic.request_json")
    def test_anthropic_connection_uses_model_get(self, request):
        request.return_value = {"id": "claude-test"}
        result = AnthropicProvider("claude-test").test_connection()
        self.assertEqual("claude-test", result["model"])
        self.assertEqual("GET", request.call_args.args[0])
        self.assertIn("/v1/models/claude-test", request.call_args.args[1])

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("app.providers.gemini.request_json")
    def test_gemini_connection_uses_model_get(self, request):
        request.return_value = {"name": "models/gemini-test"}
        result = GeminiProvider("gemini-test").test_connection()
        self.assertEqual("gemini-test", result["model"])
        self.assertEqual("GET", request.call_args.args[0])
        self.assertNotIn(":generateContent", request.call_args.args[1])

    @patch("app.providers.openai_compatible.request_json")
    def test_openai_length_finish_is_recorded_as_truncation(self, request):
        request.return_value = {
            "model": "test-model",
            "choices": [{"message": {"content": "Partial"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }
        response = OpenAICompatibleProvider("secret-key", "test-model").generate([{"role": "user", "content": "Hi"}])
        self.assertTrue(response.truncated)
        self.assertEqual(4, response.usage["input_tokens"])
        self.assertEqual(2, response.usage["output_tokens"])

    def test_mock_connection_is_local(self):
        result = create_provider("mock", test_settings("/tmp")).test_connection()
        self.assertFalse(result["external"])
        self.assertEqual("local", result["operation"])

    @patch("app.providers._http.urllib.request.urlopen")
    def test_http_errors_are_normalized_and_redacted(self, urlopen):
        error = urllib.error.HTTPError(
            "https://example.test", 429, "rate limited", {"Retry-After": "7"},
            io.BytesIO(b'{"error": "slow down"}'),
        )
        urlopen.side_effect = error
        with self.assertRaises(ProviderError) as caught:
            request_json("GET", "https://example.test/models/test")
        self.assertEqual("rate_limit", caught.exception.category)
        self.assertEqual(7, caught.exception.retry_after)
        self.assertTrue(caught.exception.retryable)

    @patch("app.providers._http.urllib.request.urlopen")
    def test_invalid_key_is_not_retryable(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test", 401, "unauthorized", {}, io.BytesIO(b"bad key")
        )
        with self.assertRaises(ProviderError) as caught:
            request_json("GET", "https://example.test/models/test")
        self.assertEqual("invalid_key", caught.exception.category)
        self.assertFalse(caught.exception.retryable)

    @patch("app.providers._http.urllib.request.urlopen")
    def test_every_http_error_category_is_classified(self, urlopen):
        cases = {
            400: ("invalid_request", False),
            401: ("invalid_key", False),
            403: ("permission_denied", False),
            404: ("model_unavailable", False),
            408: ("network", True),
            429: ("rate_limit", True),
            500: ("upstream_unavailable", True),
            503: ("upstream_unavailable", True),
        }
        for status, (category, retryable) in cases.items():
            with self.subTest(status=status):
                urlopen.side_effect = urllib.error.HTTPError(
                    "https://example.test", status, "failure", {}, io.BytesIO(b'{"error": "bounded"}')
                )
                with self.assertRaises(ProviderError) as caught:
                    request_json("GET", "https://example.test/models/test")
                self.assertEqual(category, caught.exception.category)
                self.assertEqual(retryable, caught.exception.retryable)
                self.assertEqual(status, caught.exception.status)

    @patch("app.providers._http.urllib.request.urlopen")
    def test_network_and_secret_errors_are_safe(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("offline")
        with self.assertRaises(ProviderError) as caught:
            request_json("GET", "https://example.test/models/test")
        self.assertEqual("network", caught.exception.category)
        self.assertTrue(caught.exception.retryable)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "server-secret-do-not-return"}):
            urlopen.side_effect = urllib.error.HTTPError(
                "https://example.test", 403, "denied", {},
                io.BytesIO(b'{"error": "server-secret-do-not-return was rejected"}'),
            )
            with self.assertRaises(ProviderError) as caught:
                request_json("GET", "https://example.test/models/test")
        self.assertEqual("permission_denied", caught.exception.category)
        self.assertNotIn("server-secret-do-not-return", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

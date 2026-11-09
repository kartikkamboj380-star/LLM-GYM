import json
import tempfile
import threading
import unittest
import urllib.error
from dataclasses import replace
import urllib.request

from app.api import create_server

from tests.helpers import test_settings


class APIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, test_settings(self.temp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type")
                status = response.status
        except urllib.error.HTTPError as error:
            raw = error.read()
            content_type = error.headers.get("Content-Type")
            status = error.code
        return status, json.loads(raw) if content_type.startswith("application/json") else raw.decode(), content_type

    def test_health_static_frontend_and_security_headers(self):
        status, health, _ = self.request("/api/health")
        self.assertEqual(200, status)
        self.assertEqual("ok", health["status"])
        self.assertTrue(health["database"])
        self.assertEqual(2, health["schema_version"])
        self.assertEqual("0.1.0", health["version"])
        self.assertTrue(health["providers"]["mock"])
        self.assertFalse(health["providers"]["openai"])
        with urllib.request.urlopen(self.base + "/", timeout=3) as response:
            html = response.read().decode()
            self.assertIn("LLM-GYM", html)
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_complete_chat_and_memory_api_workflow(self):
        status, conversation, _ = self.request("/api/conversations", "POST", {})
        self.assertEqual(201, status)
        conversation_id = conversation["id"]
        status, chat, _ = self.request(
            f"/api/conversations/{conversation_id}/messages",
            "POST",
            {"content": "Remember that my favorite language is Python", "provider": "mock"},
        )
        self.assertEqual(200, status)
        self.assertEqual("mock", chat["assistant_message"]["provider"])

        status, extraction, _ = self.request("/api/memory/extract", "POST", {"conversation_id": conversation_id})
        self.assertEqual(200, status)
        self.assertEqual(1, extraction["count"])
        status, found, _ = self.request("/api/memory?q=favorite%20language")
        self.assertEqual(200, status)
        self.assertTrue(any("Python" in item["content"] for item in found["memories"]))

        status, second_chat, _ = self.request(
            f"/api/conversations/{conversation_id}/messages",
            "POST",
            {"content": "What is my favorite language?", "provider": "mock"},
        )
        self.assertEqual(200, status)
        self.assertEqual(1, len(second_chat["retrieved_memories"]))
        status, loaded, _ = self.request(f"/api/conversations/{conversation_id}")
        self.assertEqual(4, len(loaded["messages"]))
        assistant = loaded["messages"][-1]
        self.assertEqual("mock-1", assistant["model"])
        self.assertIn("input_tokens", assistant)
        self.assertFalse(assistant["truncated"])
        self.assertFalse(second_chat["streaming"])

    def test_provider_catalog_local_test_and_external_confirmation(self):
        status, catalog, _ = self.request("/api/providers")
        self.assertEqual(200, status)
        self.assertFalse(catalog["streaming"])
        self.assertEqual(5, len(catalog["providers"]))
        status, result, _ = self.request("/api/providers/test", "POST", {"provider": "mock"})
        self.assertEqual(200, status)
        self.assertEqual("verified", result["status"])
        self.assertFalse(result["external"])
        status, catalog, _ = self.request("/api/providers")
        mock = next(item for item in catalog["providers"] if item["id"] == "mock")
        self.assertEqual("verified", mock["connection_status"])
        self.assertIn("tested_at", mock["last_test"])

        status, error, _ = self.request("/api/providers/test", "POST", {"provider": "openai"})
        self.assertEqual(409, status)
        self.assertEqual("EXTERNAL_CONFIRMATION_REQUIRED", error["code"])
        status, error, _ = self.request(
            "/api/providers/test", "POST", {"provider": "openai", "confirm_external": True}
        )
        self.assertEqual(400, status)
        self.assertEqual("PROVIDER_MISSING_KEY", error["code"])
        self.assertNotIn("api_key", str(error).lower())

    def test_external_provider_test_is_non_generation_and_persistent(self):
        from unittest.mock import patch

        with patch.dict("os.environ", {"OPENAI_API_KEY": "server-secret-do-not-return"}, clear=True), patch(
            "app.providers.openai_compatible.request_json", return_value={"id": "gpt-test"}
        ) as upstream:
            status, result, _ = self.request(
                "/api/providers/test", "POST", {"provider": "openai", "confirm_external": True}
            )
        self.assertEqual(200, status)
        self.assertTrue(result["external"])
        self.assertEqual("model-get", result["operation"])
        self.assertNotIn("server-secret", str(result))
        self.assertEqual("GET", upstream.call_args.args[0])
        self.assertNotIn("payload", upstream.call_args.kwargs)
        _, catalog, _ = self.request("/api/providers")
        openai = next(item for item in catalog["providers"] if item["id"] == "openai")
        self.assertEqual("verified", openai["last_test"]["status"])

    def test_conversation_provider_selection_and_response_metadata(self):
        status, conversation, _ = self.request("/api/conversations", "POST", {"provider": "MOCK"})
        self.assertEqual(201, status)
        self.assertEqual("mock", conversation["provider"])
        self.assertEqual("mock-1", conversation["model"])
        conversation_id = conversation["id"]

        status, error, _ = self.request(
            f"/api/conversations/{conversation_id}", "PATCH", {"provider": "openai"}
        )
        self.assertEqual(400, status)
        self.assertEqual("PROVIDER_MISSING_CONFIGURATION", error["code"])

        status, chat, _ = self.request(
            f"/api/conversations/{conversation_id}/messages", "POST", {"content": "Hello"}
        )
        self.assertEqual(200, status)
        self.assertFalse(chat["streaming"])
        self.assertEqual(1, chat["context"]["history_messages"])
        self.assertFalse(chat["context"]["history_truncated"])
        self.assertEqual(1, chat["assistant_message"]["context_messages"])
        _, loaded, _ = self.request(f"/api/conversations/{conversation_id}")
        assistant = loaded["messages"][-1]
        self.assertEqual("mock-1", assistant["model"])
        self.assertFalse(assistant["truncated"])
        self.assertFalse(assistant["context_truncated"])
        self.assertEqual(0, assistant["retrieved_memory_count"])
        _, markdown, _ = self.request(f"/api/conversations/{conversation_id}/export?format=markdown")
        self.assertIn("Configured model: mock-1", markdown)
        self.assertIn("Context: 1 message", markdown)

    def test_dashboard_rename_export_and_delete_conversation(self):
        _, conversation, _ = self.request("/api/conversations", "POST", {"title": "Before"})
        conversation_id = conversation["id"]
        self.request(f"/api/conversations/{conversation_id}/messages", "POST", {"content": "Hello", "provider": "mock"})
        status, dashboard, _ = self.request("/api/dashboard")
        self.assertEqual(200, status)
        self.assertEqual(1, dashboard["counts"]["conversations"])
        self.assertEqual(2, dashboard["counts"]["messages"])
        self.assertEqual("local-only", dashboard["email"]["status"])
        self.assertEqual([], dashboard["test_runs"]["recent_runs"])

        status, renamed, _ = self.request(f"/api/conversations/{conversation_id}", "PATCH", {"title": "After"})
        self.assertEqual(200, status)
        self.assertEqual("After", renamed["title"])
        status, exported, content_type = self.request(f"/api/conversations/{conversation_id}/export?format=markdown")
        self.assertEqual(200, status)
        self.assertIn("text/markdown", content_type)
        self.assertIn("# After", exported)
        self.assertIn("Hello", exported)
        status, deleted, _ = self.request(f"/api/conversations/{conversation_id}", "DELETE")
        self.assertEqual(200, status)
        self.assertTrue(deleted["deleted"])
        status, _, _ = self.request(f"/api/conversations/{conversation_id}")
        self.assertEqual(404, status)

    def test_complete_mock_email_api_workflow(self):
        status, inbox, _ = self.request("/api/email/mock/inboxes", "POST", {})
        self.assertEqual(201, status)
        inbox_id = inbox["id"]
        status, message, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}/demo", "POST", {"code_type": "alphanumeric"})
        self.assertEqual(201, status)
        self.assertIn("verification code", message["text"])
        status, result, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}/poll", "POST", {"timeout_seconds": 0})
        self.assertEqual(200, status)
        self.assertTrue(result["found"])
        self.assertRegex(result["code"], r"^[A-Z0-9]{6}$")

    def test_mock_email_lifecycle_html_rules_and_failures(self):
        status, capabilities, _ = self.request("/api/email/mock/capabilities")
        self.assertEqual(200, status)
        self.assertTrue(capabilities["expiration"])
        status, inbox, _ = self.request("/api/email/mock/inboxes", "POST", {"local_part": "api-lifecycle", "ttl_seconds": 900})
        self.assertEqual("api-lifecycle@example.test", inbox["address"])
        inbox_id = inbox["id"]
        status, demo, _ = self.request(
            f"/api/email/mock/inboxes/{inbox_id}/demo",
            "POST",
            {"code_type": "alphanumeric", "html": True},
        )
        self.assertEqual(201, status)
        self.assertIn("verification code", demo["html"])
        status, result, _ = self.request(
            f"/api/email/mock/inboxes/{inbox_id}/poll",
            "POST",
            {
                "timeout_seconds": 0,
                "backoff_multiplier": 1.5,
                "rules": {"expected_length": 6, "sender": "verification@example.test", "expected_application": "LLM-GYM"},
            },
        )
        self.assertEqual(200, status)
        self.assertEqual("verified", result["status"])
        status, fetched, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}/messages/{demo['id']}")
        self.assertEqual(demo["id"], fetched["id"])

        status, _, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}/failure", "POST", {"mode": "rate_limit"})
        self.assertEqual(200, status)
        status, error, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}/poll", "POST", {"timeout_seconds": 0})
        self.assertEqual(429, status)
        self.assertEqual("EMAIL_RATE_LIMITED", error["code"])
        status, deleted, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}", "DELETE")
        self.assertEqual(200, status)
        self.assertEqual("deleted", deleted["status"])
        status, _, _ = self.request(f"/api/email/mock/inboxes/{inbox_id}")
        self.assertEqual(404, status)

    def test_local_registration_valid_retry_expired_and_cleanup(self):
        _, inbox, _ = self.request("/api/email/mock/inboxes", "POST", {})
        status, session, _ = self.request(
            "/api/demo/register",
            "POST",
            {"email": inbox["address"], "inbox_id": inbox["id"], "scenario": "valid"},
        )
        self.assertEqual(201, status)
        self.assertNotIn("code", session)
        status, poll, _ = self.request(
            f"/api/email/mock/inboxes/{inbox['id']}/poll",
            "POST",
            {"timeout_seconds": 0, "rules": {"expected_length": 6, "expected_application": "LLM-GYM Local Demo", "expected_test_run": session["session_id"]}},
        )
        self.assertEqual("verified", poll["status"])
        wrong = "000000" if poll["code"] != "000000" else "111111"
        _, invalid, _ = self.request(f"/api/demo/sessions/{session['session_id']}/verify", "POST", {"code": wrong})
        self.assertEqual("invalid", invalid["status"])
        _, verified, _ = self.request(f"/api/demo/sessions/{session['session_id']}/verify", "POST", {"code": poll["code"]})
        self.assertEqual("verified", verified["status"])
        _, cleaned, _ = self.request(f"/api/demo/sessions/{session['session_id']}/cleanup", "POST", {})
        self.assertTrue(cleaned["inbox_deleted"])
        status, _, _ = self.request(f"/api/email/mock/inboxes/{inbox['id']}")
        self.assertEqual(404, status)

        _, expired_inbox, _ = self.request("/api/email/mock/inboxes", "POST", {})
        _, expired_session, _ = self.request(
            "/api/demo/register",
            "POST",
            {"email": expired_inbox["address"], "inbox_id": expired_inbox["id"], "scenario": "expired"},
        )
        _, expired_poll, _ = self.request(f"/api/email/mock/inboxes/{expired_inbox['id']}/poll", "POST", {"timeout_seconds": 0})
        self.assertEqual("expired", expired_poll["status"])
        self.request(f"/api/demo/sessions/{expired_session['session_id']}/cleanup", "POST", {})

    def test_demo_rejects_mismatched_email_and_serves_page(self):
        _, inbox, _ = self.request("/api/email/mock/inboxes", "POST", {})
        status, error, _ = self.request(
            "/api/demo/register", "POST", {"email": "other@example.test", "inbox_id": inbox["id"]}
        )
        self.assertEqual(400, status)
        self.assertEqual("VALIDATION_ERROR", error["code"])
        status, page, content_type = self.request("/demo")
        self.assertEqual(200, status)
        self.assertIn("Independent of Design Arena", page)
        self.assertIn("text/html", content_type)
        self.request(f"/api/email/mock/inboxes/{inbox['id']}", "DELETE")

    def test_mock_email_expiry_and_ambiguity_are_explicit(self):
        _, expired, _ = self.request("/api/email/mock/inboxes", "POST", {"ttl_seconds": 0})
        _, result, _ = self.request(f"/api/email/mock/inboxes/{expired['id']}/poll", "POST", {"timeout_seconds": 60})
        self.assertEqual("expired", result["status"])
        _, inbox, _ = self.request("/api/email/mock/inboxes", "POST", {})
        for code in ("111111", "222222"):
            self.request(
                f"/api/email/mock/inboxes/{inbox['id']}/messages",
                "POST",
                {"sender": "verification@example.test", "subject": "Test", "text": f"Verification code is {code}"},
            )
        _, result, _ = self.request(f"/api/email/mock/inboxes/{inbox['id']}/poll", "POST", {"timeout_seconds": 0})
        self.assertEqual("ambiguous", result["status"])
        self.assertIsNone(result["code"])

    def test_errors_do_not_leak_internals(self):
        status, error, _ = self.request("/api/conversations/missing")
        self.assertEqual(404, status)
        self.assertEqual("Conversation not found", error["error"])
        status, error, _ = self.request("/api/designarena/arenas")
        self.assertEqual(502, status)
        self.assertIn("DESIGNARENA_API_KEY", error["error"])
        status, error, _ = self.request("/api/not-a-real-endpoint")
        self.assertEqual(404, status)
        status, error, _ = self.request("/api/conversations", "POST", [])
        self.assertEqual(400, status)
        self.assertEqual("VALIDATION_ERROR", error["code"])
        self.assertIn("request_id", error)

        status, error, _ = self.request("/api/conversations", "POST", {"title": {"unsafe": "coercion"}})
        self.assertEqual(400, status)
        self.assertEqual("VALIDATION_ERROR", error["code"])

    def test_error_envelope_and_response_share_request_id(self):
        request = urllib.request.Request(self.base + "/api/not-a-real-endpoint")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        response = caught.exception
        payload = json.loads(response.read())
        self.assertEqual(404, response.code)
        self.assertEqual("NOT_FOUND", payload["code"])
        self.assertEqual(payload["request_id"], response.headers["X-Request-ID"])
        self.assertNotIn("Traceback", str(payload))

    def test_sensitive_endpoint_uses_configured_rate_limit(self):
        self.server.app.settings = replace(self.server.app.settings, email_rate_limit=1)
        status, _, _ = self.request("/api/email/mock/inboxes", "POST", {})
        self.assertEqual(201, status)
        status, error, _ = self.request("/api/email/mock/inboxes", "POST", {})
        self.assertEqual(429, status)
        self.assertEqual("RATE_LIMITED", error["code"])
        self.assertTrue(error["retryable"])
        self.assertGreaterEqual(error["retry_after_seconds"], 1)

    def test_path_traversal_is_not_served(self):
        status, _, _ = self.request("/../run.py")
        self.assertEqual(404, status)


if __name__ == "__main__":
    unittest.main()

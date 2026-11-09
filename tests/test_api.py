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
        self.assertEqual(1, health["schema_version"])
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

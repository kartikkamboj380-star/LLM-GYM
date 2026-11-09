import json
import tempfile
import threading
import unittest
import urllib.error
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
        self.assertEqual({"status": "ok", "database": True, "version": "0.1.0"}, health)
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

    def test_path_traversal_is_not_served(self):
        status, _, _ = self.request("/../run.py")
        self.assertEqual(404, status)


if __name__ == "__main__":
    unittest.main()

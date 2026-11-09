"""Dependency-free JSON API and same-origin static web server."""

from __future__ import annotations

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .chat import ChatService
from .config import Settings
from .database import Database
from .designarena import DesignArenaClient
from .email import MockEmailProvider, VerificationCodeParser
from .memory import MemoryExtractor, MemoryStore
from .providers import available_providers
from .providers.base import ProviderError


LOGGER = logging.getLogger(__name__)
STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
MAX_BODY_BYTES = 1_000_000


class Application:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.database_path)
        self.store = MemoryStore(self.database)
        self.chat = ChatService(self.store, settings)
        self.extractor = MemoryExtractor()
        self.email = MockEmailProvider()
        self.code_parser = VerificationCodeParser()


class APIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], app: Application):
        self.app = app
        super().__init__(address, RequestHandler)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "LLMGYM/0.1"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> Application:
        return self.server.app  # type: ignore[attr-defined]

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0:
            raise ValueError("Content-Length cannot be negative")
        if length > MAX_BODY_BYTES:
            raise ValueError("Request body exceeds 1 MB")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Request body must be valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _dispatch(self, method: str) -> None:
        try:
            parsed = urlsplit(self.path)
            if parsed.path.startswith("/api/"):
                self._api(method, parsed.path.rstrip("/") or "/", parse_qs(parsed.query))
            elif method == "GET":
                self._static(parsed.path)
            else:
                self._json(404, {"error": "Not found"})
        except KeyError as exc:
            self._json(404, {"error": str(exc).strip("'")})
        except (ValueError, TypeError) as exc:
            self._json(400, {"error": str(exc)})
        except ProviderError as exc:
            self._json(502, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            LOGGER.exception("Unhandled request error")
            self._json(500, {"error": "Internal server error"})

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def _api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "GET" and path == "/api/health":
            self._json(200, {"status": "ok", "database": self.app.database.healthcheck(), "version": "0.1.0"})
            return
        if method == "GET" and path == "/api/providers":
            self._json(200, {"default": self.app.settings.default_provider, "providers": available_providers(self.app.settings)})
            return
        if method == "GET" and path == "/api/conversations":
            self._json(200, {"conversations": self.app.store.list_conversations()})
            return
        if method == "POST" and path == "/api/conversations":
            data = self._read_json()
            conversation = self.app.store.create_conversation(str(data.get("title", "New conversation")))
            self._json(201, conversation)
            return
        match = re.fullmatch(r"/api/conversations/([^/]+)", path)
        if method == "GET" and match:
            conversation = self.app.store.get_conversation(match.group(1))
            if conversation is None:
                raise KeyError("Conversation not found")
            self._json(200, conversation)
            return
        match = re.fullmatch(r"/api/conversations/([^/]+)/messages", path)
        if method == "POST" and match:
            data = self._read_json()
            provider = data.get("provider")
            if provider is not None and not isinstance(provider, str):
                raise ValueError("Provider must be a string")
            result = self.app.chat.send(match.group(1), str(data.get("content", "")), provider)
            self._json(200, result)
            return
        if method == "GET" and path == "/api/memory":
            search = query.get("q", [""])[0]
            limit = int(query.get("limit", ["20"])[0])
            self._json(200, {"memories": self.app.store.search(search, limit)})
            return
        if method == "POST" and path == "/api/memory":
            data = self._read_json()
            tags = data.get("tags", [])
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",")]
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError("Tags must be a list of strings or a comma-separated string")
            memory = self.app.store.add_memory(str(data.get("content", "")), tags)
            self._json(201, memory)
            return
        if method == "POST" and path == "/api/memory/extract":
            data = self._read_json()
            memories = self.app.extractor.extract(self.app.store, str(data.get("conversation_id", "")))
            self._json(200, {"memories": memories, "count": len(memories)})
            return
        match = re.fullmatch(r"/api/memory/([^/]+)", path)
        if method == "DELETE" and match:
            if not self.app.store.delete_memory(match.group(1)):
                raise KeyError("Memory not found")
            self._json(200, {"deleted": True})
            return
        if method == "POST" and path == "/api/email/mock/inboxes":
            self._json(201, self.app.email.create_inbox().to_dict())
            return
        match = re.fullmatch(r"/api/email/mock/inboxes/([^/]+)/messages", path)
        if match:
            inbox_id = match.group(1)
            if method == "GET":
                self._json(200, {"messages": [message.to_dict() for message in self.app.email.get_messages(inbox_id)]})
                return
            if method == "POST":
                data = self._read_json()
                message = self.app.email.send_message(
                    inbox_id,
                    str(data.get("sender", "tests@example.test")),
                    str(data.get("subject", "")),
                    str(data.get("text", "")),
                )
                self._json(201, message.to_dict())
                return
        match = re.fullmatch(r"/api/email/mock/inboxes/([^/]+)/demo", path)
        if method == "POST" and match:
            data = self._read_json()
            message = self.app.email.send_demo_verification(match.group(1), str(data.get("code_type", "numeric")))
            self._json(201, message.to_dict())
            return
        match = re.fullmatch(r"/api/email/mock/inboxes/([^/]+)/poll", path)
        if method == "POST" and match:
            data = self._read_json()
            result = self.app.email.poll_for_code(
                match.group(1),
                timeout_seconds=float(data.get("timeout_seconds", 0)),
                interval_seconds=float(data.get("interval_seconds", 1)),
            )
            self._json(200, result)
            return
        if method == "GET" and path == "/api/designarena/arenas":
            self._json(200, DesignArenaClient(timeout=self.app.settings.request_timeout).list_arenas())
            return
        if method == "GET" and path == "/api/designarena/models":
            self._json(200, DesignArenaClient(timeout=self.app.settings.request_timeout).list_models())
            return
        if method == "GET" and path == "/api/designarena/leaderboard":
            arena = query.get("arena", [""])[0]
            category = query.get("category", [""])[0]
            self._json(200, DesignArenaClient(timeout=self.app.settings.request_timeout).leaderboard(arena, category))
            return
        self._json(404, {"error": "API endpoint not found"})

    def _static(self, path: str) -> None:
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
        }
        if path not in files:
            self._json(404, {"error": "Not found"})
            return
        filename, content_type = files[path]
        body = (STATIC_ROOT / filename).read_bytes()
        self._headers(200, content_type, len(body))
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.client_address[0], format % args)


def create_server(host: str, port: int, settings: Settings | None = None) -> APIServer:
    return APIServer((host, port), Application(settings or Settings.from_env()))

"""Dependency-free JSON API and same-origin static web server."""

from __future__ import annotations

import json
import logging
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .chat import ChatService
from .config import Settings
from .database import Database
from .designarena import DesignArenaClient
from .email import MockEmailProvider, VerificationCodeParser
from .errors import APIError
from .memory import MemoryExtractor, MemoryStore
from .rate_limit import InMemoryRateLimiter
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
        self.rate_limiter = InMemoryRateLimiter()


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

    def _headers(self, status: int, content_type: str, length: int, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Request-ID", getattr(self, "request_id", "unassigned"))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body), headers)
        self.wfile.write(body)

    @staticmethod
    def _string(data: dict, name: str, default: str | None = None) -> str:
        value = data.get(name, default)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value

    @staticmethod
    def _number(data: dict, name: str, default: float) -> float:
        value = data.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a number")
        return float(value)

    def _rate_limit(self, bucket: str, limit: int) -> None:
        self.app.rate_limiter.enforce(
            bucket,
            self.client_address[0],
            limit,
            self.app.settings.rate_limit_window,
        )

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
        self.request_id = uuid.uuid4().hex
        try:
            parsed = urlsplit(self.path)
            if parsed.path.startswith("/api/"):
                self._api(method, parsed.path.rstrip("/") or "/", parse_qs(parsed.query))
            elif method == "GET":
                self._static(parsed.path)
            else:
                raise APIError(404, "NOT_FOUND", "Not found")
        except APIError as exc:
            headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
            self._json(exc.status, exc.payload(self.request_id), headers)
        except KeyError as exc:
            error = APIError(404, "NOT_FOUND", str(exc).strip("'"))
            self._json(error.status, error.payload(self.request_id))
        except (ValueError, TypeError) as exc:
            error = APIError(400, "VALIDATION_ERROR", str(exc))
            self._json(error.status, error.payload(self.request_id))
        except ProviderError as exc:
            error = APIError(502, "PROVIDER_ERROR", str(exc), retryable=True)
            self._json(error.status, error.payload(self.request_id))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            LOGGER.exception("request_id=%s unhandled request error", self.request_id)
            error = APIError(500, "INTERNAL_ERROR", "Internal server error")
            self._json(error.status, error.payload(self.request_id))

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def _api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "GET" and path == "/api/health":
            providers = available_providers(self.app.settings)
            self._json(200, {
                "status": "ok",
                "database": self.app.database.healthcheck(),
                "schema_version": self.app.database.schema_version(),
                "version": "0.1.0",
                "providers": {provider["id"]: provider["configured"] for provider in providers},
                "email": {"mock": True, "external": False},
                "rate_limits": {"window_seconds": self.app.settings.rate_limit_window},
            })
            return
        if method == "GET" and path == "/api/providers":
            self._json(200, {"default": self.app.settings.default_provider, "providers": available_providers(self.app.settings)})
            return
        if method == "GET" and path == "/api/conversations":
            self._json(200, {"conversations": self.app.store.list_conversations()})
            return
        if method == "POST" and path == "/api/conversations":
            data = self._read_json()
            conversation = self.app.store.create_conversation(self._string(data, "title", "New conversation"))
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
            self._rate_limit("chat", self.app.settings.chat_rate_limit)
            provider = data.get("provider")
            if provider is not None and not isinstance(provider, str):
                raise ValueError("Provider must be a string")
            result = self.app.chat.send(match.group(1), self._string(data, "content"), provider)
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
            memory = self.app.store.add_memory(self._string(data, "content"), tags)
            self._json(201, memory)
            return
        if method == "POST" and path == "/api/memory/extract":
            data = self._read_json()
            memories = self.app.extractor.extract(self.app.store, self._string(data, "conversation_id"))
            self._json(200, {"memories": memories, "count": len(memories)})
            return
        match = re.fullmatch(r"/api/memory/([^/]+)", path)
        if method == "DELETE" and match:
            if not self.app.store.delete_memory(match.group(1)):
                raise KeyError("Memory not found")
            self._json(200, {"deleted": True})
            return
        if method == "POST" and path == "/api/email/mock/inboxes":
            self._rate_limit("email inbox creation", self.app.settings.email_rate_limit)
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
                    self._string(data, "sender", "tests@example.test"),
                    self._string(data, "subject", ""),
                    self._string(data, "text", ""),
                )
                self._json(201, message.to_dict())
                return
        match = re.fullmatch(r"/api/email/mock/inboxes/([^/]+)/demo", path)
        if method == "POST" and match:
            data = self._read_json()
            self._rate_limit("email demo delivery", self.app.settings.email_rate_limit)
            message = self.app.email.send_demo_verification(match.group(1), self._string(data, "code_type", "numeric"))
            self._json(201, message.to_dict())
            return
        match = re.fullmatch(r"/api/email/mock/inboxes/([^/]+)/poll", path)
        if method == "POST" and match:
            data = self._read_json()
            self._rate_limit("email polling", self.app.settings.email_rate_limit)
            result = self.app.email.poll_for_code(
                match.group(1),
                timeout_seconds=self._number(data, "timeout_seconds", 0),
                interval_seconds=self._number(data, "interval_seconds", 1),
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
        raise APIError(404, "NOT_FOUND", "API endpoint not found")

    def _static(self, path: str) -> None:
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
        }
        if path not in files:
            raise APIError(404, "NOT_FOUND", "Not found")
        filename, content_type = files[path]
        body = (STATIC_ROOT / filename).read_bytes()
        self._headers(200, content_type, len(body))
        self.wfile.write(body)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # Query strings may contain private memory searches; never log them.
        LOGGER.info(
            "request_id=%s client=%s method=%s path=%s status=%s",
            getattr(self, "request_id", "unassigned"),
            self.client_address[0],
            self.command,
            urlsplit(self.path).path,
            code,
        )

    def log_message(self, format: str, *args: Any) -> None:
        # BaseHTTPRequestHandler can include raw request lines here. Keep only metadata.
        LOGGER.info("request_id=%s http_server_event", getattr(self, "request_id", "unassigned"))


def create_server(host: str, port: int, settings: Settings | None = None) -> APIServer:
    return APIServer((host, port), Application(settings or Settings.from_env()))

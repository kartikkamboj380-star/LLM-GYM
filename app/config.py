"""Environment-based configuration. Secrets are read only on the server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path | None = None) -> None:
    """Load a small, dependency-free .env file without overriding real env vars.

    This intentionally supports simple KEY=VALUE entries, not shell execution.
    Never quote a value with a leading '#': inline comments are not supported.
    """

    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    default_provider: str = "mock"
    request_timeout: float = 30.0
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    gemini_model: str = "gemini-2.0-flash"
    compatible_model: str = "change-me"
    compatible_base_url: str = ""
    retrieval_limit: int = 4
    history_limit: int = 20
    rate_limit_window: float = 60.0
    chat_rate_limit: int = 30
    email_rate_limit: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("LLM_GYM_DATA_DIR", PROJECT_ROOT / "data")).expanduser()
        database_path = Path(os.getenv("DATABASE_PATH", data_dir / "llm_gym.db")).expanduser()
        return cls(
            data_dir=data_dir,
            database_path=database_path,
            default_provider=os.getenv("AI_PROVIDER", "mock").strip().lower(),
            request_timeout=_float_env("AI_REQUEST_TIMEOUT", 30, 1, 120),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip(),
            compatible_model=os.getenv("OPENAI_COMPATIBLE_MODEL", "change-me").strip(),
            compatible_base_url=os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").strip().rstrip("/"),
            retrieval_limit=_int_env("MEMORY_RETRIEVAL_LIMIT", 4, 1, 20),
            history_limit=_int_env("CHAT_HISTORY_LIMIT", 20, 1, 100),
            rate_limit_window=_float_env("RATE_LIMIT_WINDOW_SECONDS", 60, 1, 3600),
            chat_rate_limit=_int_env("CHAT_RATE_LIMIT_REQUESTS", 30, 1, 10000),
            email_rate_limit=_int_env("EMAIL_RATE_LIMIT_REQUESTS", 30, 1, 10000),
        )

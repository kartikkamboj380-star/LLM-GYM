"""Read-only client for Design Arena's officially documented public data API.

There is deliberately no login, prompt submission, project, voting, or account method.
"""

from __future__ import annotations

import os
from urllib.parse import quote

from app.providers._http import request_json
from app.providers.base import ProviderError


class DesignArenaClient:
    BASE_URL = "https://www.designarena.ai/api/v1"

    def __init__(self, api_key: str | None = None, timeout: float = 20):
        self.api_key = api_key or os.getenv("DESIGNARENA_API_KEY", "")
        if not self.api_key:
            raise ProviderError("Design Arena API access requires DESIGNARENA_API_KEY")
        self.timeout = timeout

    def _get(self, path: str) -> dict:
        return request_json(
            "GET",
            f"{self.BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )

    def list_arenas(self) -> dict:
        return self._get("/arenas")

    def list_models(self) -> dict:
        return self._get("/models")

    def leaderboard(self, arena: str, category: str) -> dict:
        if not arena.strip() or not category.strip():
            raise ValueError("Arena and category are required")
        # Quoting with safe='' prevents path traversal or undocumented endpoint injection.
        return self._get(f"/leaderboard/{quote(arena, safe='')}/{quote(category, safe='')}")

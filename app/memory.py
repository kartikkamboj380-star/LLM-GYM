"""Persistent conversations, searchable knowledge, and lightweight retrieval."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .database import Database


TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "do", "for", "from", "how", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "that", "the", "to", "was",
    "what", "when", "where", "which", "who", "why", "with", "you", "your",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _memory_dict(row: Any) -> dict:
    return {
        "id": row["id"],
        "content": row["content"],
        "tags": json.loads(row["tags"]),
        "source_conversation_id": row["source_conversation_id"],
        "source_message_id": row["source_message_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class MemoryStore:
    def __init__(self, database: Database):
        self.database = database

    def create_conversation(self, title: str = "New conversation") -> dict:
        clean_title = title.strip()[:200] or "New conversation"
        conversation_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, clean_title, now, now),
            )
        return {"id": conversation_id, "title": clean_title, "created_at": now, "updated_at": now}

    def list_conversations(self, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT c.*, COUNT(m.id) AS message_count
                   FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
                   GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self.database.connect() as connection:
            conversation = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if conversation is None:
                return None
            messages = connection.execute(
                "SELECT id, conversation_id, role, content, provider, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        result = dict(conversation)
        result["messages"] = [dict(row) for row in messages]
        return result

    def add_message(self, conversation_id: str, role: str, content: str, provider: str | None = None) -> dict:
        if role not in {"user", "assistant"}:
            raise ValueError("Message role must be user or assistant")
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content cannot be empty")
        if len(clean_content) > 50_000:
            raise ValueError("Message content exceeds 50,000 characters")
        now = utc_now()
        with self.database.connect() as connection:
            if connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone() is None:
                raise KeyError("Conversation not found")
            cursor = connection.execute(
                "INSERT INTO messages(conversation_id, role, content, provider, created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, role, clean_content, provider, now),
            )
            message_id = cursor.lastrowid
            if role == "user":
                connection.execute(
                    """UPDATE conversations SET updated_at = ?,
                       title = CASE WHEN title = 'New conversation' THEN ? ELSE title END
                       WHERE id = ?""",
                    (now, clean_content[:80], conversation_id),
                )
            else:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
                )
        return {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": clean_content,
            "provider": provider,
            "created_at": now,
        }

    def recent_messages(self, conversation_id: str, limit: int = 20) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, safe_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def add_memory(
        self,
        content: str,
        tags: list[str] | None = None,
        *,
        source_conversation_id: str | None = None,
        source_message_id: int | None = None,
    ) -> dict:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty")
        if len(clean_content) > 10_000:
            raise ValueError("Memory content exceeds 10,000 characters")
        clean_tags = sorted({tag.strip().lower()[:40] for tag in (tags or []) if tag.strip()})[:20]
        memory_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO memories(
                       id, content, tags, source_conversation_id, source_message_id, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory_id,
                    clean_content,
                    json.dumps(clean_tags, ensure_ascii=False),
                    source_conversation_id,
                    source_message_id,
                    now,
                    now,
                ),
            )
        return {
            "id": memory_id,
            "content": clean_content,
            "tags": clean_tags,
            "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id,
            "created_at": now,
            "updated_at": now,
        }

    def search(self, query: str = "", limit: int = 10) -> list[dict]:
        """Rank lexical matches locally; no embedding service or paid API required.

        Phrase matches rank highest, followed by distinctive token coverage. A blank
        query lists recent entries. The scan is bounded for small-device performance.
        """

        safe_limit = max(1, min(limit, 50))
        normalized = query.strip().lower()
        tokens = [token for token in TOKEN_RE.findall(normalized) if len(token) > 1 and token not in STOP_WORDS]
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT 1000"
            ).fetchall()
        if not normalized:
            return [_memory_dict(row) for row in rows[:safe_limit]]
        ranked: list[tuple[float, str, dict]] = []
        for row in rows:
            item = _memory_dict(row)
            haystack = f"{item['content']} {' '.join(item['tags'])}".lower()
            if not tokens:
                continue
            matched = sum(1 for token in tokens if token in haystack)
            if not matched:
                continue
            score = matched / len(tokens)
            if normalized in haystack:
                score += 2.0
            score += sum(min(haystack.count(token), 3) for token in tokens) * 0.05
            ranked.append((score, item["created_at"], item))
        ranked.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        results = []
        for score, _, item in ranked[:safe_limit]:
            item["score"] = round(score, 4)
            results.append(item)
        return results

    def delete_memory(self, memory_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0


class MemoryExtractor:
    """Conservative extraction from a user's own, explicitly authorized chat.

    Only explicit remember/note statements and simple 'my ... is ...' facts are
    extracted. Likely credentials are rejected rather than persisted as memories.
    """

    SENSITIVE = re.compile(r"\b(password|passcode|api[ _-]?key|secret|access token|private key|authorization)\b", re.I)
    REMEMBER = re.compile(r"\b(?:remember(?: that)?|note(?: that)?)\s*[:\-]?\s+(.+)", re.I)
    PROFILE = re.compile(r"\bmy\s+([a-z][a-z _-]{1,50}?)\s+(?:is|are)\s+([^.!?\n]{1,300})", re.I)

    def extract(self, store: MemoryStore, conversation_id: str) -> list[dict]:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise KeyError("Conversation not found")
        existing = {
            row["content"].casefold()
            for row in store.search("", 50)
            if row.get("source_conversation_id") == conversation_id
        }
        extracted = []
        for message in conversation["messages"]:
            if message["role"] != "user":
                continue
            candidates: list[tuple[str, list[str]]] = []
            remember = self.REMEMBER.search(message["content"])
            if remember:
                candidates.append((remember.group(1).strip(), ["extracted"]))
            profile = self.PROFILE.search(message["content"])
            if profile:
                candidates.append((f"My {profile.group(1).strip()} is {profile.group(2).strip()}", ["profile", "extracted"]))
            for content, tags in candidates:
                content = content[:1000].strip()
                if not content or self.SENSITIVE.search(content) or content.casefold() in existing:
                    continue
                extracted.append(
                    store.add_memory(
                        content,
                        tags,
                        source_conversation_id=conversation_id,
                        source_message_id=message["id"],
                    )
                )
                existing.add(content.casefold())
        return extracted

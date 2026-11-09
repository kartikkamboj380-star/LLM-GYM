"""Optional mail.tm adapter for explicitly authorized, documented API testing.

Mail.tm accounts are not guaranteed to receive OTPs. Use one test account only,
follow its terms, and never use this adapter to evade another service's limits.
"""

from __future__ import annotations

import os
import secrets
import string
import uuid
from datetime import datetime, timezone

from app.providers._http import request_json

from app.providers.base import ProviderError

from .base import EmailMessage, EmailProvider, Inbox


class MailTmProvider(EmailProvider):
    name = "mailtm"

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("MAILTM_BASE_URL", "https://api.mail.tm")).rstrip("/")
        self.timeout = float(os.getenv("EMAIL_REQUEST_TIMEOUT", "20"))
        self._tokens: dict[str, str] = {}
        self._account_ids: dict[str, str] = {}
        self._inboxes: dict[str, Inbox] = {}

    def capabilities(self) -> dict:
        return {
            "create": True,
            "inbox_info": True,
            "list_messages": True,
            "get_message": True,
            "delete": True,
            "expiration": False,
            "cancellation": False,
            "real_delivery": True,
            "documented_general_quota_qps": 8,
            "attribution": "https://mail.tm/",
        }

    def health(self) -> dict:
        request_json("GET", f"{self.base_url}/domains", timeout=self.timeout)
        return {"provider": self.name, "status": "ok", "external": True, "real_delivery": True}

    def create_inbox(self) -> Inbox:
        domains = request_json("GET", f"{self.base_url}/domains", timeout=self.timeout)
        members = domains.get("hydra:member", [])
        if not members or not members[0].get("domain"):
            raise ProviderError("mail.tm returned no available domains")
        address = f"llm-gym-{uuid.uuid4().hex[:12]}@{members[0]['domain']}"
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
        account = request_json(
            "POST",
            f"{self.base_url}/accounts",
            payload={"address": address, "password": password},
            timeout=self.timeout,
        )
        token_result = request_json(
            "POST",
            f"{self.base_url}/token",
            payload={"address": address, "password": password},
            timeout=self.timeout,
        )
        token = token_result.get("token")
        if not token:
            raise ProviderError("mail.tm did not return an access token")
        inbox_id = str(uuid.uuid4())
        self._tokens[inbox_id] = str(token)
        remote_id = account.get("id") or token_result.get("id")
        if remote_id:
            self._account_ids[inbox_id] = str(remote_id)
        inbox = Inbox(
            inbox_id,
            address,
            self.name,
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            status="active",
        )
        self._inboxes[inbox_id] = inbox
        return inbox

    def get_inbox(self, inbox_id: str) -> Inbox:
        token = self._tokens.get(inbox_id)
        if not token:
            raise KeyError("mail.tm inbox is not available in this process")
        account = request_json(
            "GET",
            f"{self.base_url}/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        inbox = Inbox(
            inbox_id,
            str(account.get("address", self._inboxes[inbox_id].address)),
            self.name,
            str(account.get("createdAt", self._inboxes[inbox_id].created_at)),
            status="active",
        )
        self._inboxes[inbox_id] = inbox
        return inbox

    def delete_inbox(self, inbox_id: str) -> Inbox:
        token = self._tokens.get(inbox_id)
        remote_id = self._account_ids.get(inbox_id)
        if not token or inbox_id not in self._inboxes:
            raise KeyError("mail.tm inbox is not available in this process")
        if not remote_id:
            raise ProviderError("mail.tm account ID is unavailable; deletion cannot be performed safely")
        inbox = self._inboxes[inbox_id]
        request_json(
            "DELETE",
            f"{self.base_url}/accounts/{remote_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        inbox.status = "deleted"
        self._tokens.pop(inbox_id, None)
        self._account_ids.pop(inbox_id, None)
        self._inboxes.pop(inbox_id, None)
        return inbox

    def get_messages(self, inbox_id: str) -> list[EmailMessage]:
        token = self._tokens.get(inbox_id)
        if not token:
            raise KeyError("mail.tm inbox is not available in this process")
        result = request_json(
            "GET",
            f"{self.base_url}/messages",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        summaries = result.get("hydra:member", [])
        messages = []
        for summary in summaries:
            detail = request_json(
                "GET",
                f"{self.base_url}/messages/{summary['id']}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            )
            text = detail.get("text", "")
            if isinstance(text, list):
                text = "\n".join(str(part) for part in text)
            messages.append(
                EmailMessage(
                    id=str(detail["id"]),
                    inbox_id=inbox_id,
                    sender=str(detail.get("from", {}).get("address", "unknown")),
                    subject=str(detail.get("subject", "")),
                    text=str(text),
                    received_at=str(detail.get("createdAt", "")),
                )
            )
        messages.sort(key=lambda message: message.received_at, reverse=True)
        return messages

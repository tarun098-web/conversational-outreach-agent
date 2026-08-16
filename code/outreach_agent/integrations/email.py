from __future__ import annotations

import asyncio
import base64
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from outreach_agent.domain.models import InboundMessage


class EmailProvider(Protocol):
    async def send_reply(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        thread_id: str | None,
        in_reply_to: str | None,
    ) -> str: ...

    async def fetch_history(self, start_history_id: str) -> list[InboundMessage]: ...


class MockEmailProvider:
    """Captures messages locally and never contacts Gmail."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_reply(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        thread_id: str | None,
        in_reply_to: str | None,
    ) -> str:
        external_id = f"mock-sent-{uuid4()}"
        self.sent.append(
            {
                "external_id": external_id,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "thread_id": thread_id,
                "in_reply_to": in_reply_to,
            }
        )
        return external_id

    async def fetch_history(self, start_history_id: str) -> list[InboundMessage]:
        return []


class GmailProvider:
    SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

    def __init__(self, token_path: Path) -> None:
        self.token_path = token_path

    def _service(self) -> Any:
        if not self.token_path.exists():
            raise RuntimeError(
                f"Gmail token not found at {self.token_path}. Run scripts/gmail_auth.py first."
            )
        credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            str(self.token_path), self.SCOPES
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    async def send_reply(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        thread_id: str | None,
        in_reply_to: str | None,
    ) -> str:
        def send() -> str:
            message = MIMEText(body, "plain", "utf-8")
            message["To"] = recipient
            message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            if in_reply_to:
                message["In-Reply-To"] = in_reply_to
                message["References"] = in_reply_to
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            payload: dict[str, Any] = {"raw": raw}
            if thread_id:
                payload["threadId"] = thread_id
            result = self._service().users().messages().send(userId="me", body=payload).execute()
            return str(result["id"])

        return await asyncio.to_thread(send)

    @staticmethod
    def _header(payload: dict[str, Any], name: str) -> str:
        for header in payload.get("headers", []):
            if header.get("name", "").lower() == name.lower():
                return str(header.get("value", ""))
        return ""

    @classmethod
    def _body(cls, payload: dict[str, Any]) -> str:
        body_data = payload.get("body", {}).get("data")
        if body_data:
            return base64.urlsafe_b64decode(body_data + "===").decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                value = cls._body(part)
                if value:
                    return value
        return ""

    @staticmethod
    def _email_address(value: str) -> tuple[str | None, str]:
        from email.utils import parseaddr

        name, address = parseaddr(value)
        return name or None, address

    async def fetch_history(self, start_history_id: str) -> list[InboundMessage]:
        def fetch() -> list[InboundMessage]:
            service = self._service()
            response = (
                service.users()
                .history()
                .list(userId="me", startHistoryId=start_history_id, historyTypes=["messageAdded"])
                .execute()
            )
            ids: set[str] = set()
            for history in response.get("history", []):
                for added in history.get("messagesAdded", []):
                    ids.add(str(added["message"]["id"]))
            result: list[InboundMessage] = []
            for message_id in ids:
                raw = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )
                if "SENT" in raw.get("labelIds", []):
                    continue
                payload = raw["payload"]
                sender_name, sender_email = self._email_address(self._header(payload, "From"))
                _, recipient = self._email_address(self._header(payload, "To"))
                body = self._body(payload).strip()
                if not sender_email or not body:
                    continue
                result.append(
                    InboundMessage(
                        external_id=message_id,
                        gmail_thread_id=str(raw.get("threadId", "")) or None,
                        sender_email=sender_email,
                        sender_name=sender_name,
                        recipients=[recipient] if recipient else [],
                        subject=self._header(payload, "Subject") or "(no subject)",
                        body_text=body,
                        in_reply_to=self._header(payload, "Message-ID") or None,
                        metadata={"history_id": raw.get("historyId")},
                    )
                )
            return result

        return await asyncio.to_thread(fetch)

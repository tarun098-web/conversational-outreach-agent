from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from outreach_agent.domain.models import (
    ActionRecord,
    Contact,
    Conversation,
    ConversationStage,
    ConversationView,
    DraftResponse,
    DraftStatus,
    Evidence,
    Message,
    WorkflowEvent,
)
from supabase import Client, create_client


def _json(model: Any) -> dict[str, Any]:
    return cast(dict[str, Any], model.model_dump(mode="json"))


class SupabaseRepository:
    """Supabase/Postgres persistence adapter used in real deployments."""

    def __init__(self, url: str, key: str) -> None:
        self.client: Client = create_client(url, key)

    async def _execute(self, query: Any) -> Any:
        return await asyncio.to_thread(query.execute)

    async def message_exists(self, external_id: str) -> bool:
        response = await self._execute(
            self.client.table("messages").select("id").eq("external_id", external_id).limit(1)
        )
        return bool(response.data)

    async def get_or_create_contact(self, email: str, name: str | None) -> Contact:
        normalized = email.strip().lower()
        response = await self._execute(
            self.client.table("contacts").select("*").eq("email", normalized).limit(1)
        )
        if response.data:
            return Contact.model_validate(response.data[0])
        contact = Contact(email=normalized, name=name)
        created = await self._execute(self.client.table("contacts").insert(_json(contact)))
        return Contact.model_validate(created.data[0])

    async def get_contact(self, contact_id: UUID) -> Contact:
        response = await self._execute(
            self.client.table("contacts").select("*").eq("id", str(contact_id)).single()
        )
        return Contact.model_validate(response.data)

    async def update_contact(self, contact: Contact) -> Contact:
        contact.updated_at = datetime.now(UTC)
        response = await self._execute(
            self.client.table("contacts").update(_json(contact)).eq("id", str(contact.id))
        )
        return Contact.model_validate(response.data[0])

    async def get_or_create_conversation(
        self, contact_id: UUID, gmail_thread_id: str | None, subject: str
    ) -> Conversation:
        query = self.client.table("conversations").select("*")
        query = (
            query.eq("gmail_thread_id", gmail_thread_id)
            if gmail_thread_id
            else query.eq("contact_id", str(contact_id)).eq("subject", subject)
        )
        response = await self._execute(query.limit(1))
        if response.data:
            return Conversation.model_validate(response.data[0])
        conversation = Conversation(
            contact_id=contact_id, gmail_thread_id=gmail_thread_id, subject=subject
        )
        created = await self._execute(
            self.client.table("conversations").insert(_json(conversation))
        )
        return Conversation.model_validate(created.data[0])

    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        response = await self._execute(
            self.client.table("conversations").select("*").eq("id", str(conversation_id)).single()
        )
        return Conversation.model_validate(response.data)

    async def update_conversation_stage(
        self, conversation_id: UUID, stage: ConversationStage
    ) -> Conversation:
        response = await self._execute(
            self.client.table("conversations")
            .update({"stage": stage.value, "updated_at": datetime.now(UTC).isoformat()})
            .eq("id", str(conversation_id))
        )
        return Conversation.model_validate(response.data[0])

    async def list_conversations(self) -> list[Conversation]:
        response = await self._execute(
            self.client.table("conversations").select("*").order("updated_at", desc=True)
        )
        return [Conversation.model_validate(item) for item in response.data]

    async def add_message(self, message: Message) -> Message:
        response = await self._execute(self.client.table("messages").insert(_json(message)))
        await self._execute(
            self.client.table("conversations")
            .update(
                {
                    "last_message_at": message.created_at.isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            .eq("id", str(message.conversation_id))
        )
        return Message.model_validate(response.data[0])

    async def list_messages(self, conversation_id: UUID, limit: int = 100) -> list[Message]:
        response = await self._execute(
            self.client.table("messages")
            .select("*")
            .eq("conversation_id", str(conversation_id))
            .order("created_at")
            .limit(limit)
        )
        return [Message.model_validate(item) for item in response.data]

    async def save_draft(self, draft: DraftResponse) -> DraftResponse:
        response = await self._execute(self.client.table("draft_responses").insert(_json(draft)))
        return DraftResponse.model_validate(response.data[0])

    async def get_draft(self, draft_id: UUID) -> DraftResponse:
        response = await self._execute(
            self.client.table("draft_responses").select("*").eq("id", str(draft_id)).single()
        )
        return DraftResponse.model_validate(response.data)

    async def update_draft(
        self,
        draft_id: UUID,
        status: DraftStatus,
        body: str | None = None,
        reviewer_note: str | None = None,
    ) -> DraftResponse:
        updates: dict[str, Any] = {
            "status": status.value,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if body is not None:
            updates["human_edited_body"] = body
        if reviewer_note is not None:
            updates["reviewer_note"] = reviewer_note
        response = await self._execute(
            self.client.table("draft_responses").update(updates).eq("id", str(draft_id))
        )
        return DraftResponse.model_validate(response.data[0])

    async def claim_draft_for_sending(
        self, draft_id: UUID, body: str, reviewer_note: str | None
    ) -> DraftResponse | None:
        updates: dict[str, Any] = {
            "status": DraftStatus.APPROVED.value,
            "human_edited_body": body,
            "reviewer_note": reviewer_note,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        response = await self._execute(
            self.client.table("draft_responses")
            .update(updates)
            .eq("id", str(draft_id))
            .eq("status", DraftStatus.AWAITING_APPROVAL.value)
        )
        return DraftResponse.model_validate(response.data[0]) if response.data else None

    async def list_drafts(
        self, status: DraftStatus | None = None, conversation_id: UUID | None = None
    ) -> list[DraftResponse]:
        query = self.client.table("draft_responses").select("*")
        if status:
            query = query.eq("status", status.value)
        if conversation_id:
            query = query.eq("conversation_id", str(conversation_id))
        response = await self._execute(query.order("created_at", desc=True))
        return [DraftResponse.model_validate(item) for item in response.data]

    async def save_action(self, action: ActionRecord) -> ActionRecord:
        payload = _json(action)
        existing = await self._execute(
            self.client.table("actions").select("id").eq("id", str(action.id)).limit(1)
        )
        query = (
            self.client.table("actions").update(payload).eq("id", str(action.id))
            if existing.data
            else self.client.table("actions").insert(payload)
        )
        response = await self._execute(query)
        return ActionRecord.model_validate(response.data[0])

    async def add_event(self, event: WorkflowEvent) -> WorkflowEvent:
        response = await self._execute(self.client.table("workflow_events").insert(_json(event)))
        return WorkflowEvent.model_validate(response.data[0])

    async def list_events(self, conversation_id: UUID) -> list[WorkflowEvent]:
        response = await self._execute(
            self.client.table("workflow_events")
            .select("*")
            .eq("conversation_id", str(conversation_id))
            .order("created_at")
        )
        return [WorkflowEvent.model_validate(item) for item in response.data]

    async def search_evidence(self, query: str, limit: int = 5) -> list[Evidence]:
        search_query: Any = self.client.table("knowledge_documents").select(
            "id,title,content,source"
        )
        search_query = search_query.text_search("content", query, options={"type": "websearch"})
        response = await self._execute(search_query.limit(limit))
        return [Evidence.model_validate(item) for item in response.data]

    async def add_evidence(self, evidence: Evidence) -> Evidence:
        response = await self._execute(
            self.client.table("knowledge_documents").insert(_json(evidence))
        )
        return Evidence.model_validate(response.data[0])

    async def get_view(self, conversation_id: UUID) -> ConversationView:
        conversation = await self.get_conversation(conversation_id)
        return ConversationView(
            conversation=conversation,
            contact=await self.get_contact(conversation.contact_id),
            messages=await self.list_messages(conversation_id),
            drafts=await self.list_drafts(conversation_id=conversation_id),
            events=await self.list_events(conversation_id),
        )

    async def get_mailbox_cursor(self, mailbox: str) -> str | None:
        response = await self._execute(
            self.client.table("mailbox_sync_state")
            .select("history_id")
            .eq("mailbox", mailbox)
            .limit(1)
        )
        return str(response.data[0]["history_id"]) if response.data else None

    async def set_mailbox_cursor(self, mailbox: str, history_id: str) -> None:
        await self._execute(
            self.client.table("mailbox_sync_state").upsert(
                {
                    "mailbox": mailbox,
                    "history_id": history_id,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="mailbox",
            )
        )

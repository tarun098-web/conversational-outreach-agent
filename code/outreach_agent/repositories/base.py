from __future__ import annotations

from typing import Protocol
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


class Repository(Protocol):
    async def message_exists(self, external_id: str) -> bool: ...

    async def get_or_create_contact(self, email: str, name: str | None) -> Contact: ...

    async def get_contact(self, contact_id: UUID) -> Contact: ...

    async def update_contact(self, contact: Contact) -> Contact: ...

    async def get_or_create_conversation(
        self, contact_id: UUID, gmail_thread_id: str | None, subject: str
    ) -> Conversation: ...

    async def get_conversation(self, conversation_id: UUID) -> Conversation: ...

    async def update_conversation_stage(
        self, conversation_id: UUID, stage: ConversationStage
    ) -> Conversation: ...

    async def list_conversations(self) -> list[Conversation]: ...

    async def add_message(self, message: Message) -> Message: ...

    async def list_messages(self, conversation_id: UUID, limit: int = 100) -> list[Message]: ...

    async def save_draft(self, draft: DraftResponse) -> DraftResponse: ...

    async def get_draft(self, draft_id: UUID) -> DraftResponse: ...

    async def update_draft(
        self,
        draft_id: UUID,
        status: DraftStatus,
        body: str | None = None,
        reviewer_note: str | None = None,
    ) -> DraftResponse: ...

    async def claim_draft_for_sending(
        self, draft_id: UUID, body: str, reviewer_note: str | None
    ) -> DraftResponse | None: ...

    async def list_drafts(
        self, status: DraftStatus | None = None, conversation_id: UUID | None = None
    ) -> list[DraftResponse]: ...

    async def save_action(self, action: ActionRecord) -> ActionRecord: ...

    async def add_event(self, event: WorkflowEvent) -> WorkflowEvent: ...

    async def list_events(self, conversation_id: UUID) -> list[WorkflowEvent]: ...

    async def search_evidence(self, query: str, limit: int = 5) -> list[Evidence]: ...

    async def add_evidence(self, evidence: Evidence) -> Evidence: ...

    async def get_view(self, conversation_id: UUID) -> ConversationView: ...

    async def get_mailbox_cursor(self, mailbox: str) -> str | None: ...

    async def set_mailbox_cursor(self, mailbox: str, history_id: str) -> None: ...

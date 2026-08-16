from __future__ import annotations

from datetime import UTC, datetime
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


class InMemoryRepository:
    """Development repository. Production uses SupabaseRepository."""

    def __init__(self) -> None:
        self.contacts: dict[UUID, Contact] = {}
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: dict[UUID, Message] = {}
        self.drafts: dict[UUID, DraftResponse] = {}
        self.actions: dict[UUID, ActionRecord] = {}
        self.events: dict[UUID, WorkflowEvent] = {}
        self.evidence: dict[UUID, Evidence] = {}
        self.mailbox_cursors: dict[str, str] = {}
        self._seed_knowledge()

    def _seed_knowledge(self) -> None:
        items = [
            Evidence(
                title="Demo policy",
                content="Qualified prospects may request a 30-minute discovery meeting.",
                source="built-in-demo",
            ),
            Evidence(
                title="Pricing policy",
                content=(
                    "Pricing is tailored after discovery; do not invent or quote unapproved prices."
                ),
                source="built-in-demo",
            ),
        ]
        self.evidence.update({item.id: item for item in items})

    async def message_exists(self, external_id: str) -> bool:
        return any(message.external_id == external_id for message in self.messages.values())

    async def get_or_create_contact(self, email: str, name: str | None) -> Contact:
        normalized = email.strip().lower()
        for contact in self.contacts.values():
            if contact.email.lower() == normalized:
                return contact
        contact = Contact(email=normalized, name=name)
        self.contacts[contact.id] = contact
        return contact

    async def get_contact(self, contact_id: UUID) -> Contact:
        return self.contacts[contact_id]

    async def update_contact(self, contact: Contact) -> Contact:
        contact.updated_at = datetime.now(UTC)
        self.contacts[contact.id] = contact
        return contact

    async def get_or_create_conversation(
        self, contact_id: UUID, gmail_thread_id: str | None, subject: str
    ) -> Conversation:
        for conversation in self.conversations.values():
            if gmail_thread_id and conversation.gmail_thread_id == gmail_thread_id:
                return conversation
            if (
                not gmail_thread_id
                and conversation.contact_id == contact_id
                and conversation.subject == subject
            ):
                return conversation
        conversation = Conversation(
            contact_id=contact_id, gmail_thread_id=gmail_thread_id, subject=subject
        )
        self.conversations[conversation.id] = conversation
        return conversation

    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        return self.conversations[conversation_id]

    async def update_conversation_stage(
        self, conversation_id: UUID, stage: ConversationStage
    ) -> Conversation:
        conversation = self.conversations[conversation_id]
        conversation.stage = stage
        conversation.updated_at = datetime.now(UTC)
        self.conversations[conversation_id] = conversation
        return conversation

    async def list_conversations(self) -> list[Conversation]:
        return sorted(self.conversations.values(), key=lambda item: item.updated_at, reverse=True)

    async def add_message(self, message: Message) -> Message:
        self.messages[message.id] = message
        conversation = self.conversations[message.conversation_id]
        conversation.last_message_at = message.created_at
        conversation.updated_at = datetime.now(UTC)
        return message

    async def list_messages(self, conversation_id: UUID, limit: int = 100) -> list[Message]:
        items = [item for item in self.messages.values() if item.conversation_id == conversation_id]
        return sorted(items, key=lambda item: item.created_at)[-limit:]

    async def save_draft(self, draft: DraftResponse) -> DraftResponse:
        self.drafts[draft.id] = draft
        return draft

    async def get_draft(self, draft_id: UUID) -> DraftResponse:
        return self.drafts[draft_id]

    async def update_draft(
        self,
        draft_id: UUID,
        status: DraftStatus,
        body: str | None = None,
        reviewer_note: str | None = None,
    ) -> DraftResponse:
        draft = self.drafts[draft_id]
        draft.status = status
        draft.updated_at = datetime.now(UTC)
        if body is not None:
            draft.human_edited_body = body
        if reviewer_note is not None:
            draft.reviewer_note = reviewer_note
        return draft

    async def claim_draft_for_sending(
        self, draft_id: UUID, body: str, reviewer_note: str | None
    ) -> DraftResponse | None:
        draft = self.drafts[draft_id]
        if draft.status != DraftStatus.AWAITING_APPROVAL:
            return None
        return await self.update_draft(
            draft_id, DraftStatus.APPROVED, body=body, reviewer_note=reviewer_note
        )

    async def list_drafts(
        self, status: DraftStatus | None = None, conversation_id: UUID | None = None
    ) -> list[DraftResponse]:
        items = list(self.drafts.values())
        if status:
            items = [item for item in items if item.status == status]
        if conversation_id:
            items = [item for item in items if item.conversation_id == conversation_id]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    async def save_action(self, action: ActionRecord) -> ActionRecord:
        self.actions[action.id] = action
        return action

    async def add_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events[event.id] = event
        return event

    async def list_events(self, conversation_id: UUID) -> list[WorkflowEvent]:
        items = [item for item in self.events.values() if item.conversation_id == conversation_id]
        return sorted(items, key=lambda item: item.created_at)

    async def search_evidence(self, query: str, limit: int = 5) -> list[Evidence]:
        words = {word.strip(".,?!").lower() for word in query.split() if len(word) > 3}
        ranked: list[tuple[int, Evidence]] = []
        for item in self.evidence.values():
            haystack = f"{item.title} {item.content}".lower()
            ranked.append((sum(word in haystack for word in words), item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in ranked[:limit]]

    async def add_evidence(self, evidence: Evidence) -> Evidence:
        self.evidence[evidence.id] = evidence
        return evidence

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
        return self.mailbox_cursors.get(mailbox)

    async def set_mailbox_cursor(self, mailbox: str, history_id: str) -> None:
        self.mailbox_cursors[mailbox] = history_id

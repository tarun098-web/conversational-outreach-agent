from __future__ import annotations

from difflib import SequenceMatcher
from uuid import UUID, uuid4

from outreach_agent.domain.models import (
    ActionStatus,
    ApprovalDecision,
    DraftResponse,
    DraftStatus,
    Message,
    MessageDirection,
    RejectionDecision,
    WorkflowEvent,
    WorkflowStep,
)
from outreach_agent.integrations.email import EmailProvider
from outreach_agent.repositories.base import Repository
from outreach_agent.services.actions import ActionExecutor


class DraftNotAwaitingApprovalError(RuntimeError):
    pass


class ApprovalService:
    def __init__(
        self, repository: Repository, email_provider: EmailProvider, actions: ActionExecutor
    ) -> None:
        self.repository = repository
        self.email_provider = email_provider
        self.actions = actions

    async def approve(self, draft_id: UUID, decision: ApprovalDecision) -> DraftResponse:
        original = await self.repository.get_draft(draft_id)
        final_body = decision.edited_body or original.body
        claimed = await self.repository.claim_draft_for_sending(
            draft_id, final_body, decision.reviewer_note
        )
        if claimed is None:
            raise DraftNotAwaitingApprovalError("Draft was already handled by another request")

        correlation_id = str(uuid4())
        await self.repository.add_event(
            WorkflowEvent(
                conversation_id=claimed.conversation_id,
                step=WorkflowStep.APPROVED,
                detail="Human reviewer approved the final reply and proposed action.",
                correlation_id=correlation_id,
                metadata={"edited": decision.edited_body is not None},
            )
        )
        view = await self.repository.get_view(claimed.conversation_id)
        action = await self.actions.execute(claimed, view.contact)
        await self.repository.add_event(
            WorkflowEvent(
                conversation_id=claimed.conversation_id,
                step=WorkflowStep.ACTION_EXECUTED,
                detail=f"Approved action {action.type.value}: {action.status.value}.",
                status="failed" if action.status == ActionStatus.FAILED else "completed",
                correlation_id=correlation_id,
                metadata=action.result,
            )
        )
        if action.status == ActionStatus.FAILED:
            return await self.repository.update_draft(
                draft_id, DraftStatus.FAILED, reviewer_note=action.error
            )

        inbound = next(item for item in view.messages if item.id == claimed.inbound_message_id)
        external_id = await self.email_provider.send_reply(
            recipient=view.contact.email,
            subject=view.conversation.subject,
            body=final_body,
            thread_id=view.conversation.gmail_thread_id,
            in_reply_to=inbound.in_reply_to,
        )
        await self.repository.add_message(
            Message(
                conversation_id=claimed.conversation_id,
                external_id=external_id,
                direction=MessageDirection.OUTBOUND,
                sender="configured-mailbox",
                recipients=[view.contact.email],
                subject=view.conversation.subject,
                body_text=final_body,
                gmail_thread_id=view.conversation.gmail_thread_id,
                in_reply_to=inbound.external_id,
            )
        )
        sent = await self.repository.update_draft(draft_id, DraftStatus.SENT, body=final_body)
        await self.repository.add_event(
            WorkflowEvent(
                conversation_id=claimed.conversation_id,
                step=WorkflowStep.REPLY_SENT,
                detail="Approved reply sent in the original email thread.",
                correlation_id=correlation_id,
                metadata={"external_id": external_id},
            )
        )
        similarity = SequenceMatcher(None, original.body, final_body).ratio()
        await self.repository.add_event(
            WorkflowEvent(
                conversation_id=claimed.conversation_id,
                step=WorkflowStep.EVALUATED,
                detail="Human feedback captured as an evaluation candidate.",
                correlation_id=correlation_id,
                metadata={"draft_similarity": round(similarity, 4)},
            )
        )
        return sent

    async def reject(self, draft_id: UUID, decision: RejectionDecision) -> DraftResponse:
        draft = await self.repository.get_draft(draft_id)
        if draft.status != DraftStatus.AWAITING_APPROVAL:
            raise DraftNotAwaitingApprovalError("Draft is not awaiting approval")
        rejected = await self.repository.update_draft(
            draft_id, DraftStatus.REJECTED, reviewer_note=decision.reason
        )
        await self.repository.add_event(
            WorkflowEvent(
                conversation_id=draft.conversation_id,
                step=WorkflowStep.REJECTED,
                detail="Human reviewer rejected the draft.",
                correlation_id=str(uuid4()),
                metadata={"reason": decision.reason},
            )
        )
        return rejected

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from outreach_agent.domain.models import (
    ActionProposal,
    ActionType,
    ConversationStage,
    DraftResponse,
    DraftStatus,
    GeneratedReply,
    InboundMessage,
    Intent,
    IntentAnalysis,
    Message,
    MessageDirection,
    ProcessResult,
    RiskLevel,
    WorkflowEvent,
    WorkflowStep,
)
from outreach_agent.integrations.llm import LanguageModel
from outreach_agent.repositories.base import Repository
from outreach_agent.services.policy import PolicyEngine


class ConversationPipeline:
    def __init__(
        self,
        repository: Repository,
        language_model: LanguageModel,
        policy: PolicyEngine,
        max_context_messages: int = 20,
    ) -> None:
        self.repository = repository
        self.language_model = language_model
        self.policy = policy
        self.max_context_messages = max_context_messages

    async def _event(
        self,
        conversation_id: UUID,
        step: WorkflowStep,
        detail: str,
        correlation_id: str,
        *,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.repository.add_event(
            WorkflowEvent(
                conversation_id=conversation_id,
                step=step,
                detail=detail,
                status=status,
                correlation_id=correlation_id,
                metadata=metadata or {},
            )
        )

    @staticmethod
    def _opt_out_analysis(message: InboundMessage) -> IntentAnalysis:
        return IntentAnalysis(
            intent=Intent.OPT_OUT,
            confidence=1,
            sentiment="negative",
            risk_level=RiskLevel.LOW,
            summary="Explicit opt-out request detected by deterministic policy.",
            requires_human=False,
            proposed_stage=ConversationStage.CLOSED,
        )

    async def process(self, inbound: InboundMessage) -> ProcessResult:
        correlation_id = str(uuid4())
        if await self.repository.message_exists(inbound.external_id):
            return ProcessResult(
                duplicate=True,
                status="duplicate_ignored",
                correlation_id=correlation_id,
            )

        contact = await self.repository.get_or_create_contact(
            inbound.sender_email, inbound.sender_name
        )
        conversation = await self.repository.get_or_create_conversation(
            contact.id, inbound.gmail_thread_id, inbound.subject
        )
        message = await self.repository.add_message(
            Message(
                conversation_id=conversation.id,
                external_id=inbound.external_id,
                direction=MessageDirection.INBOUND,
                sender=inbound.sender_email,
                recipients=inbound.recipients,
                subject=inbound.subject,
                body_text=inbound.body_text,
                gmail_thread_id=inbound.gmail_thread_id,
                in_reply_to=inbound.in_reply_to,
                raw_metadata=inbound.metadata,
                created_at=inbound.received_at,
            )
        )
        await self._event(
            conversation.id, WorkflowStep.RECEIVED, "Inbound email persisted.", correlation_id
        )
        await self._event(
            conversation.id,
            WorkflowStep.DEDUPLICATED,
            "External message ID accepted as unique.",
            correlation_id,
        )

        context = await self.repository.list_messages(
            conversation.id, limit=self.max_context_messages
        )
        await self._event(
            conversation.id,
            WorkflowStep.CONTEXT_LOADED,
            f"Loaded {len(context)} conversation message(s).",
            correlation_id,
        )

        evidence = await self.repository.search_evidence(inbound.body_text)
        await self._event(
            conversation.id,
            WorkflowStep.EVIDENCE_RETRIEVED,
            f"Retrieved {len(evidence)} approved knowledge item(s).",
            correlation_id,
            metadata={"sources": [item.source for item in evidence]},
        )

        if contact.opted_out and not self.policy.is_opt_out(inbound.body_text):
            await self._event(
                conversation.id,
                WorkflowStep.FAILED,
                "Suppressed contact message was stored but not processed.",
                correlation_id,
                status="blocked",
            )
            return ProcessResult(
                conversation_id=conversation.id,
                message_id=message.id,
                status="contact_suppressed",
                correlation_id=correlation_id,
            )

        if self.policy.is_opt_out(inbound.body_text):
            analysis = self._opt_out_analysis(inbound)
            generated = GeneratedReply(
                body="Understood. You have been removed from future outreach.",
                action=ActionProposal(
                    type=ActionType.SUPPRESS_CONTACT,
                    reason="Explicit opt-out detected by deterministic policy.",
                ),
            )
            model_name = "deterministic-policy-v1"
        else:
            analysis = await self.language_model.analyze(message, context)
            analysis = self.policy.validate_analysis(analysis, inbound.body_text)
            generated = await self.language_model.generate(message, context, analysis, evidence)
            model_name = self.language_model.model_name

        await self.repository.update_conversation_stage(conversation.id, analysis.proposed_stage)
        await self._event(
            conversation.id,
            WorkflowStep.INTENT_EXTRACTED,
            f"Intent: {analysis.intent.value}; risk: {analysis.risk_level.value}.",
            correlation_id,
            metadata=analysis.model_dump(mode="json"),
        )

        draft = DraftResponse(
            conversation_id=conversation.id,
            inbound_message_id=message.id,
            body=generated.body,
            analysis=analysis,
            action=generated.action,
            evidence=evidence,
            model_name=model_name,
        )
        await self._event(
            conversation.id,
            WorkflowStep.DRAFT_GENERATED,
            f"Draft generated with proposed action {draft.action.type.value}.",
            correlation_id,
        )
        draft.warnings = self.policy.validate_draft(draft)
        await self._event(
            conversation.id,
            WorkflowStep.SAFETY_CHECKED,
            f"Safety checks completed with {len(draft.warnings)} warning(s).",
            correlation_id,
            status="warning" if draft.warnings else "completed",
            metadata={"warnings": draft.warnings},
        )
        await self.repository.save_draft(draft)
        await self._event(
            conversation.id,
            WorkflowStep.AWAITING_APPROVAL,
            "No reply or action can execute until a reviewer approves this draft.",
            correlation_id,
            status="active",
            metadata={"draft_id": str(draft.id)},
        )
        return ProcessResult(
            conversation_id=conversation.id,
            message_id=message.id,
            draft_id=draft.id,
            status="awaiting_approval",
            correlation_id=correlation_id,
        )

    async def regenerate(self, draft_id: UUID) -> DraftResponse:
        old = await self.repository.get_draft(draft_id)
        messages = await self.repository.list_messages(
            old.conversation_id, self.max_context_messages
        )
        inbound = next(item for item in messages if item.id == old.inbound_message_id)
        evidence = await self.repository.search_evidence(inbound.body_text)
        generated = await self.language_model.generate(inbound, messages, old.analysis, evidence)
        await self.repository.update_draft(
            old.id, DraftStatus.REJECTED, reviewer_note="Superseded by regenerated draft."
        )
        replacement = DraftResponse(
            conversation_id=old.conversation_id,
            inbound_message_id=old.inbound_message_id,
            body=generated.body,
            analysis=old.analysis,
            action=generated.action,
            evidence=evidence,
            warnings=old.warnings,
            model_name=self.language_model.model_name,
            prompt_version=old.prompt_version,
        )
        return await self.repository.save_draft(replacement)

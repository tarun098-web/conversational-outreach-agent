from __future__ import annotations

from uuid import uuid4

import pytest
from outreach_agent.domain.models import (
    ApprovalDecision,
    DraftStatus,
    InboundMessage,
)
from outreach_agent.services.approval import DraftNotAwaitingApprovalError


def inbound(body: str, *, external_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        external_id=external_id or f"test-{uuid4()}",
        gmail_thread_id=f"thread-{uuid4()}",
        sender_email="prospect@example.com",
        sender_name="Prospect",
        recipients=["sales@example.test"],
        subject="Re: Test outreach",
        body_text=body,
    )


@pytest.mark.asyncio
async def test_startup_is_idle_and_inbound_triggers_model(container) -> None:
    assert container.language_model.calls == 0
    result = await container.pipeline.process(inbound("This is interesting. Tell me more."))
    assert result.status == "awaiting_approval"
    assert container.language_model.calls == 2


@pytest.mark.asyncio
async def test_duplicate_is_ignored_before_model_call(container) -> None:
    message = inbound("Could we schedule a meeting?", external_id="same-message")
    first = await container.pipeline.process(message)
    calls = container.language_model.calls
    second = await container.pipeline.process(message)
    assert first.duplicate is False
    assert second.duplicate is True
    assert container.language_model.calls == calls


@pytest.mark.asyncio
async def test_opt_out_uses_deterministic_policy_without_llm(container) -> None:
    result = await container.pipeline.process(inbound("Please unsubscribe me."))
    assert container.language_model.calls == 0
    draft = await container.repository.get_draft(result.draft_id)
    assert draft.action.type.value == "suppress_contact"


@pytest.mark.asyncio
async def test_approval_executes_action_and_sends_once(container) -> None:
    result = await container.pipeline.process(inbound("Can we have a meeting next week?"))
    sent = await container.approvals.approve(
        result.draft_id,
        ApprovalDecision(
            edited_body="Thanks. Please confirm your timezone and preferred time.",
            reviewer_note="Clear and safe",
        ),
    )
    assert sent.status == DraftStatus.SENT
    assert len(container.email_provider.sent) == 1
    with pytest.raises(DraftNotAwaitingApprovalError):
        await container.approvals.approve(result.draft_id, ApprovalDecision())
    assert len(container.email_provider.sent) == 1


@pytest.mark.asyncio
async def test_suppressed_contact_cannot_reenter_automation(container) -> None:
    first = await container.pipeline.process(inbound("Remove me from your emails."))
    await container.approvals.approve(first.draft_id, ApprovalDecision())
    followup = inbound("Actually, what is the price?")
    followup.gmail_thread_id = (
        await container.repository.get_draft(first.draft_id)
    ).conversation_id.hex
    result = await container.pipeline.process(followup)
    assert result.status == "contact_suppressed"

from __future__ import annotations

import base64
import json
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from outreach_agent.container import Container
from outreach_agent.domain.models import (
    ApprovalDecision,
    Conversation,
    ConversationView,
    DraftResponse,
    DraftStatus,
    InboundMessage,
    ProcessResult,
    RejectionDecision,
)
from outreach_agent.services.approval import DraftNotAwaitingApprovalError

router = APIRouter(prefix="/api/v1")


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


class PubSubMessage(BaseModel):
    data: str
    message_id: str | None = Field(default=None, alias="messageId")


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str | None = None


@router.post("/messages/inbound", response_model=ProcessResult)
async def inbound_message(message: InboundMessage, container: ContainerDep) -> ProcessResult:
    return await container.pipeline.process(message)


@router.post("/demo", response_model=ProcessResult)
async def run_demo(container: ContainerDep) -> ProcessResult:
    if container.settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Demo endpoint disabled in production")
    return await container.pipeline.process(
        InboundMessage(
            external_id=f"demo-{uuid4()}",
            gmail_thread_id=f"demo-thread-{uuid4()}",
            sender_email="alex@example.com",
            sender_name="Alex Morgan",
            recipients=["sales@example.test"],
            subject="Re: Analytics discovery",
            body_text=(
                "This sounds interesting. Could we speak next Tuesday afternoon? "
                "I am in Europe/London."
            ),
            metadata={"source": "zero-token-dashboard-demo"},
        )
    )


@router.post("/webhooks/gmail", response_model=list[ProcessResult])
async def gmail_webhook(
    envelope: PubSubEnvelope,
    container: ContainerDep,
    token: str | None = Query(default=None),
) -> list[ProcessResult]:
    expected = container.settings.gmail_pubsub_verification_token
    if expected and token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
        )
    try:
        decoded = base64.urlsafe_b64decode(envelope.message.data + "===")
        payload: dict[str, Any] = json.loads(decoded)
        mailbox = str(payload["emailAddress"])
        history_id = str(payload["historyId"])
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Malformed Gmail Pub/Sub payload") from error
    return await container.gmail_sync.handle_notification(mailbox, history_id)


@router.get("/conversations")
async def conversations(container: ContainerDep) -> list[Conversation]:
    return await container.repository.list_conversations()


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: UUID, container: ContainerDep) -> ConversationView:
    try:
        return await container.repository.get_view(conversation_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error


@router.get("/approvals", response_model=list[DraftResponse])
async def approvals(container: ContainerDep) -> list[DraftResponse]:
    return await container.repository.list_drafts(status=DraftStatus.AWAITING_APPROVAL)


@router.post("/approvals/{draft_id}/approve", response_model=DraftResponse)
async def approve(
    draft_id: UUID, decision: ApprovalDecision, container: ContainerDep
) -> DraftResponse:
    try:
        return await container.approvals.approve(draft_id, decision)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Draft not found") from error
    except DraftNotAwaitingApprovalError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/approvals/{draft_id}/reject", response_model=DraftResponse)
async def reject(
    draft_id: UUID, decision: RejectionDecision, container: ContainerDep
) -> DraftResponse:
    try:
        return await container.approvals.reject(draft_id, decision)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Draft not found") from error
    except DraftNotAwaitingApprovalError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/approvals/{draft_id}/regenerate", response_model=DraftResponse)
async def regenerate(draft_id: UUID, container: ContainerDep) -> DraftResponse:
    try:
        return await container.pipeline.regenerate(draft_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Draft not found") from error

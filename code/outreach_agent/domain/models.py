from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class Intent(StrEnum):
    INTERESTED = "interested"
    MEETING_REQUEST = "meeting_request"
    PRICING_QUESTION = "pricing_question"
    PRODUCT_QUESTION = "product_question"
    OBJECTION = "objection"
    RESCHEDULE = "reschedule"
    NOT_INTERESTED = "not_interested"
    OPT_OUT = "opt_out"
    COMPLAINT = "complaint"
    OTHER = "other"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConversationStage(StrEnum):
    NEW = "new"
    ENGAGED = "engaged"
    QUALIFYING = "qualifying"
    MEETING_PENDING = "meeting_pending"
    BOOKED = "booked"
    CLOSED = "closed"
    ESCALATED = "escalated"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DraftStatus(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"


class ActionType(StrEnum):
    NO_ACTION = "no_action"
    BOOK_MEETING = "book_meeting"
    REQUEST_BOOKING_DETAILS = "request_booking_details"
    UPDATE_CONTACT = "update_contact"
    ROUTE_TO_HUMAN = "route_to_human"
    MARK_NOT_INTERESTED = "mark_not_interested"
    SUPPRESS_CONTACT = "suppress_contact"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(StrEnum):
    RECEIVED = "received"
    DEDUPLICATED = "deduplicated"
    CONTEXT_LOADED = "context_loaded"
    EVIDENCE_RETRIEVED = "evidence_retrieved"
    INTENT_EXTRACTED = "intent_extracted"
    DRAFT_GENERATED = "draft_generated"
    SAFETY_CHECKED = "safety_checked"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    ACTION_EXECUTED = "action_executed"
    REPLY_SENT = "reply_sent"
    EVALUATED = "evaluated"
    REJECTED = "rejected"
    FAILED = "failed"


class Contact(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    email: str
    name: str | None = None
    company: str | None = None
    timezone: str | None = None
    opted_out: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Conversation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    contact_id: UUID
    gmail_thread_id: str | None = None
    subject: str
    stage: ConversationStage = ConversationStage.NEW
    last_message_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    external_id: str
    direction: MessageDirection
    sender: str
    recipients: list[str] = Field(default_factory=list)
    subject: str
    body_text: str
    gmail_thread_id: str | None = None
    in_reply_to: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Evidence(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    content: str
    source: str
    similarity: float = Field(default=1.0, ge=0, le=1)


class IntentAnalysis(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    sentiment: str
    risk_level: RiskLevel
    summary: str
    entities: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    requires_human: bool = False
    prompt_injection_suspected: bool = False
    proposed_stage: ConversationStage


class ActionProposal(BaseModel):
    type: ActionType = ActionType.NO_ACTION
    reason: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class GeneratedReply(BaseModel):
    body: str
    action: ActionProposal


class DraftResponse(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    inbound_message_id: UUID
    body: str
    analysis: IntentAnalysis
    action: ActionProposal
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.AWAITING_APPROVAL
    model_name: str
    prompt_version: str = "v1"
    reviewer_note: str | None = None
    human_edited_body: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ActionRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    draft_id: UUID
    type: ActionType
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.PROPOSED
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    step: WorkflowStep
    status: str = "completed"
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    created_at: datetime = Field(default_factory=utc_now)


class InboundMessage(BaseModel):
    external_id: str
    gmail_thread_id: str | None = None
    sender_email: str
    sender_name: str | None = None
    recipients: list[str] = Field(default_factory=list)
    subject: str
    body_text: str = Field(min_length=1)
    in_reply_to: str | None = None
    received_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessResult(BaseModel):
    duplicate: bool = False
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    draft_id: UUID | None = None
    status: str
    correlation_id: str


class ApprovalDecision(BaseModel):
    edited_body: str | None = Field(default=None, min_length=1)
    reviewer_note: str | None = None


class RejectionDecision(BaseModel):
    reason: str = Field(min_length=1)


class ConversationView(BaseModel):
    conversation: Conversation
    contact: Contact
    messages: list[Message]
    drafts: list[DraftResponse]
    events: list[WorkflowEvent]


class EvaluationScore(BaseModel):
    tone: float = Field(ge=0, le=1)
    correctness: float = Field(ge=0, le=1)
    grounding: float = Field(ge=0, le=1)
    progression: float = Field(ge=0, le=1)
    policy_compliance: float = Field(ge=0, le=1)
    explanation: str

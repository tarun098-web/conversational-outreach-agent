from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from outreach_agent.domain.models import (
    ActionRecord,
    ActionStatus,
    ActionType,
    Contact,
    DraftResponse,
)
from outreach_agent.repositories.base import Repository


class BookingRequest(BaseModel):
    starts_at: datetime
    timezone: str
    duration_minutes: int = Field(default=30, ge=15, le=120)
    attendee_email: str

    @model_validator(mode="after")
    def validate_booking(self) -> BookingRequest:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown IANA timezone") from error
        if self.starts_at.astimezone(UTC) <= datetime.now(UTC):
            raise ValueError("Meeting start must be in the future")
        return self


class ActionExecutor:
    """Executes only actions attached to an atomically claimed approved draft."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    async def execute(self, draft: DraftResponse, contact: Contact) -> ActionRecord:
        action = ActionRecord(
            conversation_id=draft.conversation_id,
            draft_id=draft.id,
            type=draft.action.type,
            arguments=draft.action.arguments,
            status=ActionStatus.APPROVED,
        )
        await self.repository.save_action(action)
        try:
            if action.type == ActionType.SUPPRESS_CONTACT:
                contact.opted_out = True
                await self.repository.update_contact(contact)
                action.result = {"contact_suppressed": True}
            elif action.type == ActionType.MARK_NOT_INTERESTED:
                contact.metadata["disposition"] = "not_interested"
                await self.repository.update_contact(contact)
                action.result = {"contact_updated": True}
            elif action.type == ActionType.UPDATE_CONTACT:
                allowed = {"company", "timezone", "name"}
                for key, value in action.arguments.items():
                    if key in allowed:
                        setattr(contact, key, value)
                await self.repository.update_contact(contact)
                action.result = {"fields_updated": sorted(set(action.arguments) & allowed)}
            elif action.type == ActionType.BOOK_MEETING:
                booking = BookingRequest.model_validate(action.arguments)
                action.result = {
                    "booking_status": "recorded",
                    "starts_at": booking.starts_at.isoformat(),
                    "timezone": booking.timezone,
                    "duration_minutes": booking.duration_minutes,
                }
            elif action.type == ActionType.ROUTE_TO_HUMAN:
                action.result = {"queue": "human_escalations", "routed": True}
            elif action.type == ActionType.REQUEST_BOOKING_DETAILS:
                action.result = {"awaiting": ["timezone", "preferred_time"]}
            else:
                action.result = {"no_action": True}
            action.status = ActionStatus.COMPLETED
        except Exception as error:
            action.status = ActionStatus.FAILED
            action.error = str(error)
        action.updated_at = datetime.now(UTC)
        return await self.repository.save_action(action)

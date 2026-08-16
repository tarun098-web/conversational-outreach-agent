from __future__ import annotations

from outreach_agent.domain.models import ProcessResult
from outreach_agent.integrations.email import EmailProvider
from outreach_agent.repositories.base import Repository
from outreach_agent.services.pipeline import ConversationPipeline


class GmailSyncService:
    def __init__(
        self,
        repository: Repository,
        email_provider: EmailProvider,
        pipeline: ConversationPipeline,
    ) -> None:
        self.repository = repository
        self.email_provider = email_provider
        self.pipeline = pipeline

    async def handle_notification(self, mailbox: str, history_id: str) -> list[ProcessResult]:
        previous = await self.repository.get_mailbox_cursor(mailbox)
        if previous is None:
            await self.repository.set_mailbox_cursor(mailbox, history_id)
            return []
        messages = await self.email_provider.fetch_history(previous)
        results = [await self.pipeline.process(message) for message in messages]
        await self.repository.set_mailbox_cursor(mailbox, history_id)
        return results

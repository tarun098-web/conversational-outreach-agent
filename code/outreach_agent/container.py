from __future__ import annotations

from outreach_agent.core.config import Settings
from outreach_agent.integrations.email import EmailProvider, GmailProvider, MockEmailProvider
from outreach_agent.integrations.llm import GroqLanguageModel, LanguageModel, MockLanguageModel
from outreach_agent.repositories.base import Repository
from outreach_agent.repositories.memory import InMemoryRepository
from outreach_agent.repositories.supabase import SupabaseRepository
from outreach_agent.services.actions import ActionExecutor
from outreach_agent.services.approval import ApprovalService
from outreach_agent.services.gmail_sync import GmailSyncService
from outreach_agent.services.pipeline import ConversationPipeline
from outreach_agent.services.policy import PolicyEngine


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if settings.storage_provider == "supabase":
            self.repository: Repository = SupabaseRepository(
                settings.supabase_url or "", settings.supabase_key or ""
            )
        else:
            self.repository = InMemoryRepository()

        if settings.ai_provider == "groq":
            self.language_model: LanguageModel = GroqLanguageModel(
                settings.groq_api_key or "",
                settings.groq_fast_model,
                settings.groq_smart_model,
            )
        else:
            self.language_model = MockLanguageModel()

        if settings.email_provider == "gmail":
            self.email_provider: EmailProvider = GmailProvider(settings.gmail_token_path)
        else:
            self.email_provider = MockEmailProvider()

        self.policy = PolicyEngine()
        self.pipeline = ConversationPipeline(
            self.repository,
            self.language_model,
            self.policy,
            settings.max_context_messages,
        )
        self.actions = ActionExecutor(self.repository)
        self.approvals = ApprovalService(self.repository, self.email_provider, self.actions)
        self.gmail_sync = GmailSyncService(self.repository, self.email_provider, self.pipeline)

from __future__ import annotations

import pytest
from outreach_agent.container import Container
from outreach_agent.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        ai_provider="mock",
        email_provider="mock",
        storage_provider="memory",
    )


@pytest.fixture
def container(settings: Settings) -> Container:
    return Container(settings)

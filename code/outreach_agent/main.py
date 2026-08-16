from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from outreach_agent.api.routes import router
from outreach_agent.container import Container
from outreach_agent.core.config import Settings, get_settings
from outreach_agent.core.logging import configure_logging
from outreach_agent.domain.models import DraftStatus

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Deliberately no polling task: idle service startup makes zero LLM calls.
        yield

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Human-controlled, event-driven conversational outreach agent",
        lifespan=lifespan,
    )
    application.state.container = Container(settings)
    application.include_router(router)
    application.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    async def ready() -> dict[str, str | bool]:
        return {
            "status": "ready",
            "ai_provider": settings.ai_provider,
            "email_provider": settings.email_provider,
            "storage_provider": settings.storage_provider,
            "background_polling": settings.enable_background_polling,
        }

    @application.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, conversation: UUID | None = None) -> Response:
        repository = request.app.state.container.repository
        conversations = await repository.list_conversations()
        selected = None
        if conversation is not None:
            try:
                selected = await repository.get_view(conversation)
            except KeyError:
                selected = None
        elif conversations:
            selected = await repository.get_view(conversations[0].id)
        drafts = await repository.list_drafts(status=DraftStatus.AWAITING_APPROVAL)
        completed_steps = (
            {event.step.value: event.status for event in selected.events} if selected else {}
        )
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "settings": settings,
                "conversations": conversations,
                "selected": selected,
                "drafts": drafts,
                "completed_steps": completed_steps,
            },
        )

    return application


app = create_app()

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.assistant.config import get_public_config
from app.assistant.knowledge import search_faq
from app.assistant.orchestrator import process_chat
from app.assistant.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantPublicConfig,
    KnowledgeSearchResponse,
)
from app.i18n.locale import resolve_locale

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/config/public", response_model=AssistantPublicConfig)
def get_assistant_config(request: Request, locale: str | None = Query(default=None)) -> AssistantPublicConfig:
    return get_public_config(resolve_locale(locale or request.query_params.get("lang"), request.headers.get("accept-language")))


@router.post("/chat", response_model=AssistantChatResponse)
async def chat(http_request: Request, request: AssistantChatRequest) -> AssistantChatResponse:
    resolved_locale = resolve_locale(request.locale, http_request.headers.get("accept-language"))
    request = request.model_copy(update={"locale": resolved_locale})
    return await process_chat(request)


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
def knowledge_search(
    request: Request,
    q: str = Query(default="", description="搜索关键词"),
    limit: int = Query(default=5, ge=1, le=20),
    locale: str | None = Query(default=None),
) -> KnowledgeSearchResponse:
    resolved_locale = resolve_locale(locale or request.query_params.get("lang"), request.headers.get("accept-language"))
    items = search_faq(q, limit=limit, locale=resolved_locale)
    return KnowledgeSearchResponse(
        items=[{"id": item["id"], "question": item["question"], "answer": item["answer"], "score": item["score"]} for item in items],
        total=len(items),
        locale=resolved_locale,
    )

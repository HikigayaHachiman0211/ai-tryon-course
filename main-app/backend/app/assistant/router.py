from __future__ import annotations

from fastapi import APIRouter, Query

from app.assistant.config import get_public_config
from app.assistant.knowledge import search_faq
from app.assistant.orchestrator import process_chat
from app.assistant.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantPublicConfig,
    KnowledgeSearchResponse,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/config/public", response_model=AssistantPublicConfig)
def get_assistant_config() -> AssistantPublicConfig:
    return get_public_config()


@router.post("/chat", response_model=AssistantChatResponse)
async def chat(request: AssistantChatRequest) -> AssistantChatResponse:
    return await process_chat(request)


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
def knowledge_search(
    q: str = Query(default="", description="搜索关键词"),
    limit: int = Query(default=5, ge=1, le=20),
) -> KnowledgeSearchResponse:
    items = search_faq(q, limit=limit)
    return KnowledgeSearchResponse(
        items=[{"id": item["id"], "question": item["question"], "answer": item["answer"], "score": item["score"]} for item in items],
        total=len(items),
    )

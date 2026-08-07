from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantFeatureFlags(BaseModel):
    text_chat: bool = True
    auto_fill: bool = True
    auto_submit: bool = False
    style_lab_guide: bool = True
    tryon_guide: bool = True


class AssistantPublicConfig(BaseModel):
    enabled: bool = True
    welcome_message: str = "你好，我是你的羽绒服 AI 导购助手。你可以告诉我预算、颜色、尺码、品牌和风格偏好。"
    features: AssistantFeatureFlags = Field(default_factory=AssistantFeatureFlags)
    defaults: dict[str, str] = Field(default_factory=lambda: {
        "ai_provider": "mimo",
        "vision_provider": "mimo",
        "mimo_model": "mimo-v2.5",
    })


class AssistantPageContext(BaseModel):
    view: str = ""
    current_form: dict[str, object] = Field(default_factory=dict)


class AssistantChatRequest(BaseModel):
    session_id: str = ""
    message: str = ""
    page_context: AssistantPageContext = Field(default_factory=AssistantPageContext)


class RecommendFormPatch(BaseModel):
    color_preference: str | None = None
    brand_preference: str | None = None
    gender: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    mbti: str | None = None
    size: str | None = None
    style_preference: str | None = None
    ai_provider: str | None = None
    vision_provider: str | None = None
    mimo_model: str | None = None
    gemini_model: str | None = None
    deepseek_model: str | None = None


class AssistantAction(BaseModel):
    type: str = "none"
    form_patch: RecommendFormPatch | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    requires_confirmation: bool = True


class AssistantDebugInfo(BaseModel):
    provider: str = "rule_fallback"
    fallback_used: bool = True
    latency_ms: int = 0


class AssistantChatResponse(BaseModel):
    reply: str = ""
    intent: str = "unknown"
    action: AssistantAction = Field(default_factory=AssistantAction)
    sources: list[str] = Field(default_factory=list)
    debug: AssistantDebugInfo = Field(default_factory=AssistantDebugInfo)


class KnowledgeSearchItem(BaseModel):
    id: int
    question: str
    answer: str
    score: float = 0.0


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeSearchItem] = Field(default_factory=list)
    total: int = 0

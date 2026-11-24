from __future__ import annotations

from app.assistant.schemas import AssistantPublicConfig, AssistantFeatureFlags
from app.i18n.locale import DEFAULT_LOCALE, normalize_locale
from app.i18n.messages import assistant_message
from app.mimo_models import DEFAULT_MIMO_MODEL


ASSISTANT_ENABLED = True

WELCOME_MESSAGE = "你好，我是你的羽绒服 AI 导购助手。你可以告诉我预算、颜色、尺码、品牌和风格偏好。"

FEATURE_FLAGS = AssistantFeatureFlags(
    text_chat=True,
    auto_fill=True,
    auto_submit=False,
    style_lab_guide=True,
    tryon_guide=True,
)

DEFAULT_AI_PROVIDER = "mimo"
DEFAULT_VISION_PROVIDER = "mimo"


def get_public_config(locale: str = DEFAULT_LOCALE) -> AssistantPublicConfig:
    resolved_locale = normalize_locale(locale) or DEFAULT_LOCALE
    return AssistantPublicConfig(
        enabled=ASSISTANT_ENABLED,
        welcome_message=assistant_message("welcome", resolved_locale),
        features=FEATURE_FLAGS,
        defaults={
            "ai_provider": DEFAULT_AI_PROVIDER,
            "vision_provider": DEFAULT_VISION_PROVIDER,
            "mimo_model": DEFAULT_MIMO_MODEL,
        },
        locale=resolved_locale,
    )

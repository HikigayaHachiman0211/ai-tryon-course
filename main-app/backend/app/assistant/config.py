from __future__ import annotations

from app.assistant.schemas import AssistantPublicConfig, AssistantFeatureFlags


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
DEFAULT_MIMO_MODEL = "mimo-v2.5"


def get_public_config() -> AssistantPublicConfig:
    return AssistantPublicConfig(
        enabled=ASSISTANT_ENABLED,
        welcome_message=WELCOME_MESSAGE,
        features=FEATURE_FLAGS,
        defaults={
            "ai_provider": DEFAULT_AI_PROVIDER,
            "vision_provider": DEFAULT_VISION_PROVIDER,
            "mimo_model": DEFAULT_MIMO_MODEL,
        },
    )

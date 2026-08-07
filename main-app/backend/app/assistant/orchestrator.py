from __future__ import annotations

import logging
import time
from typing import Any

from app.assistant.knowledge import get_faq_answer, search_faq
from app.assistant.llm_clients import try_llm_enhance
from app.assistant.rule_extractor import extract_recommend_fields, is_recommend_intent, sanitize_recommend_fields
from app.llm_parsing import coerce_confidence as _coerce_confidence
from app.assistant.schemas import (
    AssistantAction,
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantDebugInfo,
    RecommendFormPatch,
)

logger = logging.getLogger(__name__)

# Explicit whitelist of fields allowed in RecommendFormPatch
_RECOMMEND_FORM_FIELDS = set(RecommendFormPatch.model_fields.keys())


def classify_intent(message: str) -> str:
    """Classify user message intent (rule-based fallback).

    Priority: recommend (when strong keywords present) > tryon > style_lab > faq > unknown.
    """
    msg = message.strip()

    if is_recommend_intent(msg):
        return "recommend"

    if "试穿" in msg or "虚拟试穿" in msg:
        return "tryon"

    if "搭配" in msg or "自己搭配" in msg:
        return "style_lab"

    faq_keywords = ["怎么用", "如何", "什么是", "是什么", "怎么", "什么意思", "网站", "隐私", "照片"]
    if any(kw in msg for kw in faq_keywords):
        return "faq"

    return "unknown"


def build_recommend_action(form_patch: dict[str, Any], *, requires_confirmation: bool = True) -> AssistantAction:
    """Build a fill_recommend_form action from extracted fields."""
    patch = RecommendFormPatch(**{k: v for k, v in form_patch.items() if k in _RECOMMEND_FORM_FIELDS})
    return AssistantAction(
        type="fill_recommend_form",
        form_patch=patch,
        confidence=0.9,
        requires_confirmation=requires_confirmation,
    )


def build_recommend_reply(form_patch: dict[str, Any]) -> str:
    """Generate a human-readable summary of the extracted fields."""
    parts: list[str] = []

    gender = form_patch.get("gender")
    if gender == "female":
        parts.append("女款")
    elif gender == "male":
        parts.append("男款")

    color = form_patch.get("color_preference")
    if color:
        parts.append(color)

    price_max = form_patch.get("price_max")
    price_min = form_patch.get("price_min")
    if price_min is not None and price_max is not None:
        parts.append(f"预算 {price_min:.0f} - {price_max:.0f}")
    elif price_max is not None:
        parts.append(f"预算 {price_max:.0f} 以内")
    elif price_min is not None:
        parts.append(f"预算 {price_min:.0f} 以上")

    brand = form_patch.get("brand_preference")
    if brand:
        parts.append(f"品牌偏好 {brand}")

    size = form_patch.get("size")
    if size:
        parts.append(f"尺码 {size}")

    style = form_patch.get("style_preference")
    if style:
        parts.append(f"风格 {style}")

    if parts:
        summary = "、".join(parts)
        return f"我已经帮你整理成推荐条件：{summary}。你可以确认后生成推荐。"
    else:
        return "已识别你想要推荐羽绒服，但提取到的条件较少。请确认后补充更多偏好信息。"


def build_tryon_reply() -> str:
    return "要进行虚拟试穿，请先在推荐结果或「自己搭配」页面选择一件羽绒服，然后点击「尝试试穿」按钮。系统会自动打开试穿工作台并同步商品图，你只需在试穿站上传全身照即可。"


def build_style_lab_reply() -> str:
    return "你可以在页面顶部导航栏点击「自己搭配」进入 Style Lab。在那里你可以从商品库中挑选任意羽绒服，系统会对该单品与你的偏好进行多维评分和穿搭建议。"


def build_unknown_reply() -> str:
    return "你好，我是你的羽绒服 AI 导购助手。你可以告诉我预算、颜色、尺码、品牌或风格偏好，我会帮你整理推荐条件。"


async def process_chat(request: AssistantChatRequest) -> AssistantChatResponse:
    """Main orchestration: LLM-first, rule fallback.

    1. Try LLM via try_llm_enhance() for intent + field extraction.
    2. If LLM succeeds, use its result directly.
    3. If LLM fails, fall back to rule-based classify_intent + extract_recommend_fields.
    """
    start_time = time.time()

    message = request.message.strip()
    if not message:
        return AssistantChatResponse(
            reply="请告诉我你的需求，例如「我想要黑色显瘦的女款羽绒服，预算500以内」。",
            intent="unknown",
            debug=AssistantDebugInfo(provider="rule_fallback", fallback_used=True, latency_ms=0),
        )

    # --- Phase 1: Try LLM-first ---
    llm_result = None
    try:
        llm_result = await try_llm_enhance(message, request.page_context.current_form)
    except Exception as exc:
        logger.warning("LLM enhance failed unexpectedly: %s", exc)

    if llm_result:
        intent = llm_result.get("intent", "unknown")
        reply = llm_result.get("reply", "")
        form_patch = llm_result.get("form_patch", {})
        action_type = llm_result.get("action_type", "none")
        requires_conf = llm_result.get("requires_confirmation", True)
        confidence = llm_result.get("confidence", 0.5)
        provider = llm_result.get("provider", "unknown")

        if intent == "recommend" and not form_patch:
            form_patch = extract_recommend_fields(message)
            if form_patch:
                action_type = "fill_recommend_form"
        if intent == "recommend" and form_patch:
            form_patch = sanitize_recommend_fields(message, form_patch)

        # Build action
        action = AssistantAction()
        if action_type == "fill_recommend_form" and form_patch:
            action = build_recommend_action(form_patch, requires_confirmation=requires_conf)
        elif action_type == "none":
            action = AssistantAction(type="none", confidence=_coerce_confidence(confidence))

        # If intent is recommend but reply is empty, build one from form_patch
        if intent == "recommend" and not reply and form_patch:
            reply = build_recommend_reply(form_patch)

        # If intent is faq, try to enrich with knowledge base
        if intent == "faq" and not reply:
            faq_answer = get_faq_answer(message)
            reply = faq_answer or "抱歉，我没有找到相关问题的答案。你可以试试问我网站功能、尺码填写、试穿方法等问题。"

        # If intent is tryon/style_lab and reply is empty, use defaults
        if intent == "tryon" and not reply:
            reply = build_tryon_reply()
        if intent == "style_lab" and not reply:
            reply = build_style_lab_reply()

        # Some reasoning models can return a valid intent payload with empty user-facing
        # content. Never let a successful provider response create a blank chat bubble.
        reply = reply.strip()
        if not reply:
            faq_answer = get_faq_answer(message)
            if faq_answer:
                reply = faq_answer
                intent = "faq"
            elif intent == "recommend":
                reply = build_recommend_reply(form_patch)
            else:
                reply = build_unknown_reply()

        latency_ms = int((time.time() - start_time) * 1000)

        return AssistantChatResponse(
            reply=reply,
            intent=intent,
            action=action,
            sources=[],
            debug=AssistantDebugInfo(
                provider=provider,
                fallback_used=False,
                latency_ms=latency_ms,
            ),
        )

    # --- Phase 2: Rule fallback ---
    intent = classify_intent(message)
    form_patch: dict[str, Any] = {}
    reply = ""
    action = AssistantAction()

    if intent == "faq":
        faq_answer = get_faq_answer(message)
        if faq_answer:
            reply = faq_answer
        else:
            faq_results = search_faq(message, limit=3)
            if faq_results:
                reply = "我找到了几个可能相关的问题：\n"
                for item in faq_results:
                    reply += f"\n**{item['question']}**\n{item['answer']}\n"
            else:
                reply = "抱歉，我没有找到相关问题的答案。你可以试试问我网站功能、尺码填写、试穿方法等问题。"

    elif intent == "tryon":
        reply = build_tryon_reply()

    elif intent == "style_lab":
        reply = build_style_lab_reply()

    elif intent == "recommend":
        form_patch = sanitize_recommend_fields(message, extract_recommend_fields(message))
        reply = build_recommend_reply(form_patch)
        action = build_recommend_action(form_patch)

    else:
        # Unknown intent - try FAQ first, then suggest recommendation
        faq_answer = get_faq_answer(message)
        if faq_answer:
            reply = faq_answer
            intent = "faq"
        else:
            reply = build_unknown_reply()

    latency_ms = int((time.time() - start_time) * 1000)

    return AssistantChatResponse(
        reply=reply,
        intent=intent,
        action=action,
        sources=[],
        debug=AssistantDebugInfo(
            provider="rule_fallback",
            fallback_used=True,
            latency_ms=latency_ms,
        ),
    )

from __future__ import annotations

"""LLM client for assistant chat — tries configured providers in fallback order.

Uses backend/app/ai_runtime_config.py to resolve provider config,
and backend/app/prompt_loader.py to load prompts from the admin DB.
"""
import json
import logging
import re
from typing import Any

import httpx

from app.ai_runtime_config import build_auth_headers, resolve_effective_provider, resolve_provider_config
from app.assistant.schemas import RecommendFormPatch
from app.prompt_loader import load_active_prompt
from app.llm_parsing import (
    extract_json_object as _extract_json_object,
    coerce_confidence as _coerce_confidence,
    coerce_text as _coerce_text,
    coerce_action_type as _coerce_action_type,
)

logger = logging.getLogger(__name__)

_RECOMMEND_FORM_FIELDS = set(RecommendFormPatch.model_fields.keys())


def _sanitize_error_for_log(exc: Exception) -> str:
    """Strip API keys, tokens, base64 from error messages."""
    text = str(exc)
    text = re.sub(r"Authorization\s*[:=]\s*Bearer\s+\S+", "Authorization: Bearer [REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"api[_-]?key\s*[:=]\s*\S+", "api-key=[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"\?key=\S+", "?key=[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"data:[a-z]+/[a-z]+;base64,[A-Za-z0-9+/=]{40,}", "data:[REDACTED]", text, flags=re.IGNORECASE)
    if len(text) > 300:
        text = text[:300] + "..."
    return text


def _strip_json_block(text: str) -> dict[str, Any] | None:
    """Extract JSON object from text, stripping markdown code fences."""
    return _extract_json_object(text)


def _filter_form_patch(raw: dict[str, Any]) -> dict[str, Any]:
    """Filter LLM-returned form_patch to only allow RecommendFormPatch fields."""
    return {k: v for k, v in raw.items() if k in _RECOMMEND_FORM_FIELDS and v is not None}


def _normalize_intent(raw_intent: Any, *, message: str, form_patch: dict[str, Any]) -> str:
    intent = str(raw_intent or "").strip().lower()
    mapping = {
        "recommendation": "recommend",
        "recommend_form": "recommend",
        "fill_recommend_form": "recommend",
        "推荐": "recommend",
        "商品推荐": "recommend",
        "羽绒服推荐": "recommend",
        "问答": "faq",
        "常见问题": "faq",
        "试穿": "tryon",
        "虚拟试穿": "tryon",
        "搭配": "style_lab",
        "穿搭": "style_lab",
        "style": "style_lab",
        "stylelab": "style_lab",
        "unknown": "unknown",
    }
    if intent in mapping:
        return mapping[intent]
    if intent in ("recommend", "faq", "tryon", "style_lab"):
        return intent
    if form_patch:
        return "recommend"
    if any(keyword in message for keyword in ("推荐", "羽绒服", "预算", "颜色", "尺码", "品牌")):
        return "recommend"
    return "unknown"


def _call_mimo_chat(cfg: dict[str, Any], messages: list[dict], model: str) -> str | None:
    """Call MiMo chat completions API."""
    base_url = (cfg.get("base_url") or "https://api.xiaomimimo.com/v1").rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = build_auth_headers(cfg)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": 4096,
        "stream": False,
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return None
    message = choices[0].get("message", {})
    return message.get("content") or message.get("reasoning_content") or ""


def _call_deepseek_chat(cfg: dict[str, Any], messages: list[dict], model: str) -> str | None:
    """Call Deepseek chat completions API (OpenAI-compatible)."""
    base_url = (cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = build_auth_headers(cfg)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": False,
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return None
    return choices[0].get("message", {}).get("content", "")


def _call_gemini_chat(cfg: dict[str, Any], messages: list[dict], model: str) -> str | None:
    """Call Gemini generateContent API."""
    api_key = cfg.get("api_key", "")
    # Build Gemini contents from messages
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        gemini_role = "model" if role == "assistant" else role
        if role == "system":
            # Prepend system as first user message
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        else:
            contents.append({"role": gemini_role, "parts": [{"text": msg["content"]}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": contents,
        "generationConfig": {"temperature": 0.2},
    }
    resp = httpx.post(url, params={"key": api_key}, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    texts = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            if "text" in part:
                texts.append(part["text"])
    return "\n".join(texts) if texts else None


# Provider dispatch table
_PROVIDER_CALLERS = {
    "mimo": _call_mimo_chat,
    "deepseek": _call_deepseek_chat,
    "gemini": _call_gemini_chat,
}


async def try_llm_enhance(
    message: str,
    current_fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Attempt LLM-based intent classification and field extraction.

    Tries providers in the assistant_chat fallback chain order.
    Returns structured dict on success, None on failure.
    """
    _, chain = resolve_effective_provider("assistant_chat")

    # Build prompt from DB or default
    _DEFAULT_EXTRACT_PROMPT = (
        "你是羽绒服 AI 导购助手的需求理解与参数提取器。\n"
        "用户消息：{message}\n\n"
        "先在内部完成以下语义判断，再输出 JSON：\n"
        "1. 区分用户明确想要的正向条件与明确不要的排除条件。\n"
        "2. “不要、不喜欢、别推荐、排除、避免、不考虑、不接受”等词修饰的值是排除项，绝不能写入 form_patch。\n"
        "3. 同一句同时出现正向和排除款式时，只写正向款式。例如“像风衣，不要面包服”只能写“中长款大衣”。\n"
        "4. 不能仅因为用户提到某个名词就当成偏好，必须结合否定范围和完整句意。\n"
        "5. 用户没有明确表达、无法由现有映射确定的字段必须省略，不得脑补。\n\n"
        "请严格返回一个 JSON 对象（不要输出其他内容）：\n"
        '{{\n'
        '  "intent": "recommend/faq/tryon/style_lab/unknown",\n'
        '  "reply": "友好的中文回复，30字以内",\n'
        '  "form_patch": {{\n'
        '    "gender": "male/female 或省略",\n'
        '    "color_preference": "标准颜色或省略",\n'
        '    "brand_preference": "具体品牌列表或省略",\n'
        '    "size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/6XL/7XL 或省略",\n'
        '    "price_min": 数字或不填,\n'
        '    "price_max": 数字或不填,\n'
        '    "style_preference": "一个标准款式或省略",\n'
        '    "mbti": "16种标准MBTI之一或省略"\n'
        '  }},\n'
        '  "confidence": 0.0到1.0\n'
        '}}\n\n'
        "字段约束：\n"
        "- 只能输出上述 form_patch 字段，禁止新增 excluded_style、negative_style、notes 等前端不存在的字段。\n"
        "- gender 只能是 male 或 female。\n"
        "- color_preference 只使用标准色：黑色、白色、米白、灰色、蓝色、雾蓝、藏青、绿色、豆绿、橄榄、红色、棕色、卡其色、米色、橘色、粉色。\n"
        "- brand_preference 必须是商品数据库里存在的具体品牌或品牌候选，不能输出 大品牌、品牌大点、有保障、品质保障、知名品牌 这类泛化词。\n"
        "- 可选品牌：波司登、李宁、安踏、骆驼、阿迪达斯、耐克、优衣库、太平鸟、雪中飞、雅鹿、鸭鸭、鸿星尔克、361°、北面、始祖鸟、哥伦比亚、Under Armour、安德玛、罗蒙、南极人、乔丹、FILA、匹克、海澜之家。\n"
        "- 当用户只说“大品牌/品牌大点/有保障/品质保障/知名品牌”时，要结合预算和风格推断具体候选品牌。预算 350 以内优先：罗蒙、雅鹿、鸭鸭、雪中飞、南极人、骆驼、李宁、安踏；预算更高可考虑：波司登、阿迪达斯、耐克、FILA、优衣库、李宁、安踏、骆驼。\n"
        "- style_preference 只能是数据库款式之一：常规短外套、短款、轻薄款、绗缝款（排骨款）、面包服、中长款大衣、长款、巴恩风/工装风、派克大衣、马甲。一次只输出一个最明确的正向款式。\n"
        "- 风格映射：风衣/风衣感/大衣感/西服领 → 中长款大衣；工装/巴恩/多口袋/山系 → 巴恩风/工装风；绗缝/排骨/内胆 → 绗缝款（排骨款）；泡芙/蓬松 → 面包服；轻便/轻量/轻盈 → 轻薄款；通勤/极简/简约/百搭/基础 → 常规短外套；派克 → 派克大衣；背心 → 马甲。\n"
        "- 审美形容词如“帅、好看、高级、不土、洋气”不能单独映射为具体款式。\n"
        "- 明确排除优先于关键词映射。例如“不要面包服”“不喜欢泡芙感”“别推荐蓬松款”都禁止输出面包服。\n"
        "- “不要黑色，想要白色”只能输出 color_preference=白色。\n"
        "- 中文价格要转数字：三百块以内/300以内 → price_max: 300；五百到八百 → price_min: 500, price_max: 800。\n"
        "- 身高体重要联合判断尺码，不要只看身高；180cm 且 80kg/微胖 → size 至少 2XL；180cm 且 90kg以上 → 至少 3XL。\n"
        "- XXL → 2XL, XXXL → 3XL, 大码 → 2XL, 加大码 → 3XL\n"
        "- 男学生/男生/男士 → male, 女学生/女生/女士 → female\n"
        "- 如果用户问网站功能或使用方法，intent: faq\n"
        "- 如果用户提到试穿，intent: tryon\n"
        "- 如果用户提到搭配，intent: style_lab"
    )

    page_context = json.dumps(current_fields or {}, ensure_ascii=False, default=str)
    prompt_template = load_active_prompt("assistant_param_extractor", _DEFAULT_EXTRACT_PROMPT)
    prompt = prompt_template.replace("{message}", message)
    prompt += (
        "\n\n当前页面上下文 JSON：\n"
        f"{page_context}\n\n"
        "请结合当前页面上下文理解用户意图：\n"
        "- 如果 photo_uploaded=true，说明用户已经上传了照片，但你不能直接看见图片内容；需要图像身型分析时，应设置 vision_provider=mimo、mimo_model=mimo-v2.5，并引导用户填齐必填项后生成推荐。\n"
        "- 如果 recommendation_inference 存在，说明推荐接口已经完成图片/偏好分析；回复应引用其中的 body_shape、resolved_size、resolved_style、reasoning。\n"
        "- 如果 current_form 已有字段，不要要求用户重复填写；缺失 color_preference 或 gender 时应主动提取或询问。\n"
        "- 若用户要求根据照片推荐，intent 应为 recommend；能从文字中提取的字段放入 form_patch。\n"
        "- 不要默认补充 ai_provider、vision_provider 或模型字段；只有用户明确指定服务商时才填写，其他情况使用后台配置默认值。\n"
        "- 结构化字段质量规则：brand_preference 只允许数据库具体品牌或候选品牌列表；如果用户只说“大品牌、有保障、靠谱品牌、品质保障”，不要留空，要在候选品牌中按预算/风格选择 3-8 个具体品牌。\n"
        "- style_preference 必须使用数据库标准款式，不要输出 品质保障、风衣感、简约、不土 等自由词；先完成否定判断，再做标准映射。\n"
        "- 体型尺码规则：结合身高、体重、微胖/偏胖描述推断。180cm/一米八且约80kg，或用户说微胖，推荐 2XL 起步，不要输出 XL。"
    )

    messages = [
        {"role": "system", "content": "你是专业的羽绒服导购 AI 助手。只返回 JSON，不要输出多余解释。"},
        {"role": "user", "content": prompt},
    ]

    errors: list[str] = []
    for provider_key in chain:
        if provider_key == "rule":
            break
        cfg = resolve_provider_config(provider_key, feature_key="assistant_chat")
        api_key = cfg.get("api_key", "")
        if not api_key:
            reason = cfg.get("failure_reason", "")
            if reason:
                errors.append(reason)
            continue
        model = cfg.get("default_model", "")
        if not model:
            errors.append(f"{provider_key}: 未配置默认模型")
            continue

        caller = _PROVIDER_CALLERS.get(provider_key)
        if not caller:
            continue

        try:
            raw_text = caller(cfg, messages, model)
            if not raw_text:
                errors.append(f"{provider_key}: empty response")
                continue

            parsed = _strip_json_block(raw_text)
            if not parsed:
                errors.append(f"{provider_key}: invalid JSON")
                continue

            reply = _coerce_text(parsed.get("reply")) or ""

            raw_patch = parsed.get("form_patch", {})
            action_obj = parsed.get("action", {})
            if (not raw_patch or not isinstance(raw_patch, dict)) and isinstance(action_obj, dict):
                raw_patch = action_obj.get("form_patch", {})
            if not isinstance(raw_patch, dict):
                raw_patch = {}
            filtered_patch = _filter_form_patch(raw_patch)
            intent = _normalize_intent(parsed.get("intent"), message=message, form_patch=filtered_patch)

            # G1: coerce confidence — rejects NaN/inf/bool/str
            confidence = _coerce_confidence(parsed.get("confidence", 0.5))

            # Derive a default action_type, then apply G2: coerce action.type to safe values only
            derived_action_type = "fill_recommend_form" if intent == "recommend" and filtered_patch else "none"
            if isinstance(action_obj, dict) and action_obj.get("type"):
                action_type = _coerce_action_type(action_obj["type"])
            else:
                action_type = derived_action_type

            requires_conf = True
            if isinstance(action_obj, dict) and "requires_confirmation" in action_obj:
                requires_conf = bool(action_obj["requires_confirmation"])

            return {
                "intent": intent,
                "reply": reply,
                "form_patch": filtered_patch,
                "action_type": action_type,
                "requires_confirmation": requires_conf,
                "confidence": confidence,
                "provider": provider_key,
                "fallback_used": False,
                "errors": errors,
            }

        except Exception as exc:
            errors.append(f"{provider_key}: {_sanitize_error_for_log(exc)}")
            continue

    # All providers failed
    if errors:
        logger.warning("Assistant LLM providers failed; using rule fallback: %s", "; ".join(errors[:3]))
    return None

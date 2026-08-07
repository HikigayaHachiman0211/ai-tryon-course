from __future__ import annotations

from typing import Any

from app.ai_runtime_config import resolve_effective_provider, resolve_provider_config
from app.database import normalize_size
from app.llm_parsing import coerce_text as _coerce_text, has_known_profile_field as _has_known_profile_field
from app.profile_providers import (
    _sanitize_error_for_log,
    call_deepseek_profile,
    call_gemini_profile,
    call_gemini_text_profile,
    call_mimo_profile,
)
from app.recommendation_rules import normalize_body_shape, normalize_style_preference


def fallback_body_shape(size: str | None) -> str:
    if size in {"XS", "S"}:
        return "偏瘦"
    if size in {"M", "L"}:
        return "标准"
    if size in {"XL", "2XL"}:
        return "微胖"
    if size in {"3XL", "4XL", "5XL", "6XL", "7XL"}:
        return "高壮"
    return "标准"


def fallback_size_from_body_shape(body_shape: str | None) -> str | None:
    if body_shape in {"偏瘦", "H型"}:
        return "S"
    if body_shape in {"标准", "沙漏型", "倒三角"}:
        return "M"
    if body_shape in {"微胖", "梨形", "O型"}:
        return "XL"
    if body_shape == "高壮":
        return "2XL"
    return None


def infer_style_heuristically(body_shape: str | None, mbti: str | None) -> str:
    mbti_value = (mbti or "").upper()

    if body_shape in {"梨形", "O型"}:
        return "中长款大衣"
    if body_shape in {"微胖", "高壮"}:
        return "面包服"
    if body_shape in {"偏瘦", "H型"}:
        return "绗缝款（排骨款）"
    if body_shape == "倒三角":
        return "轻薄款"

    if mbti_value.endswith("J"):
        return "常规短外套"
    if mbti_value.endswith("P"):
        return "巴恩风/工装风"
    if mbti_value[:1] == "E":
        return "面包服"
    return "短款"


def build_inference_reason(body_shape: str, resolved_size: str | None, resolved_style: str, mbti: str | None) -> str:
    parts = [f"综合身型特征判断更接近{body_shape}"]
    if resolved_size:
        parts.append(f"尺码按{resolved_size}估计")
    if mbti:
        parts.append(f"结合 {mbti.upper()} 的气质偏好建议 {resolved_style}")
    else:
        parts.append(f"推荐优先考虑 {resolved_style}")
    return "，".join(parts)


def resolve_user_profile(
    *,
    image_bytes: bytes | None,
    mime_type: str | None,
    color_preference: str,
    gender: str | None,
    mbti: str | None,
    size: str | None,
    style_preference: str | None,
    gemini_api_key: str | None,
    gemini_model: str | None,
    deepseek_api_key: str | None = None,
    deepseek_model: str | None = None,
    mimo_api_key: str | None = None,
    mimo_model: str | None = None,
    ai_provider: str | None = None,
    vision_provider: str | None = None,
) -> dict[str, Any]:
    resolved_size = normalize_size(size)
    resolved_style = normalize_style_preference(style_preference)
    user_size = resolved_size  # preserve user input
    user_style = resolved_style  # preserve user input
    body_shape: str | None = None
    ai_reasoning: str | None = None
    size_source = "user" if resolved_size else "unknown"
    style_source = "user" if resolved_style else "unknown"
    ai_result: dict[str, Any] | None = None
    used_provider = "none"
    vision_used = "none"
    mimo_multimodal_used = False
    provider_errors: list[str] = []
    ai_attempted = False
    rule_fallback_used = False

    # Always try AI — not just when fields are missing
    should_try_ai = True
    has_image = bool(image_bytes)

    # --- Resolve fallback chains from feature config (DB → code defaults) ---
    _, text_chain = resolve_effective_provider("recommendation", request_provider=ai_provider)
    _, vision_chain = resolve_effective_provider("vision_analysis", request_provider=vision_provider)

    # --- Helper: resolve a single provider's config ---
    def _get_cfg(pk: str, *, fk: str | None = None) -> dict[str, Any]:
        req_key: str | None = None
        req_model: str | None = None
        if pk == "mimo":
            req_key, req_model = mimo_api_key, mimo_model
        elif pk == "gemini":
            req_key, req_model = gemini_api_key, gemini_model
        elif pk == "deepseek":
            req_key, req_model = deepseek_api_key, deepseek_model
        return resolve_provider_config(
            pk, request_api_key=req_key, request_model=req_model, feature_key=fk
        )

    # --- Helper: call a provider (multimodal if image, text otherwise) ---
    def _try_call(pk: str, cfg: dict[str, Any], *, use_image: bool) -> dict[str, Any] | None:
        api_key = cfg["api_key"]
        model = cfg["default_model"]
        if not api_key:
            # Record specific reason instead of generic "not configured"
            reason = cfg.get("failure_reason", "")
            if reason:
                provider_errors.append(reason)
            return None
        if pk == "mimo":
            return call_mimo_profile(
                api_key=api_key, gender=gender, mbti=mbti,
                color_preference=color_preference, size=size,
                style_preference=style_preference, model=model,
                image_bytes=image_bytes if use_image else None,
                mime_type=mime_type if use_image else None,
                base_url=cfg.get("base_url"),
                auth_type=cfg.get("auth_type"),
                auth_header_name=cfg.get("auth_header_name"),
            )
        if pk == "gemini":
            if use_image:
                return call_gemini_profile(
                    image_bytes=image_bytes, mime_type=mime_type,
                    api_key=api_key, gender=gender, mbti=mbti,
                    color_preference=color_preference, size=size,
                    style_preference=style_preference, model=model,
                )
            # Text-only Gemini — no image, use text generateContent
            return call_gemini_text_profile(
                api_key=api_key, gender=gender, mbti=mbti,
                color_preference=color_preference, size=size,
                style_preference=style_preference, model=model,
            )
        if pk == "deepseek":
            return call_deepseek_profile(
                api_key=api_key, gender=gender, mbti=mbti,
                color_preference=color_preference, size=size,
                style_preference=style_preference, model=model,
                base_url=cfg.get("base_url"),
            )
        return None

    # ===== Vision fallback chain (when image is available) =====
    if should_try_ai and has_image:
        ai_attempted = True
        for pk in vision_chain:
            if pk == "rule":
                break
            cfg = _get_cfg(pk, fk="vision_analysis")
            if not cfg["api_key"]:
                continue
            try:
                result = _try_call(pk, cfg, use_image=True)
                if result and _has_known_profile_field(result):
                    ai_result = result
                    used_provider = pk
                    vision_used = pk
                    if pk == "mimo":
                        mimo_multimodal_used = True
                    break
                if result:
                    provider_errors.append(f"{pk} 图像分析返回 JSON 缺少可用字段")
                else:
                    provider_errors.append(f"{pk} 图像分析返回为空或非 JSON")
            except Exception as exc:
                provider_errors.append(f"{pk} 图像分析失败: {_sanitize_error_for_log(exc)}")

    # ===== Text fallback chain (always, as backup or primary) =====
    if should_try_ai and not ai_result:
        ai_attempted = True
        for pk in text_chain:
            if pk == "rule":
                break
            cfg = _get_cfg(pk, fk="recommendation")
            if not cfg["api_key"]:
                continue
            try:
                result = _try_call(pk, cfg, use_image=False)
                if result and _has_known_profile_field(result):
                    ai_result = result
                    used_provider = pk
                    break
                if result:
                    provider_errors.append(f"{pk} 文本分析返回 JSON 缺少可用字段")
                else:
                    provider_errors.append(f"{pk} 文本分析返回为空或非 JSON")
            except Exception as exc:
                provider_errors.append(f"{pk} 文本分析失败: {_sanitize_error_for_log(exc)}")

    if not ai_result:
        rule_fallback_used = True

    if not ai_result and ai_reasoning is None:
        if provider_errors:
            ai_reasoning = f"AI 推断失败，已回退为规则推断。原因：{'; '.join(provider_errors[:3])}"
        else:
            ai_reasoning = "未配置 AI 引擎密钥，已回退为规则推断"

    if ai_result:
        body_shape = normalize_body_shape(str(ai_result.get("body_shape") or ""))
        result_reasoning = _coerce_text(ai_result.get("reasoning"))
        if result_reasoning:
            ai_reasoning = result_reasoning
        # Only fill size/style from AI if user didn't provide them
        if not user_size:
            ai_size = normalize_size(str(ai_result.get("recommended_size") or ""))
            if ai_size:
                resolved_size = ai_size
                size_source = used_provider
        if not user_style:
            ai_style = normalize_style_preference(str(ai_result.get("suggested_style") or ""))
            if ai_style:
                resolved_style = ai_style
                style_source = used_provider

    if not body_shape:
        body_shape = fallback_body_shape(resolved_size)

    if not resolved_size:
        resolved_size = fallback_size_from_body_shape(body_shape)
        if resolved_size:
            size_source = "heuristic"

    if not resolved_style:
        resolved_style = infer_style_heuristically(body_shape, mbti)
        style_source = "heuristic"

    # Resolve effective models for return values
    mimo_cfg = _get_cfg("mimo")
    gemini_cfg = _get_cfg("gemini")

    reasoning = ai_reasoning or build_inference_reason(body_shape, resolved_size, resolved_style, mbti)
    return {
        "resolved_size": resolved_size,
        "resolved_style": resolved_style,
        "body_shape": body_shape,
        "size_source": size_source,
        "style_source": style_source,
        "reasoning": reasoning,
        "gemini_model": gemini_cfg["default_model"],
        "gemini_used": used_provider == "gemini",
        "ai_provider": used_provider,
        "vision_provider": vision_chain[0] if vision_chain else "mimo",
        "vision_provider_used": vision_used,
        "mimo_model": mimo_cfg["default_model"],
        "mimo_used": used_provider == "mimo",
        "mimo_multimodal_used": mimo_multimodal_used,
        "ai_attempted": ai_attempted,
        "rule_fallback_used": rule_fallback_used,
        "provider_error_summary": "; ".join(provider_errors) if provider_errors else None,
    }

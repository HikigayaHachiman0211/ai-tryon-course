"""Shared try-on provider catalog, capability schema, and fine-tuning option helpers."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.config import DEFAULT_MODEL, MODEL_LIMITS, MODEL_MAP

VALID_PROVIDERS: tuple[str, ...] = ("gemini", "totokens")
VALID_TOTOKENS_SCOPES: tuple[str, ...] = ("gemini", "gpt_1k", "gpt_2k4k", "gpt_all", "custom")

BUILTIN_TOTOKENS_PROFILES: tuple[Dict[str, Any], ...] = (
    {
        "id": "totokens_gemini",
        "scope": "gemini",
        "label": "ToTokens Gemini 生图",
        "builtin": True,
        "enabled": True,
        "default_model": "gemini-3.1-flash-image",
        "models": ["gemini-3.1-flash-image", "gemini-3-pro-image-preview"],
        "timeout_seconds": 120,
    },
    {
        "id": "totokens_gpt_1k",
        "scope": "gpt_1k",
        "label": "ToTokens GPT Image 1K",
        "builtin": True,
        "enabled": True,
        "default_model": "gpt-image-2",
        "models": ["gpt-image-2", "chatgpt-image-latest", "gpt-image-1.5", "gpt-image-1"],
        "timeout_seconds": 120,
    },
    {
        "id": "totokens_gpt_2k4k",
        "scope": "gpt_2k4k",
        "label": "ToTokens GPT Image 2K/4K",
        "builtin": True,
        "enabled": True,
        "default_model": "gpt-image-2",
        "models": ["gpt-image-2"],
        "timeout_seconds": 120,
    },
)

PROFILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

ASPECT_RATIOS: tuple[str, ...] = (
    "auto",
    "3:4",
    "4:5",
    "9:16",
    "1:1",
    "4:3",
    "3:2",
    "2:3",
    "5:4",
    "16:9",
    "21:9",
)

GEMINI_IMAGE_SIZES: tuple[str, ...] = ("auto", "1K", "2K", "4K")
GPT_QUALITIES: tuple[str, ...] = ("auto", "low", "medium", "high")

TEMPERATURE_MIN: float = 0.0
TEMPERATURE_MAX: float = 2.0
SEED_MIN: int = 0
SEED_MAX: int = 2147483647

MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

_DEFAULT_PROVIDER_META: Dict[str, Dict[str, str]] = {
    "gemini": {
        "label": "Google Gemini 官方直连",
        "protocol_summary": "Gemini Native SDK",
    },
    "totokens": {
        "label": "ToTokens 中转站",
        "protocol_summary": "Gemini / OpenAI 统一中转",
    },
}

_BUILTIN_MODEL_LIST: Dict[str, List[str]] = {
    "gemini": [
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image-preview",
        "gemini-2.5-flash-image",
        "gemini-3-pro-image",
    ],
    "totokens": [
        "gemini-3.1-flash-image",
        "gpt-image-2",
        "chatgpt-image-latest",
        "gpt-image-1.5",
        "gpt-image-1",
    ],
}

_OPENAI_SIZE_BY_ASPECT: Dict[str, str] = {
    "1:1": "1024x1024",
    "2:3": "1024x1536",
    "3:4": "1024x1536",
    "4:5": "1024x1536",
    "9:16": "1024x1536",
    "3:2": "1536x1024",
    "4:3": "1536x1024",
    "5:4": "1536x1024",
    "16:9": "1536x1024",
    "21:9": "1536x1024",
}

# OpenAI gpt-image-2 2K / 4K dimensions: multiples of 16, max side 3840, total <= 8,294,400 px.
_OPENAI_SIZE_2K_BY_ASPECT: Dict[str, str] = {
    "auto": "2048x2048",
    "1:1": "2048x2048",
    "2:3": "1344x2016",
    "3:4": "1536x2048",
    "4:5": "1600x2000",
    "9:16": "1152x2048",
    "3:2": "2016x1344",
    "4:3": "2048x1536",
    "5:4": "2000x1600",
    "16:9": "2048x1152",
    "21:9": "2688x1152",
}

_OPENAI_SIZE_4K_BY_ASPECT: Dict[str, str] = {
    "auto": "2880x2880",
    "1:1": "2880x2880",
    "2:3": "2304x3456",
    "3:4": "2400x3200",
    "4:5": "2560x3200",
    "9:16": "2160x3840",
    "3:2": "3456x2304",
    "4:3": "3200x2400",
    "5:4": "3200x2560",
    "16:9": "3840x2160",
    "21:9": "3696x1584",
}

_IMAGE_SIZE_TO_OPENAI_QUALITY: Dict[str, str] = {
    "1K": "medium",
    "2K": "high",
    "4K": "high",
}


def validate_totokens_profile_id(profile_id: Optional[str]) -> Optional[str]:
    """Validate optional ToTokens multi-API profile selector."""
    if profile_id is None:
        return None
    cleaned = str(profile_id).strip()
    if not cleaned or cleaned.lower() == "auto":
        return None
    if not PROFILE_ID_PATTERN.fullmatch(cleaned):
        raise ValueError("ToTokens 密钥分组 ID 格式无效")
    return cleaned


def supports_gpt_multi_resolution(model_id: Optional[str]) -> bool:
    """Return True if a GPT image model supports 1K/2K/4K resolution tiers (e.g. gpt-image-2)."""
    low = str(model_id or "").strip().lower()
    if not low:
        return False
    return low.startswith("gpt-image-2") or low.startswith("gpt-image-3")


def validate_provider_key(provider: Optional[str]) -> Optional[str]:
    """Validate optional provider override key."""
    if provider is None:
        return None
    normalized = str(provider).strip().lower()
    if not normalized or normalized == "auto":
        return None
    if normalized not in VALID_PROVIDERS:
        raise ValueError("不支持的模型提供商，仅允许 gemini 或 totokens")
    return normalized


def validate_model_id(model_id: Optional[str]) -> Optional[str]:
    """Validate optional explicit model_id against path/URL injection."""
    if model_id is None:
        return None
    cleaned = str(model_id).strip()
    if not cleaned:
        return None
    if ".." in cleaned or "://" in cleaned or "?" in cleaned or "#" in cleaned or "@" in cleaned:
        raise ValueError("模型 ID 格式无效，不能包含路径跳转、查询参数或凭证字符")
    if not MODEL_ID_PATTERN.fullmatch(cleaned):
        raise ValueError("模型 ID 仅支持字母、数字及 . _ : / - 字符，长度不超过 128")
    return cleaned


def infer_model_protocol(provider_key: str, model_id: str) -> str:
    """Determine wire protocol used to call a concrete model on a provider."""
    lower = (model_id or "").strip().lower()
    if (provider_key or "").strip().lower() == "totokens" and ("gpt" in lower or "chatgpt" in lower):
        return "openai_images_edit"
    return "gemini_generate_content"


def infer_preset_key(
    model_id: Optional[str],
    *,
    flash_model: str = "",
    pro_model: str = "",
    chatgpt_model: str = "",
    fallback: str = DEFAULT_MODEL,
) -> str:
    """Map concrete model_id back to legacy preset key ('flash' | 'pro' | 'chatgpt')."""
    raw = str(model_id or "").strip()
    low = raw.lower()
    if not low:
        return fallback if fallback in MODEL_MAP else DEFAULT_MODEL
    if chatgpt_model and raw == chatgpt_model.strip():
        return "chatgpt"
    if "gpt" in low or "chatgpt" in low:
        return "chatgpt"
    if pro_model and raw == pro_model.strip():
        return "pro"
    if flash_model and raw == flash_model.strip():
        return "flash"
    if "pro" in low:
        return "pro"
    if "flash" in low:
        return "flash"
    return fallback if fallback in MODEL_MAP else DEFAULT_MODEL


def get_model_capabilities(provider_key: str, model_id: str) -> Dict[str, Any]:
    """Return UI and validation capability descriptor for a provider/model pair."""
    protocol = infer_model_protocol(provider_key, model_id)
    lower = (model_id or "").strip().lower()
    if protocol == "openai_images_edit":
        supports_multi_res = supports_gpt_multi_resolution(model_id)
        return {
            "protocol": protocol,
            "supports_aspect_ratio": True,
            "aspect_ratio_options": list(ASPECT_RATIOS),
            "supports_image_size": supports_multi_res,
            "image_size_options": list(GEMINI_IMAGE_SIZES) if supports_multi_res else ["auto", "1K"],
            "supports_quality": True,
            "quality_options": list(GPT_QUALITIES),
            "supports_temperature": False,
            "supports_seed": False,
        }

    supports_image_size = "2.5-flash" not in lower
    return {
        "protocol": protocol,
        "supports_aspect_ratio": True,
        "aspect_ratio_options": list(ASPECT_RATIOS),
        "supports_image_size": supports_image_size,
        "image_size_options": list(GEMINI_IMAGE_SIZES) if supports_image_size else ["auto", "1K"],
        "supports_quality": False,
        "quality_options": ["auto"],
        "supports_temperature": True,
        "supports_seed": True,
    }


def is_tryon_image_model_id(model_id: str, extra_included: Optional[set[str]] = None) -> bool:
    """Filter synced provider model lists to image-generation models plus pinned tryon IDs."""
    cleaned = str(model_id or "").strip()
    if not cleaned:
        return False
    if extra_included and cleaned in extra_included:
        return True
    low = cleaned.lower()
    if any(bad in low for bad in ("embedding", "aqa", "tts", "audio", "veo", "whisper", "realtime", "transcribe")):
        return False
    return (
        "image" in low
        or "imagen" in low
        or low.startswith("gpt-image")
        or low.startswith("chatgpt-image")
    )


def describe_model_entry(
    provider_key: str,
    model_id: str,
    *,
    flash_model: str = "",
    pro_model: str = "",
    chatgpt_model: str = "",
    default_model_id: str = "",
) -> Dict[str, Any]:
    """Build sanitized metadata entry for a provider's model dropdown option."""
    preset_key = infer_preset_key(
        model_id,
        flash_model=flash_model,
        pro_model=pro_model,
        chatgpt_model=chatgpt_model,
    )
    caps = get_model_capabilities(provider_key, model_id)
    limit = MODEL_LIMITS.get(preset_key, MODEL_LIMITS[DEFAULT_MODEL])
    low = model_id.lower()

    if "gpt" in low or "chatgpt" in low:
        speed_tier = "relay"
        badge = "GPT 图像"
    elif "pro" in low:
        speed_tier = "quality"
        badge = "精修"
    elif "3.1-flash" in low:
        speed_tier = "fast"
        badge = "新版极速"
    elif "flash" in low:
        speed_tier = "fast"
        badge = "快速"
    else:
        speed_tier = "custom"
        badge = "图像模型"

    return {
        "id": model_id,
        "label": model_id,
        "preset_key": preset_key,
        "protocol": caps["protocol"],
        "speed_tier": speed_tier,
        "badge": badge,
        "max_concurrency": int(limit.get("max_concurrency", 5)),
        "is_default": bool(default_model_id and model_id == default_model_id),
        "capabilities": caps,
    }


def _dedupe_nonempty(items: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for raw in items:
        item = str(raw or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _scope_resolutions(scope: str) -> List[str]:
    if scope == "gpt_1k":
        return ["1K"]
    if scope == "gpt_2k4k":
        return ["2K", "4K"]
    return ["1K", "2K", "4K"]


def _scope_protocol(scope: str) -> str:
    if scope == "gemini":
        return "gemini_generate_content"
    if scope in ("gpt_1k", "gpt_2k4k", "gpt_all"):
        return "openai_images_edit"
    return "mixed"


def extract_totokens_profiles(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize ToTokens multi-API profiles from runtime or sanitized config."""
    records = extract_provider_records(config)
    relay_rec = records.get("totokens") or {}
    default_base_url = str(relay_rec.get("base_url") or config.get("relay_base_url") or "https://totokens.cc").strip() or "https://totokens.cc"
    default_timeout = int(relay_rec.get("timeout_seconds") or config.get("relay_timeout_seconds") or config.get("timeout_seconds") or 120)

    raw_profiles = config.get("totokens_apis_internal")
    if not isinstance(raw_profiles, list):
        raw_profiles = relay_rec.get("api_profiles")
    if not isinstance(raw_profiles, list):
        raw_profiles = config.get("totokens_apis")

    saved_by_id: Dict[str, Dict[str, Any]] = {}
    ordered_custom: List[Dict[str, Any]] = []
    builtin_ids = {item["id"] for item in BUILTIN_TOTOKENS_PROFILES}

    for entry in (raw_profiles or []):
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("id") or "").strip()
        if not pid:
            continue
        if pid in builtin_ids:
            saved_by_id[pid] = entry
        else:
            ordered_custom.append(entry)

    def _normalize_entry(template: Dict[str, Any], saved: Dict[str, Any]) -> Dict[str, Any]:
        pid = str(saved.get("id") or template.get("id") or "").strip()
        scope = str(saved.get("scope") or template.get("scope") or "custom").strip().lower()
        if scope not in VALID_TOTOKENS_SCOPES:
            scope = "custom"
        raw_models = saved.get("models") if isinstance(saved.get("models"), list) else template.get("models", [])
        models = _dedupe_nonempty([str(m or "") for m in (raw_models or [])])
        default_model = str(saved.get("default_model") or template.get("default_model") or (models[0] if models else "")).strip()
        if default_model and default_model not in models:
            models = [default_model, *models]
        enabled = bool(saved["enabled"]) if "enabled" in saved else bool(template.get("enabled", True))
        api_key = str(saved.get("api_key") or "").strip()
        configured = bool(saved.get("configured", bool(api_key))) and enabled
        try:
            timeout_s = max(10, min(300, int(saved.get("timeout_seconds") or template.get("timeout_seconds") or default_timeout)))
        except (TypeError, ValueError):
            timeout_s = default_timeout
        return {
            "id": pid,
            "scope": scope,
            "label": str(saved.get("label") or template.get("label") or pid).strip(),
            "builtin": bool(pid in builtin_ids),
            "enabled": enabled,
            "configured": configured,
            "api_key": api_key,
            "base_url": str(saved.get("base_url") or default_base_url).strip() or default_base_url,
            "default_model": default_model,
            "models": models,
            "timeout_seconds": timeout_s,
            "supported_resolutions": _scope_resolutions(scope),
            "protocol": _scope_protocol(scope),
        }

    normalized: List[Dict[str, Any]] = [
        _normalize_entry(tpl, saved_by_id.get(tpl["id"], {}))
        for tpl in BUILTIN_TOTOKENS_PROFILES
    ]
    for custom in ordered_custom:
        normalized.append(_normalize_entry({"builtin": False, "enabled": True, "models": []}, custom))
    return normalized


def _is_gemini_totokens_model(model_key: str, model_id: Optional[str]) -> bool:
    mid = str(model_id or "").strip().lower()
    if mid:
        if "gemini" in mid:
            return True
        if "gpt" in mid or "chatgpt" in mid:
            return False
    return str(model_key or "").strip().lower() == "flash"


def resolve_totokens_route(
    config: Dict[str, Any],
    *,
    model_id: Optional[str],
    model_key: str = DEFAULT_MODEL,
    detail_options: Optional[Dict[str, Any]] = None,
    explicit_profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Select the exact ToTokens API key/base_url for Gemini vs GPT 1K vs GPT 2K/4K.

    Prevents cross-group routing (e.g., never routes 2K/4K GPT requests to a 1K-only
    key, and never sends Gemini requests to a GPT-only key).
    """
    records = extract_provider_records(config)
    relay_rec = records.get("totokens") or {}
    legacy_key = str(relay_rec.get("api_key") or config.get("relay_api_key") or "").strip()
    if not legacy_key and str(config.get("provider_key") or "").strip().lower() == "totokens":
        legacy_key = str(config.get("api_key") or "").strip()
    default_base_url = str(relay_rec.get("base_url") or config.get("relay_base_url") or "https://totokens.cc").strip() or "https://totokens.cc"
    default_timeout = int(relay_rec.get("timeout_seconds") or config.get("relay_timeout_seconds") or 120)

    profiles = extract_totokens_profiles(config)
    usable = [p for p in profiles if p["enabled"] and p["api_key"]]

    opts = dict(detail_options or {})
    req_profile = validate_totokens_profile_id(explicit_profile_id if explicit_profile_id is not None else opts.get("totokens_profile"))
    is_gemini = _is_gemini_totokens_model(model_key, model_id)
    effective_model = str(model_id or "").strip()
    requested_size = str(opts.get("image_size") or "auto").strip().upper()
    if requested_size == "AUTO" or not requested_size:
        requested_size = "AUTO"
    multi_res_gpt = supports_gpt_multi_resolution(effective_model)

    def _result_from_profile(p: Dict[str, Any], out_opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "api_key": p["api_key"],
            "base_url": p.get("base_url") or default_base_url,
            "timeout_seconds": int(p.get("timeout_seconds") or default_timeout),
            "profile_id": p["id"],
            "profile_label": p["label"],
            "profile_scope": p["scope"],
            "effective_detail_options": out_opts,
        }

    def _result_from_legacy(out_opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "api_key": legacy_key,
            "base_url": default_base_url,
            "timeout_seconds": default_timeout,
            "profile_id": "totokens_legacy",
            "profile_label": "ToTokens Default",
            "profile_scope": "legacy",
            "effective_detail_options": out_opts,
        }

    # Explicit user/caller profile selection
    if req_profile:
        target = next((p for p in profiles if p["id"] == req_profile), None)
        if not target:
            raise ValueError(f"指定的 ToTokens 密钥分组不存在：{req_profile}")
        if not target["enabled"]:
            raise RuntimeError(f"ToTokens 密钥分组「{target['label']}」当前已停用")
        if not target["api_key"]:
            raise RuntimeError(f"ToTokens 密钥分组「{target['label']}」尚未配置 API Key")

        scope = target["scope"]
        if scope == "gemini" and not is_gemini:
            raise ValueError("所选 ToTokens Gemini 密钥分组不支持 GPT Image 模型，请切换到 GPT 密钥分组或设为智能匹配")
        if scope in ("gpt_1k", "gpt_2k4k", "gpt_all") and is_gemini:
            raise ValueError("所选 ToTokens GPT 密钥分组不支持 Gemini 生图模型，请切换到 Gemini 密钥分组或设为智能匹配")
        if scope == "gpt_1k" and not is_gemini and requested_size in ("2K", "4K"):
            raise ValueError("「GPT Image 1K」密钥分组仅支持 1K 分辨率；生成 2K/4K 请使用「GPT Image 2K/4K」密钥或设为智能匹配")
        if scope == "gpt_2k4k" and not is_gemini:
            if not multi_res_gpt:
                raise ValueError(f"模型 {effective_model or model_key} 仅支持 1K，不能使用「GPT Image 2K/4K」密钥分组")
            if requested_size == "1K":
                raise ValueError("「GPT Image 2K/4K」密钥分组仅支持 2K/4K 分辨率；生成 1K 请使用「GPT Image 1K」密钥或调整分辨率")
            if requested_size == "AUTO":
                opts["image_size"] = "2K"
        return _result_from_profile(target, opts)

    # Smart automatic selection based on model protocol and requested resolution
    def _pick_first(cands: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not cands:
            return None
        if effective_model:
            matched = [p for p in cands if effective_model in (p.get("models") or [])]
            if matched:
                return matched[0]
        return cands[0]

    if is_gemini:
        chosen = _pick_first([p for p in usable if p["scope"] == "gemini"])
        if not chosen and effective_model:
            chosen = _pick_first([p for p in usable if p["scope"] == "custom" and effective_model in (p.get("models") or [])])
        if chosen:
            return _result_from_profile(chosen, opts)
        if legacy_key:
            return _result_from_legacy(opts)
        raise RuntimeError("ToTokens Gemini 生图 API Key 未配置，请在后台「ToTokens 多 API 配置」填写 Gemini 密钥")

    # GPT Image routes
    custom_exact = [p for p in usable if p["scope"] == "custom" and effective_model and effective_model in (p.get("models") or [])]

    if requested_size in ("2K", "4K"):
        chosen = (
            _pick_first([p for p in usable if p["scope"] == "gpt_2k4k"])
            or _pick_first([p for p in usable if p["scope"] == "gpt_all"])
            or _pick_first(custom_exact)
        )
        if chosen:
            return _result_from_profile(chosen, opts)
        if legacy_key:
            return _result_from_legacy(opts)
        raise RuntimeError("ToTokens GPT Image 2K/4K API Key 未配置（1K 密钥无法生成 2K/4K 图像），请在后台配置 2K/4K 生图密钥")

    if requested_size == "1K" or not multi_res_gpt:
        chosen = (
            _pick_first([p for p in usable if p["scope"] == "gpt_1k"])
            or _pick_first([p for p in usable if p["scope"] == "gpt_all"])
            or _pick_first(custom_exact)
        )
        if chosen:
            return _result_from_profile(chosen, opts)
        if legacy_key:
            return _result_from_legacy(opts)
        raise RuntimeError("ToTokens GPT Image 1K API Key 未配置（2K/4K 密钥不能用于 1K），请在后台配置 1K 生图密钥")

    # Auto resolution on multi-res GPT model (e.g. gpt-image-2 with image_size='auto'):
    # prefer 1K -> gpt_all -> gpt_2k4k (auto-promoted to 2K so upstream never rejects 1K default) -> custom -> legacy
    chosen_1k_or_all = (
        _pick_first([p for p in usable if p["scope"] == "gpt_1k"])
        or _pick_first([p for p in usable if p["scope"] == "gpt_all"])
    )
    if chosen_1k_or_all:
        return _result_from_profile(chosen_1k_or_all, opts)

    chosen_2k4k = _pick_first([p for p in usable if p["scope"] == "gpt_2k4k"])
    if chosen_2k4k:
        opts["image_size"] = "2K"
        return _result_from_profile(chosen_2k4k, opts)

    chosen_custom = _pick_first(custom_exact)
    if chosen_custom:
        return _result_from_profile(chosen_custom, opts)
    if legacy_key:
        return _result_from_legacy(opts)
    raise RuntimeError("ToTokens GPT Image API Key 未配置（请配置 GPT 1K 或 GPT 2K/4K 密钥）")


def extract_provider_records(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build normalized internal provider map from rich DB config or legacy flat config."""
    internal = config.get("providers_internal")
    if isinstance(internal, dict) and internal:
        return internal

    # Synthesize from legacy flat config dict (env fallback or unit-test mocks).
    primary_key = str(config.get("provider_key") or "gemini").strip().lower()
    if primary_key not in VALID_PROVIDERS:
        primary_key = "gemini"

    flash_model = str(config.get("flash_model") or "").strip()
    pro_model = str(config.get("pro_model") or "").strip()
    chatgpt_model = str(config.get("chatgpt_model") or "gpt-image-2").strip()

    gemini_key = str(config.get("api_key") or "") if primary_key == "gemini" else ""
    gemini_enabled = bool(config.get("provider_enabled", config.get("enabled", False))) if primary_key == "gemini" else False
    gemini_models = _dedupe_nonempty(
        ([flash_model, pro_model] if primary_key == "gemini" else [])
        + list(MODEL_MAP["flash"]["ids"])
        + list(MODEL_MAP["pro"]["ids"])
    )

    relay_key = str(config.get("relay_api_key") or "") or (
        str(config.get("api_key") or "") if primary_key == "totokens" else ""
    )
    relay_enabled = bool(config.get("relay_enabled")) or (
        primary_key == "totokens" and bool(config.get("provider_enabled", config.get("enabled", False)))
    )
    relay_configured = bool(config.get("relay_configured")) or (relay_enabled and bool(relay_key))
    totokens_models = _dedupe_nonempty(
        ([flash_model, pro_model] if primary_key == "totokens" else [])
        + [chatgpt_model]
        + _BUILTIN_MODEL_LIST["totokens"]
    )

    return {
        "gemini": {
            "provider_key": "gemini",
            "enabled": gemini_enabled,
            "configured": bool(gemini_enabled and gemini_key),
            "api_key": gemini_key,
            "base_url": str(config.get("base_url") or "") if primary_key == "gemini" else "",
            "timeout_seconds": int(config.get("timeout_seconds") or 60),
            "retry_count": int(config.get("retry_count") if config.get("retry_count") is not None else 1),
            "default_model": flash_model or MODEL_MAP["flash"]["ids"][0],
            "models": gemini_models,
        },
        "totokens": {
            "provider_key": "totokens",
            "enabled": relay_enabled,
            "configured": relay_configured,
            "api_key": relay_key,
            "base_url": str(
                config.get("relay_base_url")
                or (config.get("base_url") if primary_key == "totokens" else "")
                or "https://totokens.cc"
            ).strip(),
            "timeout_seconds": int(config.get("relay_timeout_seconds") or config.get("timeout_seconds") or 120),
            "retry_count": int(config.get("retry_count") if config.get("retry_count") is not None else 1),
            "default_model": (flash_model if primary_key == "totokens" else chatgpt_model) or chatgpt_model,
            "models": totokens_models,
        },
    }


def build_runtime_providers_catalog(config: Dict[str, Any]) -> Dict[str, Any]:
    """Construct public non-sensitive provider + model catalog for /api/runtime-status."""
    feature_enabled = bool(config.get("feature_enabled", config.get("enabled", False)))
    default_provider = str(config.get("provider_key") or "gemini").strip().lower()
    if default_provider not in VALID_PROVIDERS:
        default_provider = "gemini"

    flash_model = str(config.get("flash_model") or "").strip()
    pro_model = str(config.get("pro_model") or "").strip()
    chatgpt_model = str(config.get("chatgpt_model") or "gpt-image-2").strip()
    records = extract_provider_records(config)
    totokens_profiles_all = extract_totokens_profiles(config)
    totokens_rec_raw = records.get("totokens") or {}
    totokens_legacy_key = bool(str(totokens_rec_raw.get("api_key") or config.get("relay_api_key") or "").strip())

    # Order default provider first so frontend natural fallback picks primary route first.
    ordered_keys = [default_provider] + [k for k in VALID_PROVIDERS if k != default_provider]
    providers_out: List[Dict[str, Any]] = []

    for pkey in ordered_keys:
        rec = records.get(pkey) or {}
        raw_models = list(rec.get("models") or _BUILTIN_MODEL_LIST.get(pkey, []))
        pinned: set[str] = set()
        if pkey == default_provider:
            if flash_model:
                pinned.add(flash_model)
            if pro_model:
                pinned.add(pro_model)
        if pkey == "totokens" and chatgpt_model:
            pinned.add(chatgpt_model)
        rec_default = str(rec.get("default_model") or "").strip()
        if rec_default:
            pinned.add(rec_default)

        seed_order: List[str] = []
        if pkey == default_provider:
            if flash_model:
                seed_order.append(flash_model)
            if pro_model:
                seed_order.append(pro_model)
        if pkey == "totokens" and chatgpt_model:
            seed_order.append(chatgpt_model)
        if rec_default:
            seed_order.append(rec_default)
        if pkey == "totokens":
            for prof in totokens_profiles_all:
                if prof.get("default_model"):
                    pinned.add(str(prof["default_model"]).strip())
                    seed_order.append(str(prof["default_model"]).strip())
                for m in prof.get("models") or []:
                    pinned.add(str(m).strip())
                    seed_order.append(str(m).strip())
        for cand in raw_models:
            if is_tryon_image_model_id(cand, pinned):
                seed_order.append(cand)
        for fallback_cand in _BUILTIN_MODEL_LIST.get(pkey, []):
            seed_order.append(fallback_cand)

        final_model_ids = _dedupe_nonempty(seed_order)
        chosen_default_id = (
            (flash_model if pkey == default_provider and flash_model else "")
            or rec_default
            or (chatgpt_model if pkey == "totokens" and chatgpt_model else "")
            or (final_model_ids[0] if final_model_ids else "")
        )
        enabled = bool(rec.get("enabled", False)) and feature_enabled
        if pkey == "totokens":
            any_profile_key = any(bool(p.get("enabled") and (p.get("api_key") or p.get("configured"))) for p in totokens_profiles_all)
            configured = bool(rec.get("configured", False) or (rec.get("enabled", False) and (totokens_legacy_key or any_profile_key))) and feature_enabled
        else:
            configured = bool(rec.get("configured", False)) and feature_enabled

        provider_payload: Dict[str, Any] = {
            "key": pkey,
            "label": _DEFAULT_PROVIDER_META[pkey]["label"],
            "protocol_summary": _DEFAULT_PROVIDER_META[pkey]["protocol_summary"],
            "enabled": enabled,
            "configured": configured,
            "is_default": pkey == default_provider,
            "default_model_id": chosen_default_id,
            "models": [
                describe_model_entry(
                    pkey,
                    mid,
                    flash_model=flash_model,
                    pro_model=pro_model,
                    chatgpt_model=chatgpt_model,
                    default_model_id=chosen_default_id,
                )
                for mid in final_model_ids
            ],
        }
        if pkey == "totokens":
            public_profiles = [
                {
                    "id": prof["id"],
                    "scope": prof["scope"],
                    "label": prof["label"],
                    "builtin": bool(prof.get("builtin", False)),
                    "enabled": bool(prof.get("enabled", False)) and feature_enabled,
                    "configured": bool(feature_enabled and rec.get("enabled", False) and prof.get("enabled", False) and (prof.get("api_key") or prof.get("configured"))),
                    "default_model": prof.get("default_model", ""),
                    "models": list(prof.get("models") or []),
                    "supported_resolutions": list(prof.get("supported_resolutions") or _scope_resolutions(prof["scope"])),
                    "protocol": prof.get("protocol") or _scope_protocol(prof["scope"]),
                }
                for prof in totokens_profiles_all
            ]
            provider_payload["api_profiles"] = public_profiles
            provider_payload["legacy_configured"] = bool(feature_enabled and rec.get("enabled", False) and totokens_legacy_key)
            provider_payload["configured_scopes"] = _dedupe_nonempty([
                p["scope"] for p in public_profiles if p["configured"]
            ])
        providers_out.append(provider_payload)

    # Determine default preset bindings for flash/pro/chatgpt compatibility.
    gemini_rec = next((p for p in providers_out if p["key"] == "gemini"), None)
    totokens_rec = next((p for p in providers_out if p["key"] == "totokens"), None)
    default_rec = next((p for p in providers_out if p["key"] == default_provider), providers_out[0])

    default_model_id = (
        flash_model
        or default_rec.get("default_model_id")
        or MODEL_MAP["flash"]["ids"][0]
    )

    presets = {
        "flash": {
            "provider": default_provider if default_rec["configured"] else ("totokens" if totokens_rec and totokens_rec["configured"] else default_provider),
            "model_id": flash_model or (default_rec["models"][0]["id"] if default_rec["models"] else MODEL_MAP["flash"]["ids"][0]),
        },
        "pro": {
            "provider": default_provider if default_rec["configured"] else ("gemini" if gemini_rec else default_provider),
            "model_id": pro_model or MODEL_MAP["pro"]["ids"][0],
        },
        "chatgpt": {
            "provider": "totokens",
            "model_id": chatgpt_model or "gpt-image-2",
        },
    }

    return {
        "default_provider": default_provider,
        "default_model_id": default_model_id,
        "allow_custom_model": True,
        "providers": providers_out,
        "presets": presets,
        "detail_schema": {
            "aspect_ratios": list(ASPECT_RATIOS),
            "gemini_image_sizes": list(GEMINI_IMAGE_SIZES),
            "gpt_qualities": list(GPT_QUALITIES),
            "temperature": {"min": TEMPERATURE_MIN, "max": TEMPERATURE_MAX, "step": 0.1},
            "seed": {"min": SEED_MIN, "max": SEED_MAX},
        },
    }


def _parse_optional_float(value: Any, name: str, min_val: float, max_val: float) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        value = stripped
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if num != num or num < min_val or num > max_val:
        raise ValueError(f"{name} 必须在 {min_val} 到 {max_val} 之间")
    return round(num, 3)


def _parse_optional_int(value: Any, name: str, min_val: int, max_val: int) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        value = stripped
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是整数")
    try:
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{name} 必须是整数")
        num = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if num < min_val or num > max_val:
        raise ValueError(f"{name} 必须在 {min_val} 到 {max_val} 之间")
    return num


def normalize_tryon_options(
    *,
    aspect_ratio: Any = None,
    image_size: Any = None,
    quality: Any = None,
    temperature: Any = None,
    seed: Any = None,
    totokens_profile: Any = None,
    protocol: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate and normalize API-level try-on generation options.

    Default values ('auto' or None) are omitted from the returned dict so
    requests stay backwards-compatible when no overrides are selected.
    """
    normalized: Dict[str, Any] = {}

    if aspect_ratio is not None:
        ar = str(aspect_ratio).strip()
        if ar and ar.lower() != "auto":
            if ar not in ASPECT_RATIOS:
                raise ValueError(f"不支持的画面比例：{ar}")
            normalized["aspect_ratio"] = ar

    if image_size is not None:
        size = str(image_size).strip()
        if size and size.lower() != "auto":
            upper = size.upper()
            if upper not in GEMINI_IMAGE_SIZES:
                raise ValueError(f"不支持的分辨率档位：{size}")
            allow_openai_res = supports_gpt_multi_resolution(model_id)
            if protocol != "openai_images_edit" or allow_openai_res:
                normalized["image_size"] = upper

    if quality is not None:
        qual = str(quality).strip().lower()
        if qual and qual != "auto":
            if qual not in GPT_QUALITIES:
                raise ValueError(f"不支持的画质档位：{quality}")
            if protocol != "gemini_generate_content":
                normalized["quality"] = qual

    temp_val = _parse_optional_float(temperature, "采样温度 temperature", TEMPERATURE_MIN, TEMPERATURE_MAX)
    if temp_val is not None and protocol != "openai_images_edit":
        normalized["temperature"] = temp_val

    seed_val = _parse_optional_int(seed, "随机种子 seed", SEED_MIN, SEED_MAX)
    if seed_val is not None and protocol != "openai_images_edit":
        normalized["seed"] = seed_val

    cleaned_profile = validate_totokens_profile_id(totokens_profile)
    if cleaned_profile is not None:
        normalized["totokens_profile"] = cleaned_profile

    return normalized


def map_aspect_ratio_to_openai_size(aspect_ratio: Optional[str], image_size: Optional[str] = None) -> Optional[str]:
    """Map semantic aspect ratio + resolution tier ('1K'/'2K'/'4K') to /v1/images/edits size."""
    ar = str(aspect_ratio or "").strip()
    ar_key = ar if (ar and ar.lower() != "auto") else "auto"
    tier = str(image_size or "").strip().upper()
    if tier == "2K":
        return _OPENAI_SIZE_2K_BY_ASPECT.get(ar_key) or _OPENAI_SIZE_2K_BY_ASPECT["auto"]
    if tier == "4K":
        return _OPENAI_SIZE_4K_BY_ASPECT.get(ar_key) or _OPENAI_SIZE_4K_BY_ASPECT["auto"]
    if ar_key == "auto":
        return None
    return _OPENAI_SIZE_BY_ASPECT.get(ar_key)


def map_image_size_to_openai_quality(image_size: Optional[str]) -> Optional[str]:
    """Fallback map if a caller supplies image_size ('1K'/'2K'/'4K') for GPT edits."""
    if not image_size:
        return None
    return _IMAGE_SIZE_TO_OPENAI_QUALITY.get(str(image_size).strip().upper())


def serialize_detail_options(options: Optional[Dict[str, Any]]) -> str:
    if not options:
        return "{}"
    return json.dumps(options, ensure_ascii=False, sort_keys=True)


def parse_detail_options(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
    return {}

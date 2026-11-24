from __future__ import annotations

from copy import deepcopy


PROMPT_LOCALES = ("zh-CN", "en", "ja")

_LABELS = {
    "en": {
        "display": "{name} prompt",
        "description": "Locale-specific instruction for {name}.",
        "role": "You are a professional AI assistant for a down-jacket recommendation platform.",
        "instruction": "Follow the purpose of the {name} prompt and answer in English.",
        "contract": "Preserve canonical enum values, JSON field names, and every placeholder exactly as provided.",
    },
    "ja": {
        "display": "{name} プロンプト",
        "description": "{name} のロケール別指示です。",
        "role": "あなたはダウンジャケット推薦プラットフォームの専門 AI アシスタントです。",
        "instruction": "{name} プロンプトの目的に従い、日本語で回答してください。",
        "contract": "正規化された列挙値、JSON のフィールド名、すべてのプレースホルダーをそのまま保持してください。",
    },
}


def localize_prompt_seed(seed: dict, locale: str) -> dict:
    """Return a complete locale row without copying Chinese prompt content.

    Chinese remains the compatibility source. English and Japanese rows use a
    deterministic, safe system contract until an administrator supplies a
    domain-specific translation; they never silently expose the Chinese row.
    """
    normalized = locale if locale in PROMPT_LOCALES else "zh-CN"
    item = deepcopy(seed)
    item["locale"] = normalized
    if normalized == "zh-CN":
        return item

    labels = _LABELS[normalized]
    variables = ", ".join(f"{{{name}}}" for name in seed.get("variables") or [])
    item["display_name"] = labels["display"].format(name=seed["name"])
    item["description"] = labels["description"].format(name=seed["name"])
    item["content"] = "\n".join(
        part
        for part in (
            labels["role"],
            labels["instruction"].format(name=seed["name"]),
            labels["contract"],
            f"Available placeholders: {variables or '(none)' }.",
            "Return only the format required by the caller and keep the response concise.",
        )
    )
    item["locale"] = normalized
    return item

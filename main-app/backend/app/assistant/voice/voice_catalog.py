"""Voice catalog — manages preset voices and published clone voices.

Preset voices are hardcoded. Clone voices are read from admin DB (if available).
Clone voices not marked as published are never exposed to the main site.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Preset voices — always available
PRESET_VOICES: list[dict[str, Any]] = [
    {"id": "冰糖", "name": "冰糖", "source": "preset", "gender": "female", "language": "zh", "description": "清甜女声"},
    {"id": "茉莉", "name": "茉莉", "source": "preset", "gender": "female", "language": "zh", "description": "温柔女声（默认）"},
    {"id": "苏打", "name": "苏打", "source": "preset", "gender": "female", "language": "zh", "description": "活泼女声"},
    {"id": "白桦", "name": "白桦", "source": "preset", "gender": "male", "language": "zh", "description": "沉稳男声"},
    {"id": "Mia", "name": "Mia", "source": "preset", "gender": "female", "language": "en", "description": "English female"},
    {"id": "Chloe", "name": "Chloe", "source": "preset", "gender": "female", "language": "en", "description": "English female soft"},
    {"id": "Milo", "name": "Milo", "source": "preset", "gender": "male", "language": "en", "description": "English male"},
    {"id": "Dean", "name": "Dean", "source": "preset", "gender": "male", "language": "en", "description": "English male deep"},
]

DEFAULT_VOICE = "茉莉"
AVAILABLE_VOICE_NAMES = [v["id"] for v in PRESET_VOICES]


def get_published_clone_voices() -> list[dict[str, str]]:
    """Read published clone voices from admin DB.

    Returns list of {id, name, source, description, gender, language, provider_voice_id}.
    Returns empty list if DB unavailable or no clone voices configured.
    Only returns voices that are published and enabled.
    Never returns raw sample audio URLs or source_audio_path.
    """
    try:
        from app.ai_runtime_config import _get_engine
        engine = _get_engine()
        if engine is None:
            return []

        from sqlalchemy import MetaData, Table, select, text

        metadata = MetaData()
        # Check if voice_clone_profiles table exists
        try:
            Table("voice_clone_profiles", metadata, autoload_with=engine)
        except Exception:
            return []

        profiles = metadata.tables["voice_clone_profiles"]
        stmt = (
            select(
                profiles.c.id,
                profiles.c.name,
                profiles.c.description,
                profiles.c.gender,
                profiles.c.language,
                profiles.c.is_published,
                profiles.c.enabled,
                profiles.c.provider_voice_id,
            )
            .where(
                profiles.c.is_published.is_(True),
                profiles.c.enabled.is_(True),
            )
        )
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()

        result = []
        for row in rows:
            # Only include profiles that have a real provider_voice_id
            provider_voice_id = row[7] or ""
            if not provider_voice_id:
                continue
            result.append({
                "id": str(row[0]),
                "name": row[1] or "",
                "source": "clone",
                "description": row[2] or "",
                "gender": row[3] or "",
                "language": row[4] or "zh",
                "provider_voice_id": provider_voice_id,
            })
        return result

    except Exception as exc:
        logger.debug("Failed to read clone voices: %s", exc)
        return []


def resolve_voice(voice_name: str | None, clone_voice_id: str | None, voice_source: str | None) -> str:
    """Resolve the effective voice name for TTS calls.

    Priority:
    1. clone_voice_id (if voice_source=clone and voice is published with provider_voice_id)
    2. voice_name (if it's a valid preset)
    3. Default voice "茉莉"

    For clone voices, returns the provider_voice_id (not the DB id) since
    that's what MiMo TTS API expects.

    Falls back to default if clone voice is unavailable.
    """
    if voice_source == "clone" and clone_voice_id:
        # Verify clone voice is published and has provider_voice_id
        published = get_published_clone_voices()
        for v in published:
            if v["id"] == clone_voice_id and v.get("provider_voice_id"):
                return v["provider_voice_id"]
        # Clone not available — fallback
        logger.info("Clone voice '%s' not published or missing provider_voice_id, falling back to default '%s'", clone_voice_id, DEFAULT_VOICE)
        return DEFAULT_VOICE

    if voice_name and voice_name in AVAILABLE_VOICE_NAMES:
        return voice_name

    return DEFAULT_VOICE


def get_all_catalog_items() -> list[dict[str, Any]]:
    """Get all available voice catalog items (presets + published clones).

    Only includes clone voices if voice_clone feature is enabled in backend config.
    """
    items = []
    for v in PRESET_VOICES:
        items.append({
            "id": v["id"],
            "name": v["name"],
            "source": "preset",
            "enabled": True,
            "published": True,
            "description": v.get("description"),
            "gender": v.get("gender"),
            "language": v.get("language"),
        })

    # Only include clone voices if voice_clone feature is enabled
    try:
        from app.ai_runtime_config import resolve_feature_config
        clone_feat = resolve_feature_config("voice_clone", include_disabled=True)
        clone_enabled = clone_feat.get("enabled", False) if clone_feat else False
    except Exception:
        clone_enabled = False

    if clone_enabled:
        for v in get_published_clone_voices():
            items.append({
                "id": v["id"],
                "name": v["name"],
                "source": "clone",
                "enabled": True,
                "published": True,
                "description": v.get("description"),
                "gender": v.get("gender"),
                "language": v.get("language"),
            })

    return items

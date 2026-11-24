"""
Profile logger for the main site.
Call after AI body analysis to store user profile data.

Usage:
    from admin.integration.profile_logger import log_profile
    log_profile(session_id, photo_url, gender, ai_result)
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def log_profile(
    session_id: str,
    photo_url: str | None = None,
    gender: str | None = None,
    mbti: str | None = None,
    color_preference: str | None = None,
    size_input: str | None = None,
    style_input: str | None = None,
    ai_recommended_size: str | None = None,
    ai_body_shape: str | None = None,
    ai_suggested_style: str | None = None,
    ai_reasoning: str | None = None,
    used_fallback: bool = False,
) -> bool:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return False
    try:
        engine = create_engine(url)
        from admin.backend.app.database import UserProfile
        with Session(engine) as db:
            profile = UserProfile(
                session_id=session_id,
                photo_url=photo_url,
                gender=gender,
                mbti=mbti,
                color_preference=color_preference,
                size_input=size_input,
                style_input=style_input,
                ai_recommended_size=ai_recommended_size,
                ai_body_shape=ai_body_shape,
                ai_suggested_style=ai_suggested_style,
                ai_reasoning=ai_reasoning,
                used_fallback=used_fallback,
            )
            db.add(profile)
            db.commit()
        return True
    except Exception:
        return False

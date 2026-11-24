"""
Prompt loader for the main site.
Replaces hardcoded prompts with database-managed versions.

Usage:
    from admin.integration.prompt_loader import load_prompt
    prompt = load_prompt("body_analysis", variables={"user_gender": "男"})
"""
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@lru_cache(maxsize=1)
def _get_engine():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return None
    return create_engine(url)


def load_prompt(name: str, variables: dict[str, str] | None = None, locale: str | None = None) -> str | None:
    """Load a prompt from the admin database, with variable substitution."""
    engine = _get_engine()
    if not engine:
        return None

    try:
        from admin.backend.app.database import PromptConfig
        with Session(engine) as session:
            from admin.backend.app.i18n.locale import DEFAULT_LOCALE, normalize_locale
            requested_locale = normalize_locale(locale) or DEFAULT_LOCALE
            configs = session.query(PromptConfig).filter(
                PromptConfig.name == name,
                PromptConfig.is_active.is_(True),
                PromptConfig.locale.in_([requested_locale, DEFAULT_LOCALE]),
            ).all()
            config = next((item for item in configs if item.locale == requested_locale), None)
            config = config or next((item for item in configs if item.locale == DEFAULT_LOCALE), None)
            if not config:
                return None
            content = config.content
            if variables:
                for k, v in variables.items():
                    content = content.replace(f"{{{{{k}}}}}", v)
            return content
    except Exception:
        return None

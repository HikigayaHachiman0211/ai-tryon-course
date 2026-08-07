"""Prompt loader for the main site.

Reads active prompts from admin DB prompt_configs table,
falls back to hardcoded defaults if DB is unavailable.

Usage:
    from app.prompt_loader import load_active_prompt
    prompt = load_active_prompt("mimo_image_profile_analysis", fallback="default prompt text")
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Reuse the shared DB URL resolution from ai_runtime_config
# This ensures both modules always point to the same database.


def _get_engine():
    """Get or create a cached SQLAlchemy engine via ai_runtime_config.

    This ensures prompt_loader and ai_runtime_config always use the same DB.
    """
    from app.ai_runtime_config import _get_engine as _get_ai_engine
    return _get_ai_engine()


def load_active_prompt(
    name: str,
    fallback: str,
    variables: dict[str, str] | None = None,
) -> str:
    """Load an active prompt from the database with optional variable substitution.

    Args:
        name: The prompt name (matches prompt_configs.name where is_active=true).
        fallback: Default content to return if DB read fails or prompt not found.
        variables: Optional dict of {key: value} for {key} placeholder substitution.

    Returns:
        The prompt content with variables substituted, or fallback on any error.
    """
    engine = _get_engine()
    if engine is None:
        return _apply_variables(fallback, variables)

    try:
        from sqlalchemy import MetaData, Table, select

        metadata = MetaData()
        prompts = Table("prompt_configs", metadata, autoload_with=engine)
        stmt = (
            select(
                prompts.c.content,
                prompts.c.is_active,
            )
            .where(
                prompts.c.name == name,
                prompts.c.is_active.is_(True),
            )
        )
        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            if not row:
                logger.debug("Prompt '%s' not found or not active, using fallback", name)
                return _apply_variables(fallback, variables)

            content = row[0] or fallback
            return _apply_variables(content, variables)
    except Exception as exc:
        # Table doesn't exist, DB unavailable, etc. — never crash the main site.
        logger.debug("Failed to load prompt '%s': %s — using fallback", name, exc)
        return _apply_variables(fallback, variables)


def _apply_variables(content: str, variables: dict[str, str] | None) -> str:
    """Apply variable substitution to prompt content.

    Uses {key} placeholder format (single braces, matching DB storage format).
    """
    if not variables:
        return content
    result = content
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result

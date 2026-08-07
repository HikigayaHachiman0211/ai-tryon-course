from __future__ import annotations

import base64
import hashlib
import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fernet encryption (lazy import to avoid hard dependency at module level)
# ---------------------------------------------------------------------------

_fernet = None
_fernet_warning_issued = False


def _is_production() -> bool:
    """Check if running in production environment.

    Recognises:
    - APP_ENV=production / prod
    - ENV=production / prod
    - K_SERVICE exists (Cloud Run) unless APP_ENV=development is explicit
    """
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if app_env in ("production", "prod"):
        return True
    if app_env == "development":
        return False
    env = os.getenv("ENV", "").strip().lower()
    if env in ("production", "prod"):
        return True
    # Cloud Run sets K_SERVICE — treat as production unless explicitly dev
    if os.getenv("K_SERVICE"):
        return True
    return False


def _get_fernet():
    global _fernet, _fernet_warning_issued
    if _fernet is not None:
        return _fernet

    key = os.getenv("FERNET_SECRET_KEY", "").strip()
    if not key:
        if not _fernet_warning_issued:
            if _is_production():
                logger.error(
                    "FERNET_SECRET_KEY is not set in production! "
                    "API key storage is DISABLED. Set FERNET_SECRET_KEY immediately."
                )
            else:
                logger.warning(
                    "FERNET_SECRET_KEY is not set. Dev-only fallback: API keys will "
                    "be stored with base64 obfuscation. NOT suitable for production."
                )
            _fernet_warning_issued = True
        return None

    try:
        from cryptography.fernet import Fernet

        # Allow raw passphrase: derive a valid Fernet key from it
        if len(key) != 44 or not key.endswith("="):
            key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        _fernet = Fernet(key)
        return _fernet
    except Exception as exc:
        logger.error("Failed to initialise Fernet: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encrypt_secret(value: str) -> str:
    """Encrypt a secret string. Returns a prefixed ciphertext string.

    In production without FERNET_SECRET_KEY, raises RuntimeError.
    In dev without FERNET_SECRET_KEY, uses base64 obfuscation with warning.
    """
    if not value:
        return ""
    f = _get_fernet()
    if f is not None:
        return "fernet:" + f.encrypt(value.encode("utf-8")).decode("ascii")
    # Production without Fernet key → refuse to store
    if _is_production():
        raise RuntimeError(
            "Cannot encrypt API key: FERNET_SECRET_KEY is not set in production. "
            "Refusing to store as plaintext."
        )
    # Dev-only fallback: base64 obfuscation (NOT real encryption)
    return "b64:" + base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    """Decrypt a secret string previously encrypted with encrypt_secret.

    Unknown format → raise ValueError (never return as-is).
    """
    if not value:
        return ""
    if value.startswith("fernet:"):
        f = _get_fernet()
        if f is None:
            raise RuntimeError("Fernet key unavailable — cannot decrypt")
        return f.decrypt(value[7:].encode("ascii")).decode("utf-8")
    if value.startswith("b64:"):
        if _is_production():
            raise RuntimeError("Cannot decrypt b64-encoded secret in production (FERNET_SECRET_KEY required)")
        return base64.urlsafe_b64decode(value[4:].encode("ascii")).decode("utf-8")
    # Unknown format — do NOT return as plaintext
    raise ValueError(f"Unknown secret format (prefix={value[:8]}...). Cannot decrypt safely.")


def mask_secret(value: str) -> str:
    """Return a masked version of a secret for display.

    Examples:
        "sk-abcdefghijklmnop" -> "sk-****mnop"
        "short"               -> "****"
        ""                    -> ""
    """
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:3] + "****" + value[-4:]


def sanitize_error_message(message: str) -> str:
    """Strip sensitive data from error messages before logging/display."""
    text = message
    # Authorization headers
    text = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+\S+",
        "Authorization: Bearer [REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # api-key headers
    text = re.sub(
        r"api[_-]?key\s*[:=]\s*\S+",
        "api-key=[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # Query-string keys
    text = re.sub(r"\?key=\S+", "?key=[REDACTED]", text, flags=re.IGNORECASE)
    # Standalone Bearer tokens
    text = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    # Base64 data URLs
    text = re.sub(
        r"data:[a-z]+/[a-z]+;base64,[A-Za-z0-9+/=]{40,}",
        "data:[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # Truncate
    if len(text) > 500:
        text = text[:500] + "..."
    return text

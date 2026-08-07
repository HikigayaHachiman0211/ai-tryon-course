"""In-memory rate limiter for ASR and TTS endpoints.

Development version — replace with Redis-based limiter for production.
Uses session_id as the rate limit key.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Literal

# Rate limit windows
_ASR_LIMIT = 5      # per session per minute
_TTS_LIMIT = 10     # per session per minute
_WINDOW_SECONDS = 60

# {key: [timestamp, ...]}
_buckets: dict[str, list[float]] = defaultdict(list)


def _cleanup_old_entries(key: str, now: float) -> None:
    """Remove entries older than the window; delete empty buckets to bound memory."""
    bucket = _buckets[key]
    cutoff = now - _WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if not bucket:
        del _buckets[key]


def check_rate_limit(session_id: str, endpoint: Literal["asr", "tts"]) -> tuple[bool, str]:
    """Check if the request is within rate limits.

    Returns (allowed, error_message).
    """
    if not session_id:
        return True, ""

    now = time.time()
    key = f"{endpoint}:{session_id}"
    _cleanup_old_entries(key, now)

    limit = _ASR_LIMIT if endpoint == "asr" else _TTS_LIMIT
    count = len(_buckets[key])

    if count >= limit:
        remaining = int(_WINDOW_SECONDS - (now - _buckets[key][0]))
        return False, f"请求过于频繁，请 {remaining} 秒后重试。"

    _buckets[key].append(now)
    return True, ""


def get_rate_limit_info(session_id: str, endpoint: Literal["asr", "tts"]) -> dict:
    """Get current rate limit status for a session."""
    now = time.time()
    key = f"{endpoint}:{session_id}"
    _cleanup_old_entries(key, now)

    limit = _ASR_LIMIT if endpoint == "asr" else _TTS_LIMIT
    count = len(_buckets[key])

    return {
        "limit": limit,
        "remaining": max(0, limit - count),
        "window_seconds": _WINDOW_SECONDS,
    }

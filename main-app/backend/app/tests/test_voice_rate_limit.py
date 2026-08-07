"""Tests for voice rate limiter — no credentials or network access required.

Run:
  cd backend && python -m unittest app.tests.test_voice_rate_limit
"""
from __future__ import annotations

import importlib
import sys
import types
import unittest


def _fresh_module() -> types.ModuleType:
    """Import voice_rate_limit with a clean bucket state for each test."""
    mod_name = "app.assistant.voice.voice_rate_limit"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestVoiceRateLimit(unittest.TestCase):

    def test_asr_limit_enforced(self) -> None:
        """ASR limit (5/min) is enforced per session."""
        rl = _fresh_module()
        sid = "test-session-asr"
        for i in range(5):
            allowed, msg = rl.check_rate_limit(sid, "asr")
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
        allowed, msg = rl.check_rate_limit(sid, "asr")
        self.assertFalse(allowed)
        self.assertIn("秒", msg)

    def test_tts_limit_enforced(self) -> None:
        """TTS limit (10/min) is enforced per session."""
        rl = _fresh_module()
        sid = "test-session-tts"
        for i in range(10):
            allowed, _ = rl.check_rate_limit(sid, "tts")
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
        allowed, msg = rl.check_rate_limit(sid, "tts")
        self.assertFalse(allowed)

    def test_different_sessions_independent(self) -> None:
        """Rate limits are per session — one session exhausted does not block another."""
        rl = _fresh_module()
        for _ in range(5):
            rl.check_rate_limit("session-a", "asr")
        # session-a is exhausted
        allowed_a, _ = rl.check_rate_limit("session-a", "asr")
        self.assertFalse(allowed_a)
        # session-b is unaffected
        allowed_b, _ = rl.check_rate_limit("session-b", "asr")
        self.assertTrue(allowed_b)

    def test_empty_session_bypasses_limit(self) -> None:
        """Empty session_id is never rate-limited (legacy behaviour preserved)."""
        rl = _fresh_module()
        for _ in range(100):
            allowed, msg = rl.check_rate_limit("", "asr")
            self.assertTrue(allowed)
            self.assertEqual(msg, "")

    def test_window_expiry_allows_new_requests(self) -> None:
        """Entries outside the 60-second window are pruned; new requests are allowed."""
        rl = _fresh_module()
        sid = "test-window"
        now = 1_000_000.0
        window = rl._WINDOW_SECONDS  # 60

        # Fill bucket with timestamps from the previous window
        key = f"asr:{sid}"
        rl._buckets[key] = [now - window - 10] * rl._ASR_LIMIT

        # All old entries should be pruned; new request allowed
        import time
        original_time = time.time
        time.time = lambda: now  # type: ignore[method-assign]
        try:
            allowed, _ = rl.check_rate_limit(sid, "asr")
        finally:
            time.time = original_time  # type: ignore[method-assign]

        self.assertTrue(allowed, "Old-window entries should be pruned; request should be allowed")

    def test_expired_bucket_keys_pruned(self) -> None:
        """Empty buckets are deleted from _buckets after cleanup to bound memory."""
        rl = _fresh_module()
        sid = "test-prune"
        key = f"asr:{sid}"
        now = 1_000_000.0
        window = rl._WINDOW_SECONDS

        # Seed bucket with one expired entry
        rl._buckets[key] = [now - window - 5]
        self.assertIn(key, rl._buckets)

        # Trigger cleanup
        rl._cleanup_old_entries(key, now)

        # Bucket key must be gone
        self.assertNotIn(key, rl._buckets,
                         "Empty bucket key should be deleted to prevent unbounded growth")

    def test_get_rate_limit_info(self) -> None:
        """get_rate_limit_info returns correct limit, remaining, and window."""
        rl = _fresh_module()
        sid = "test-info"
        info = rl.get_rate_limit_info(sid, "asr")
        self.assertEqual(info["limit"], rl._ASR_LIMIT)
        self.assertEqual(info["remaining"], rl._ASR_LIMIT)
        self.assertEqual(info["window_seconds"], rl._WINDOW_SECONDS)

        rl.check_rate_limit(sid, "asr")
        info = rl.get_rate_limit_info(sid, "asr")
        self.assertEqual(info["remaining"], rl._ASR_LIMIT - 1)


if __name__ == "__main__":
    unittest.main()

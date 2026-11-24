from app.assistant.voice import voice_rate_limit as limiter


def test_expired_voice_sessions_are_reclaimed_without_resetting_active_limits(monkeypatch):
    limiter._buckets.clear()
    clock = [1000.0]
    monkeypatch.setattr(limiter.time, "time", lambda: clock[0])
    for index in range(1000):
        assert limiter.check_rate_limit(str(index), "asr")[0]
    clock[0] = 1041.0
    for _ in range(5):
        assert limiter.check_rate_limit("active", "asr")[0]
    clock[0] = 1061.0
    limiter.check_rate_limit("new", "tts")
    assert len(limiter._buckets) == 2
    assert not limiter.check_rate_limit("active", "asr")[0]

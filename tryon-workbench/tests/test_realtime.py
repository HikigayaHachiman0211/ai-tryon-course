import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from app import realtime_budget as budget
from app import realtime_routes as routes
from app.task_db import ensure_task_tables, reset_engine_cache


ORIGIN = {"Origin": "http://testserver"}
ACCESS = "demo-pass-for-test-only"
REQUEST = {"access_code": ACCESS, "seconds": 10, "max_cents": 20}
START = "/api/realtime-tryon/sessions"
JPEG = "/9j/AA=="


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for name in ("APP_ENV", "WORKBENCH_PUBLIC_URL", "DECART_REALTIME_ORIGIN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'realtime.db').as_posix()}")
    monkeypatch.setenv("DECART_REALTIME_ENABLED", "true")
    monkeypatch.setenv("DECART_REALTIME_ACCESS_CODE", ACCESS)
    monkeypatch.setenv("DECART_API_KEY", "provider-test-key")
    ensure_task_tables()
    yield budget.load_settings()
    reset_engine_cache()


@pytest.fixture
def client(cfg):
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as test_client:
        yield test_client


def test_config_is_disabled_until_explicitly_enabled(client, monkeypatch):
    monkeypatch.setenv("DECART_REALTIME_ENABLED", "false")
    assert client.get("/api/realtime-tryon/config").json() == {"available": False}
    assert client.post(START, json=REQUEST, headers=ORIGIN).status_code == 503


def test_start_requires_cookie_origin_code_and_matching_quote(client):
    assert client.post(START, json=REQUEST, headers=ORIGIN).status_code == 403
    config = client.get("/api/realtime-tryon/config")
    assert config.json() == {"available": True, "model": budget.MODEL, "min_seconds": 10, "max_seconds": 20, "cents_per_second": 2}
    assert "HttpOnly" in config.headers["set-cookie"]
    assert client.post(START, json=REQUEST, headers={"Origin": "https://other.example"}).status_code == 403
    assert client.post(START, json=REQUEST | {"access_code": "wrong"}, headers=ORIGIN).status_code == 403
    assert client.post(START, json=REQUEST | {"max_cents": 19}, headers=ORIGIN).status_code == 409
    assert client.post(START, json=REQUEST | {"seconds": 9, "max_cents": 18}, headers=ORIGIN).status_code == 400
    ticket = client.post(START, json=REQUEST, headers=ORIGIN).json()
    assert ticket["state"] == "reserved" and ticket["accounted_cents"] == 20
    assert client.post(f"{START}/{ticket['id']}/stop", headers=ORIGIN).status_code == 200
    assert client.get(f"{START}/{ticket['id']}").json()["accounted_cents"] == 0


def test_atomic_global_budget_and_single_claim(cfg):
    cfg = replace(cfg, max_active=5, starts_per_minute=10, daily_cents=40)
    now = datetime(2026, 11, 22, 10, tzinfo=budget.BUDGET_ZONE).timestamp()

    def enter(index):
        try:
            return budget.reserve(cfg, f"visitor-{index}", 20, now=now)
        except budget.BudgetDenied as exc:
            return str(exc)

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(enter, range(8)))
    admitted = [row for row in results if not isinstance(row, str)]
    assert len(admitted) == 1
    assert results.count("daily_budget") == 7
    row = admitted[0]
    assert budget.claim(row.id, "other-browser", now=now) is None
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda _: budget.claim(row.id, row.visitor_hash, now=now), range(2)))
    assert sum(claim is not None for claim in claims) == 1


def test_expiry_conservative_settlement_and_calendar_caps(cfg):
    cfg = replace(cfg, daily_cents=60, monthly_cents=60, visitor_daily_cents=40)
    date = datetime(2026, 11, 22, 10, tzinfo=budget.BUDGET_ZONE)
    now = date.timestamp()
    stale = budget.reserve(cfg, "a", 20, now=now)
    with pytest.raises(budget.BudgetDenied, match="visitor_busy"):
        budget.reserve(cfg, "a", 10, now=now + 1)
    assert budget.claim(stale.id, "a", now=now + 16) is None
    assert budget.receipt(stale, now=now + 16)["accounted_cents"] == 0
    row = budget.reserve(cfg, "a", 20, now=now + 16)
    row = budget.claim(row.id, "a", now=now + 17)
    budget.finalize(row, reason="disconnect", provider_session_id=None, provider_seconds=None, join_sent=True)
    assert budget.get_receipt(row.id, "a")["accounted_cents"] == 40
    with pytest.raises(budget.BudgetDenied, match="visitor_budget"):
        budget.reserve(cfg, "a", 10, now=now + 75)
    with pytest.raises(budget.BudgetDenied, match="monthly_budget"):
        budget.reserve(cfg, "a", 20, now=now + 86400)
    near_midnight = date.replace(hour=23, minute=59, second=55).timestamp()
    with pytest.raises(budget.BudgetDenied, match="budget_reset"):
        budget.reserve(cfg, "b", 10, now=near_midnight)


def test_provider_token_and_websocket_are_pinned_to_standard_720p(monkeypatch):
    calls = {}

    def tokens(request):
        calls["token"] = json.loads(request.content)
        assert request.url.path == "/v1/client/tokens"
        assert request.headers["x-api-key"] == "fake"
        return httpx.Response(200, json={
            "apiKey": "scoped-token", "constraints": calls["token"]["constraints"],
        })

    monkeypatch.setattr(routes, "httpx", SimpleNamespace(
        AsyncClient=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(tokens), **kwargs),
    ))

    async def connect(url, **kwargs):
        calls["stream"] = parse_qs(urlsplit(url).query)

    monkeypatch.setattr(routes, "connect", connect)
    asyncio.run(routes.open_provider("fake", 20, "vp8"))
    assert calls["token"] == {
        "expiresIn": 15, "allowedModels": [budget.MODEL],
        "constraints": {"realtime": {"maxSessionDuration": 20}},
    }
    assert calls["stream"] == {
        "model": [budget.MODEL], "resolution": ["720p"], "api_key": ["scoped-token"],
        "livekit_server_codec": ["vp8"], "user_agent": [routes.PROVIDER_USER_AGENT],
    }


def test_websocket_forwards_garment_and_settles_only_provider_usage(client, monkeypatch):
    calls = []

    class Provider:
        def __init__(self):
            self.events = asyncio.Queue()
            self.closed = False

        async def send(self, raw):
            signal = json.loads(raw)
            calls.append(signal)
            if signal["type"] == "livekit_join":
                self.events.put_nowait({"type": "livekit_room_info", "session_id": "provider-session"})
            else:
                self.events.put_nowait({"type": "generation_ended", "seconds": 3.2, "reason": "timeout"})

        def __aiter__(self):
            return self

        async def __anext__(self):
            return json.dumps(await self.events.get())

        async def close(self):
            self.closed = True

    upstream = Provider()

    async def open_provider(api_key, seconds, safari_codec):
        assert api_key == "provider-test-key" and seconds == 10
        return upstream

    monkeypatch.setattr(routes, "open_provider", open_provider)
    client.get("/api/realtime-tryon/config")
    ticket = client.post(START, json=REQUEST, headers=ORIGIN).json()["id"]
    socket_url = f"/api/realtime-tryon/v1/stream?ticket={ticket}&model={budget.MODEL}"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(socket_url + "&speed=fast", headers=ORIGIN):
            pytest.fail("Fast mode was accepted")
    with client.websocket_connect(socket_url, headers=ORIGIN) as websocket:
        websocket.send_json({"type": "livekit_join", "passthrough": True})
        assert websocket.receive_json()["session_id"] == "provider-session"
        websocket.send_json({"type": "set_image", "image_data": JPEG, "prompt": "Try on the jacket"})
        assert websocket.receive_json()["seconds"] == 3.2
        assert websocket.receive()["type"] == "websocket.close"
    assert upstream.closed
    assert calls == [
        {"type": "livekit_join", "passthrough": False},
        {"type": "set_image", "image_data": JPEG, "prompt": "Try on the jacket", "enhance_prompt": False},
    ]
    receipt = client.get(f"{START}/{ticket}").json()
    assert receipt["state"] == "ended" and receipt["accounted_cents"] == 8
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(socket_url, headers=ORIGIN):
            pytest.fail("Previously claimed ticket was accepted")


def test_backend_stops_at_deadline_when_provider_stays_open(client, monkeypatch):
    monkeypatch.setattr(budget, "MIN_SECONDS", 1)
    closed = []

    class SilentProvider:
        async def send(self, raw):
            assert json.loads(raw)["type"] == "livekit_join"

        async def __aiter__(self):
            await asyncio.Future()
            yield

        async def close(self):
            closed.append(True)

    async def open_provider(*args):
        return SilentProvider()

    monkeypatch.setattr(routes, "open_provider", open_provider)
    client.get("/api/realtime-tryon/config")
    ticket = client.post(START, json=REQUEST | {"seconds": 1, "max_cents": 2}, headers=ORIGIN).json()["id"]
    with client.websocket_connect(f"/api/realtime-tryon/v1/stream?ticket={ticket}&model={budget.MODEL}", headers=ORIGIN) as websocket:
        websocket.send_json({"type": "livekit_join"})
        assert websocket.receive()["type"] == "websocket.close"
    assert closed == [True]
    receipt = client.get(f"{START}/{ticket}").json()
    assert receipt["reason"] == "timeout" and receipt["accounted_cents"] == 2


def test_admin_db_config_loading_cache_clear_and_optional_access_code(tmp_path, monkeypatch):
    import base64
    from sqlalchemy import create_engine, text

    db_file = tmp_path / "admin_shared.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE ai_api_providers ("
            "id INTEGER PRIMARY KEY, provider_key VARCHAR(50), enabled BOOLEAN, api_key_encrypted TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE ai_feature_configs ("
            "id INTEGER PRIMARY KEY, feature_key VARCHAR(50), enabled BOOLEAN, config TEXT)"
        ))
        enc_key = "b64:" + base64.urlsafe_b64encode(b"decart-db-secret-key").decode("ascii")
        enc_code = "b64:" + base64.urlsafe_b64encode(b"db-access-code-123456").decode("ascii")
        cfg_json = json.dumps({
            "require_access_code": False,
            "access_code_encrypted": enc_code,
            "max_seconds": 30,
            "default_seconds": 12,
            "cents_per_second": 3,
            "daily_cents": 300,
            "monthly_cents": 1500,
            "visitor_daily_cents": 90,
            "max_active": 2,
            "starts_per_minute": 5,
            "origin": "https://workbench.example.test",
            "default_prompt": "Keep quilting crisp",
        })
        conn.execute(
            text("INSERT INTO ai_api_providers (provider_key, enabled, api_key_encrypted) VALUES ('decart', 1, :k)"),
            {"k": enc_key},
        )
        conn.execute(
            text("INSERT INTO ai_feature_configs (feature_key, enabled, config) VALUES ('tryon_realtime', 1, :c)"),
            {"c": cfg_json},
        )

    for env_name in ("DECART_REALTIME_ENABLED", "DECART_API_KEY", "DECART_REALTIME_ACCESS_CODE", "DECART_REALTIME_ORIGIN", "WORKBENCH_PUBLIC_URL", "APP_ENV"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", db_url)
    monkeypatch.setenv("AI_CONFIG_DATABASE_URL", db_url)
    budget.clear_settings_cache()
    ensure_task_tables(db_url)

    try:
        loaded = budget.load_settings()
        assert loaded.source == "admin_db"
        assert loaded.enabled is True
        assert loaded.available is True
        assert loaded.api_key == "decart-db-secret-key"
        assert loaded.require_access_code is False
        assert loaded.max_seconds == 30
        assert loaded.default_seconds == 12
        assert loaded.cents_per_second == 3
        assert loaded.origin == "https://workbench.example.test"
        assert loaded.default_prompt == "Keep quilting crisp"

        app = FastAPI()
        app.include_router(routes.router)
        with TestClient(app, base_url="https://workbench.example.test") as tc:
            st = tc.get("/api/realtime-tryon/status").json()
            assert st["available"] is True
            assert st["require_access_code"] is False
            assert st["default_seconds"] == 12
            assert st["quota"]["visitor_remaining_cents"] == 90
            assert st["quota"]["can_start_min_session"] is True

            ticket = tc.post(
                START,
                json={"access_code": "", "seconds": 10, "max_cents": 30},
                headers={"Origin": "https://workbench.example.test"},
            )
            assert ticket.status_code == 201

        # Hot reload after DB disable + cache clear
        with engine.begin() as conn:
            conn.execute(text("UPDATE ai_feature_configs SET enabled = 0 WHERE feature_key = 'tryon_realtime'"))
        budget.clear_settings_cache()
        reloaded = budget.load_settings()
        assert reloaded.enabled is False
        assert reloaded.available is False
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()
        engine.dispose()


def test_status_endpoint_reasons_origin_fallback_and_diagnose(tmp_path, monkeypatch):
    for env_name in ("APP_ENV", "WORKBENCH_PUBLIC_URL", "DECART_REALTIME_ORIGIN", "AI_CONFIG_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'status.db').as_posix()}")
    monkeypatch.setenv("ROUTER01_MEDIA_BASE_URL", "https://media.example.test/")
    monkeypatch.setenv("DECART_REALTIME_ENABLED", "false")
    monkeypatch.delenv("DECART_API_KEY", raising=False)
    budget.clear_settings_cache()
    ensure_task_tables()

    try:
        diag = budget.diagnose_settings()
        assert diag["enabled"] is False
        assert diag["available"] is False
        assert diag["origin_https"] is True

        app = FastAPI()
        app.include_router(routes.router)
        with TestClient(app) as tc:
            resp = tc.get("/api/realtime-tryon/status")
            assert resp.status_code == 200
            assert resp.json() == {"available": False, "reason": "disabled"}

            monkeypatch.setenv("DECART_REALTIME_ENABLED", "true")
            assert tc.get("/api/realtime-tryon/status").json() == {"available": False, "reason": "missing_api_key"}

            monkeypatch.setenv("DECART_API_KEY", "k-123")
            monkeypatch.setenv("DECART_REALTIME_ACCESS_CODE", "short")
            assert tc.get("/api/realtime-tryon/status").json() == {"available": False, "reason": "missing_access_code"}
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()


def test_xmax_disabled_by_default_and_providers_endpoint(tmp_path, monkeypatch):
    for name in (
        "APP_ENV",
        "DECART_REALTIME_ENABLED",
        "XMAX_REALTIME_ENABLED",
        "XMAX_API_KEY",
        "XMAX_REALTIME_ACCESS_CODE",
        "AI_CONFIG_DATABASE_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'xmax_off.db').as_posix()}")
    budget.clear_settings_cache()
    ensure_task_tables()
    try:
        app = FastAPI()
        app.include_router(routes.router)
        with TestClient(app) as tc:
            resp = tc.get("/api/realtime-tryon/providers")
            assert resp.status_code == 200
            data = resp.json()
            assert data["any_available"] is False
            assert data["providers"]["decart"]["available"] is False
            assert data["providers"]["xmax"]["available"] is False
            assert tc.post("/api/realtime-tryon/xmax/sessions", json={"access_code": ACCESS, "seconds": 30, "max_cents": 5}).status_code == 503
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()


def test_xmax_admission_balance_guard_token_attach_and_settlement(tmp_path, monkeypatch):
    for name in ("APP_ENV", "WORKBENCH_PUBLIC_URL", "XMAX_REALTIME_ORIGIN", "AI_CONFIG_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'xmax_on.db').as_posix()}")
    monkeypatch.setenv("XMAX_REALTIME_ENABLED", "true")
    monkeypatch.setenv("XMAX_API_KEY", "uk-xmax-master-secret")
    monkeypatch.setenv("XMAX_REALTIME_ACCESS_CODE", ACCESS)
    monkeypatch.setenv("XMAX_REALTIME_MIN_ACCOUNT_CREDITS", "60")
    monkeypatch.setenv("XMAX_REALTIME_CENTS_PER_MINUTE", "10")
    monkeypatch.setenv("XMAX_REALTIME_VISITOR_DAILY_CENTS", "20")
    budget.clear_settings_cache()
    ensure_task_tables()

    upstream_calls = []

    async def fake_balance(api_key, *, base_url, timeout=10.0):
        upstream_calls.append(("balance", api_key, base_url))
        return 25.0  # below min_account_credits=60 initially

    async def fake_create_tk(api_key, *, base_url, expire_seconds, points_limit, session_limit=1, timeout=10.0):
        upstream_calls.append(("create_tk", api_key, expire_seconds, points_limit, session_limit))
        return {
            "uid": "utk-123456",
            "temporaryApiKey": "tk-temp-issued-secret",
            "pointsLimit": points_limit,
            "expireTimestamp": "2026-11-23T12:00:00+00:00",
        }

    async def fake_close_session(api_key, session_uid, *, base_url, timeout=10.0):
        upstream_calls.append(("close_session", session_uid))

    async def fake_deactivate(api_key, temp_key, *, base_url, timeout=10.0):
        upstream_calls.append(("deactivate_tk", temp_key))
        return {"temporaryApiKey": temp_key, "status": "inactive", "consumedCredit": 12}

    async def fake_tk_status(api_key, temp_key, *, base_url, timeout=10.0):
        upstream_calls.append(("status_tk", temp_key))
        return {"temporaryApiKey": temp_key, "status": "inactive", "consumedCredit": 12}

    monkeypatch.setattr(routes.xmax_client, "get_balance", fake_balance)
    monkeypatch.setattr(routes.xmax_client, "create_temporary_api_key", fake_create_tk)
    monkeypatch.setattr(routes.xmax_client, "close_session", fake_close_session)
    monkeypatch.setattr(routes.xmax_client, "deactivate_temporary_api_key", fake_deactivate)
    monkeypatch.setattr(routes.xmax_client, "get_temporary_api_key_status", fake_tk_status)

    try:
        app = FastAPI()
        app.include_router(routes.router)
        with TestClient(app) as tc:
            p = tc.get("/api/realtime-tryon/providers").json()
            assert p["any_available"] is True
            assert p["default_provider"] == "xmax"
            assert p["providers"]["xmax"]["available"] is True

            # Wrong quote rejected
            bad_quote = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 30, "max_cents": 99, "model": "x2.1"},
                headers=ORIGIN,
            )
            assert bad_quote.status_code == 409

            # Insufficient balance releases reservation to 0
            r1 = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 30, "max_cents": 5, "model": "x2.1"},
                headers=ORIGIN,
            )
            assert r1.status_code == 201
            sid1 = r1.json()["id"]
            tok1 = tc.post(f"/api/realtime-tryon/xmax/sessions/{sid1}/token", json={}, headers=ORIGIN)
            assert tok1.status_code == 429
            assert tok1.json()["error"]["code"] == "insufficient_credits"
            assert tc.get(f"/api/realtime-tryon/sessions/{sid1}").json()["accounted_cents"] == 0

            # Top up balance -> issues scoped tk- key & enforces settle on stop
            async def healthy_balance(api_key, *, base_url, timeout=10.0):
                upstream_calls.append(("balance_ok",))
                return 500.0

            monkeypatch.setattr(routes.xmax_client, "get_balance", healthy_balance)
            r2 = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 30, "max_cents": 5, "model": "x2.1"},
                headers=ORIGIN,
            )
            assert r2.status_code == 201
            sid2 = r2.json()["id"]

            tok2 = tc.post(f"/api/realtime-tryon/xmax/sessions/{sid2}/token", json={}, headers=ORIGIN)
            assert tok2.status_code == 200
            tok_data = tok2.json()
            assert tok_data["temporary_api_key"] == "tk-temp-issued-secret"
            assert tok_data["environment"] == "global"
            assert tok_data["model"] == "x2.1"
            assert tok_data["max_credits"] == 30
            assert "uk-xmax-master-secret" not in str(tok_data)

            # Single-use token endpoint rejects replay
            assert tc.post(f"/api/realtime-tryon/xmax/sessions/{sid2}/token", json={}, headers=ORIGIN).status_code == 409

            # Attach provider session ID and stop
            att = tc.post(
                f"/api/realtime-tryon/xmax/sessions/{sid2}/attach",
                json={"provider_session_id": "ums-xmax-live-99"},
                headers=ORIGIN,
            )
            assert att.status_code == 200
            stp = tc.post(f"/api/realtime-tryon/sessions/{sid2}/stop", json={}, headers=ORIGIN)
            assert stp.status_code == 200

            rcpt = tc.get(f"/api/realtime-tryon/sessions/{sid2}").json()
            assert rcpt["provider_key"] == "xmax"
            assert rcpt["state"] == "ended"
            assert rcpt["provider_credits"] == 12.0
            assert rcpt["provider_seconds"] == 12.0
            # 12 credits / 1 cps = 12s -> ceil(12 * 10 / 60) = 2 cents
            assert rcpt["accounted_cents"] == 2
            row = budget.get_session_row(sid2)
            assert row is not None and row.provider_temp_key_encrypted is None
            assert ("close_session", "ums-xmax-live-99") in upstream_calls
            assert ("deactivate_tk", "tk-temp-issued-secret") in upstream_calls
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()


def test_xmax_admin_db_config_loading_and_diagnose(tmp_path, monkeypatch):
    import base64
    from sqlalchemy import create_engine, text

    db_file = tmp_path / "admin_xmax.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE ai_api_providers ("
            "id INTEGER PRIMARY KEY, provider_key VARCHAR(50), enabled BOOLEAN, base_url VARCHAR(500), default_model VARCHAR(100), api_key_encrypted TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE ai_feature_configs ("
            "id INTEGER PRIMARY KEY, feature_key VARCHAR(50), enabled BOOLEAN, default_model VARCHAR(100), config TEXT)"
        ))
        enc_key = "b64:" + base64.urlsafe_b64encode(b"uk-xmax-db-key").decode("ascii")
        enc_code = "b64:" + base64.urlsafe_b64encode(b"xmax-access-code-12345").decode("ascii")
        cfg_json = json.dumps({
            "environment": "china",
            "allowed_models": ["x2.1", "x2.1-flash"],
            "camera_preset": "704x1280",
            "face_restoration": False,
            "require_access_code": True,
            "access_code_encrypted": enc_code,
            "min_seconds": 10,
            "max_seconds": 90,
            "default_seconds": 45,
            "credits_per_second": 1,
            "cents_per_minute": 12,
            "daily_cents": 500,
            "monthly_cents": 2000,
            "visitor_daily_cents": 100,
            "min_account_credits": 80,
            "max_active": 2,
            "starts_per_minute": 4,
            "origin": "https://xmax.example.test",
            "default_prompt": "Keep character consistent",
        })
        conn.execute(
            text(
                "INSERT INTO ai_api_providers (provider_key, enabled, base_url, default_model, api_key_encrypted) "
                "VALUES ('xmax', 1, 'https://cloud.xmax.22duck.cn/open/api/v1', 'x2.1-flash', :k)"
            ),
            {"k": enc_key},
        )
        conn.execute(
            text("INSERT INTO ai_feature_configs (feature_key, enabled, default_model, config) VALUES ('tryon_realtime_xmax', 1, 'x2.1-flash', :c)"),
            {"c": cfg_json},
        )

    for env_name in ("XMAX_REALTIME_ENABLED", "XMAX_API_KEY", "XMAX_REALTIME_ORIGIN", "WORKBENCH_PUBLIC_URL", "APP_ENV"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", db_url)
    monkeypatch.setenv("AI_CONFIG_DATABASE_URL", db_url)
    budget.clear_settings_cache()
    ensure_task_tables(db_url)
    try:
        cfg = budget.load_xmax_settings()
        assert cfg.source == "admin_db"
        assert cfg.enabled is True
        assert cfg.available is True
        assert cfg.environment == "china"
        assert cfg.default_model == "x2.1-flash"
        assert cfg.face_restoration is False
        assert cfg.max_seconds == 90
        assert cfg.cents_per_minute == 12
        assert cfg.min_account_credits == 80
        diag = budget.diagnose_xmax_settings()
        assert diag["available"] is True
        assert diag["environment"] == "china"
        assert diag["model"] == "x2.1-flash"
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()
        engine.dispose()


def test_reactor_disabled_by_default_and_end_to_end_session_flow(tmp_path, monkeypatch):
    from app import reactor_client

    for name in (
        "APP_ENV",
        "DECART_REALTIME_ENABLED",
        "XMAX_REALTIME_ENABLED",
        "REACTOR_REALTIME_ENABLED",
        "REACTOR_API_KEY",
        "REACTOR_REALTIME_API_KEY",
        "REACTOR_REALTIME_ACCESS_CODE",
        "WORKBENCH_PUBLIC_URL",
        "REACTOR_REALTIME_ORIGIN",
        "AI_CONFIG_DATABASE_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'reactor.db').as_posix()}")
    budget.clear_settings_cache()
    ensure_task_tables()

    try:
        app = FastAPI()
        app.include_router(routes.router)
        with TestClient(app) as tc:
            off = tc.get("/api/realtime-tryon/providers")
            assert off.status_code == 200
            assert off.json()["providers"]["reactor"]["available"] is False
            assert tc.post(
                "/api/realtime-tryon/reactor/sessions",
                json={"access_code": ACCESS, "seconds": 30, "max_cents": 6},
            ).status_code == 503

        # Enable Reactor in env mode
        monkeypatch.setenv("REACTOR_REALTIME_ENABLED", "true")
        monkeypatch.setenv("REACTOR_API_KEY", "rk-reactor-master-secret")
        monkeypatch.setenv("REACTOR_REALTIME_ACCESS_CODE", ACCESS)
        monkeypatch.setenv("REACTOR_REALTIME_CREDITS_PER_SECOND", "17")
        monkeypatch.setenv("REACTOR_REALTIME_CENTS_PER_MINUTE", "11")
        monkeypatch.setenv("REACTOR_REALTIME_MIN_ACCOUNT_CREDITS", "1000")
        monkeypatch.setenv("REACTOR_REALTIME_VISITOR_DAILY_CENTS", "50")
        budget.clear_settings_cache()

        calls = []
        bal_state = {"credits": 400.0}

        async def fake_get_balance(api_key, *, base_url, timeout=10.0):
            calls.append(("balance", api_key, base_url))
            return {
                "account_id": "acct_reactor_1",
                "balance": bal_state["credits"],
                "balance_usd": round(bal_state["credits"] / 10000.0, 4),
                "currency_code": "USD",
            }

        async def fake_create_jwt(
            api_key,
            *,
            base_url,
            model_name,
            max_session_duration_seconds,
            expire_seconds,
            max_sessions=1,
            timeout=10.0,
        ):
            calls.append(("jwt", model_name, max_session_duration_seconds, expire_seconds, max_sessions))
            return {"jwt": "eyJ-reactor-scoped-jwt"}

        async def fake_close_session(api_key, session_id, *, base_url, reason="user_stopped", timeout=10.0):
            calls.append(("close_session", session_id, reason))

        async def fake_get_usage(api_key, session_id, *, base_url, account_id="", timeout=10.0):
            calls.append(("usage", session_id))
            return {"id": session_id, "state": "CLOSED", "billed_seconds": 12.0}

        monkeypatch.setattr(reactor_client, "get_balance", fake_get_balance)
        monkeypatch.setattr(reactor_client, "create_scoped_jwt", fake_create_jwt)
        monkeypatch.setattr(reactor_client, "close_session", fake_close_session)
        monkeypatch.setattr(reactor_client, "get_session_usage", fake_get_usage)

        with TestClient(app) as tc:
            prov = tc.get("/api/realtime-tryon/providers")
            assert prov.status_code == 200
            r_prov = prov.json()["providers"]["reactor"]
            assert r_prov["available"] is True
            assert r_prov["model"] == "reactor/xmax-x2-1"
            assert r_prov["allowed_models"] == ["reactor/xmax-x2-1", "xmax/x2"]
            assert r_prov["credits_per_second"] == 17
            assert r_prov["cents_per_minute"] == 11

            # Balance below floor -> 429 + hold released
            res1 = tc.post(
                "/api/realtime-tryon/reactor/sessions",
                json={"access_code": ACCESS, "seconds": 30, "max_cents": 6, "model": "x2.1"},
                headers=ORIGIN,
            )
            assert res1.status_code == 201
            sid1 = res1.json()["id"]
            assert res1.json()["model_id"] == "reactor/xmax-x2-1"

            tok1 = tc.post(f"/api/realtime-tryon/reactor/sessions/{sid1}/token", json={}, headers=ORIGIN)
            assert tok1.status_code == 429
            assert tok1.json()["error"]["code"] == "insufficient_credits"

            # Raise balance above floor -> reserve X2.0 (alias xmax/x2), mint JWT, attach, and settle
            bal_state["credits"] = 25000.0
            res2 = tc.post(
                "/api/realtime-tryon/reactor/sessions",
                json={"access_code": ACCESS, "seconds": 30, "max_cents": 6, "model": "x2.0"},
                headers=ORIGIN,
            )
            assert res2.status_code == 201
            sid2 = res2.json()["id"]
            assert res2.json()["model_id"] == "xmax/x2"

            tok2 = tc.post(f"/api/realtime-tryon/reactor/sessions/{sid2}/token", json={}, headers=ORIGIN)
            assert tok2.status_code == 200
            tok_data = tok2.json()
            assert tok_data["jwt"] == "eyJ-reactor-scoped-jwt"
            assert tok_data["model"] == "xmax/x2"
            assert tok_data["api_url"] == "https://api.reactor.inc"
            assert "rk-reactor-master-secret" not in str(tok_data)
            assert ("jwt", "xmax/x2", 30, 60, 1) in calls

            att = tc.post(
                f"/api/realtime-tryon/reactor/sessions/{sid2}/attach",
                json={"provider_session_id": "rsess_abc123"},
                headers=ORIGIN,
            )
            assert att.status_code == 200

            stopped = tc.post(f"/api/realtime-tryon/sessions/{sid2}/stop", json={}, headers=ORIGIN)
            assert stopped.status_code == 200
            assert ("close_session", "rsess_abc123", "stopped") in calls
            row = budget.get_session_row(sid2)
            assert row is not None
            assert row.provider_seconds == 12.0
            # ceil(12.0 * 11 / 60) = 3 cents
            assert row.accounted_cents == 3
            assert float(row.provider_credits) == pytest.approx(204.0, abs=0.1)

            diag = budget.diagnose_reactor_settings()
            assert diag["available"] is True
            assert diag["model"] == "reactor/xmax-x2-1"
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()


def test_reactor_admin_db_config_loading(tmp_path, monkeypatch):
    import base64
    from sqlalchemy import create_engine, text

    db_file = tmp_path / "admin_reactor.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE ai_api_providers ("
            "id INTEGER PRIMARY KEY, provider_key VARCHAR(50), enabled BOOLEAN, base_url VARCHAR(500), default_model VARCHAR(100), api_key_encrypted TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE ai_feature_configs ("
            "id INTEGER PRIMARY KEY, feature_key VARCHAR(50), enabled BOOLEAN, default_model VARCHAR(100), config TEXT)"
        ))
        enc_key = "b64:" + base64.urlsafe_b64encode(b"rk-reactor-db-key").decode("ascii")
        enc_code = "b64:" + base64.urlsafe_b64encode(b"reactor-access-code-1234").decode("ascii")
        cfg_json = json.dumps({
            "allowed_models": ["reactor/xmax-x2-1", "xmax/x2"],
            "require_access_code": True,
            "access_code_encrypted": enc_code,
            "min_seconds": 10,
            "max_seconds": 60,
            "default_seconds": 30,
            "credits_per_second": 17,
            "cents_per_minute": 11,
            "daily_cents": 200,
            "monthly_cents": 1000,
            "visitor_daily_cents": 50,
            "min_account_credits": 1000,
            "max_active": 1,
            "starts_per_minute": 3,
            "origin": "https://reactor.example.test",
            "default_prompt": "Keep garment accurate",
        })
        conn.execute(
            text(
                "INSERT INTO ai_api_providers (provider_key, enabled, base_url, default_model, api_key_encrypted) "
                "VALUES ('reactor', 1, 'https://api.reactor.inc', 'reactor/xmax-x2-1', :k)"
            ),
            {"k": enc_key},
        )
        conn.execute(
            text("INSERT INTO ai_feature_configs (feature_key, enabled, default_model, config) VALUES ('tryon_realtime_reactor', 1, 'reactor/xmax-x2-1', :c)"),
            {"c": cfg_json},
        )

    for env_name in ("REACTOR_REALTIME_ENABLED", "REACTOR_API_KEY", "REACTOR_REALTIME_API_KEY", "REACTOR_REALTIME_ORIGIN", "WORKBENCH_PUBLIC_URL", "APP_ENV"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", db_url)
    monkeypatch.setenv("AI_CONFIG_DATABASE_URL", db_url)
    budget.clear_settings_cache()
    ensure_task_tables(db_url)
    try:
        cfg = budget.load_reactor_settings()
        assert cfg.source == "admin_db"
        assert cfg.enabled is True
        assert cfg.available is True
        assert cfg.default_model == "reactor/xmax-x2-1"
        assert cfg.allowed_models == ("reactor/xmax-x2-1", "xmax/x2")
        assert cfg.credits_per_second == 17
        assert cfg.cents_per_minute == 11
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()
        engine.dispose()


def test_workbench_realtime_ui_and_i18n_parity():
    root = Path(__file__).resolve().parents[1]
    bundles = {
        loc: json.loads((root / "static/i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("zh-CN", "en", "ja")
    }
    zh_rt = bundles["zh-CN"]["realtime"]
    for loc in ("en", "ja"):
        loc_rt = bundles[loc]["realtime"]
        assert set(loc_rt.keys()) == set(zh_rt.keys())
        assert set(loc_rt["presets"].keys()) == set(zh_rt["presets"].keys())
        assert set(loc_rt["errors"].keys()) == set(zh_rt["errors"].keys())

    html = (root / "static/index.html").read_text(encoding="utf-8")
    for marker in (
        'id="realtime-provider-tabs"',
        'id="realtime-provider-xmax"',
        'id="realtime-provider-reactor"',
        'id="realtime-provider-decart"',
        'id="realtime-refresh-status"',
        'id="realtime-xmax-preset"',
        'id="realtime-xmax-source"',
        'id="realtime-xmax-adaptive"',
        'id="realtime-local-image"',
        'id="realtime-stage"',
        'id="realtime-maximize-toggle"',
        'id="realtime-float-toggle"',
        'id="realtime-popout-toggle"',
        'id="realtime-fullscreen-toggle"',
        'id="realtime-fit-toggle"',
        'id="realtime-layout-pip"',
        '<option value="auto" selected>',
        'viewport-fit=cover',
        '/static/css/video.css?v=20261124-v8',
        '/static/js/i18n.js?v=20261124-v8',
        '/static/js/realtime.js?v=20261124-v8',
        'id="realtime-inline-error"',
    ):
        assert marker in html
    assert 'id="realtime-provider-tabs" class="realtime-provider-tabs" role="tablist"' in html
    error_log_html = (root / "static/error-log.html").read_text(encoding="utf-8")
    assert 'viewport-fit=cover' in error_log_html
    assert '/static/js/i18n.js?v=20261124-v8' in error_log_html

    video_css = (root / "static/css/video.css").read_text(encoding="utf-8")
    assert ".realtime-xmax-host > div" in video_css
    assert ".realtime-inline-error" in video_css
    assert "--realtime-aspect-ratio" in video_css
    assert 'data-orientation="landscape"' in video_css

    realtime_js = (root / "static/js/realtime.js").read_text(encoding="utf-8")
    for marker in (
        './realtime-helpers.js?v=20261124-v8',
        'createLocalImageStream',
        'createLocalVideoStream',
        'createLocalCameraStream',
        'createExternalVideoStream',
        'XmaxLoggerOption.business',
        'isAdaptiveQualityEnabled',
        'documentPictureInPicture',
        'setStageDisplayMode',
        'pickBestXmaxPreset',
        'computeStageAspectRatio',
        'updateCameraFormat',
        'computeCenterCropRect',
    ):
        assert marker in realtime_js


def test_stop_endpoint_records_sanitized_reason_and_enforces_xmax_min_ttl(tmp_path, monkeypatch):
    for name in (
        "APP_ENV",
        "WORKBENCH_PUBLIC_URL",
        "XMAX_REALTIME_ORIGIN",
        "XMAX_REALTIME_ENVIRONMENT",
        "XMAX_REALTIME_MODEL",
        "XMAX_REALTIME_ALLOWED_MODELS",
        "AI_CONFIG_DATABASE_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'xmax_stop_meta.db').as_posix()}")
    monkeypatch.setenv("XMAX_REALTIME_ENABLED", "true")
    monkeypatch.setenv("XMAX_API_KEY", "uk-xmax-master-secret")
    monkeypatch.setenv("XMAX_REALTIME_ACCESS_CODE", ACCESS)
    monkeypatch.setenv("XMAX_REALTIME_MIN_ACCOUNT_CREDITS", "10")
    budget.clear_settings_cache()
    ensure_task_tables()

    issued_ttls = []

    async def fake_balance(api_key, *, base_url, timeout=10.0):
        return 600.0

    async def fake_create_tk(api_key, *, base_url, expire_seconds, points_limit, session_limit=1, timeout=10.0):
        issued_ttls.append((expire_seconds, points_limit))
        return {
            "uid": "utk-ttl-check",
            "temporaryApiKey": "tk-temp-issued-ttl",
            "pointsLimit": points_limit,
            "expireTimestamp": "2026-11-24T12:00:00+00:00",
        }

    async def fake_deactivate(api_key, temp_key, *, base_url, timeout=10.0):
        return {"temporaryApiKey": temp_key, "status": "inactive", "consumedCredit": 0}

    async def fake_tk_status(api_key, temp_key, *, base_url, timeout=10.0):
        return {"temporaryApiKey": temp_key, "status": "inactive", "consumedCredit": 0}

    monkeypatch.setattr(routes.xmax_client, "get_balance", fake_balance)
    monkeypatch.setattr(routes.xmax_client, "create_temporary_api_key", fake_create_tk)
    monkeypatch.setattr(routes.xmax_client, "deactivate_temporary_api_key", fake_deactivate)
    monkeypatch.setattr(routes.xmax_client, "get_temporary_api_key_status", fake_tk_status)

    try:
        app = FastAPI()
        app.include_router(routes.router)
        with TestClient(app) as tc:
            prov_global = tc.get("/api/realtime-tryon/providers").json()["providers"]["xmax"]
            assert prov_global["environment"] == "global"
            assert prov_global["model"] == "x2.1"
            assert prov_global["allowed_models"] == ["x2.1"]

            # Global node rejects x2.1-flash up-front before issuing temporary key
            bad_model = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 10, "max_cents": 2, "model": "x2.1-flash"},
                headers=ORIGIN,
            )
            assert bad_model.status_code == 400
            assert bad_model.json()["error"]["code"] == "invalid_model"

            # 10s Xmax session should get at least 60s temp-key TTL while keeping points_limit == 10
            res1 = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 10, "max_cents": 2, "model": "x2.1"},
                headers=ORIGIN,
            )
            assert res1.status_code == 201
            sid1 = res1.json()["id"]
            assert tc.post(f"/api/realtime-tryon/xmax/sessions/{sid1}/token", json={}, headers=ORIGIN).status_code == 200
            assert issued_ttls == [(60, 10)]

            # Stop with client diagnostic reason preserves normalized reason <= 32 chars
            stop1 = tc.post(
                f"/api/realtime-tryon/sessions/{sid1}/stop",
                json={
                    "reason": "camera_not_readable",
                    "stage": "camera",
                    "detail": "Agora operation failed (NOT_READABLE) for tk-temp-issued-ttl",
                },
                headers=ORIGIN,
            )
            assert stop1.status_code == 200
            row1 = budget.get_session_row(sid1)
            assert row1 is not None and row1.reason == "camera_not_readable"

            # Reserved-only cancel with invalid/oversized reason sanitizes to "stopped"
            res2 = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 10, "max_cents": 2, "model": "x2.1"},
                headers=ORIGIN,
            )
            assert res2.status_code == 201
            sid2 = res2.json()["id"]
            stop2 = tc.post(
                f"/api/realtime-tryon/sessions/{sid2}/stop",
                json={"reason": "Invalid Reason! " + "x" * 40},
                headers=ORIGIN,
            )
            assert stop2.status_code == 200
            row2 = budget.get_session_row(sid2)
            assert row2 is not None and row2.reason == "stopped"

            # China node continues to allow both x2.1 and x2.1-flash
            monkeypatch.setenv("XMAX_REALTIME_ENVIRONMENT", "china")
            budget.clear_settings_cache()
            prov_china = tc.get("/api/realtime-tryon/providers").json()["providers"]["xmax"]
            assert prov_china["allowed_models"] == ["x2.1", "x2.1-flash"]
            flash_ok = tc.post(
                "/api/realtime-tryon/xmax/sessions",
                json={"access_code": ACCESS, "seconds": 10, "max_cents": 2, "model": "x2.1-flash"},
                headers=ORIGIN,
            )
            assert flash_ok.status_code == 201
            assert tc.post(f"/api/realtime-tryon/sessions/{flash_ok.json()['id']}/stop", json={}, headers=ORIGIN).status_code == 200
    finally:
        budget.clear_settings_cache()
        reset_engine_cache()

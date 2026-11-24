from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    AIAPIProvider,
    AIAPITestLog,
    AIFeatureConfig,
    Base,
    WorkbenchRealtimeSession,
    _seed_ai_configs,
)
from app.routers import realtime_tryon as rt


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_seeded_defaults_and_config_update_encryption():
    engine = _make_db()
    admin = SimpleNamespace(username="tester")
    with (
        Session(engine) as db,
        patch("app.routers.realtime_tryon.encrypt_secret", side_effect=lambda v: f"enc:{v}"),
        patch("app.routers.realtime_tryon.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")),
    ):
        _seed_ai_configs(db)
        provider = db.query(AIAPIProvider).filter_by(provider_key="decart").one()
        feature = db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime").one()
        assert provider.enabled is False
        assert feature.enabled is False

        initial = rt.get_config(admin=admin, db=db)
        assert initial["enabled"] is False
        assert initial["ready_to_serve"] is False
        assert "feature_disabled" in initial["blocking_reasons"]

        updated = rt.update_config(
            rt.RealtimeConfigUpdate(
                enabled=True,
                api_key="decart-secret-key",
                access_code="admin-chosen-access-code-1234",
                origin="https://workbench.example.test/",
                max_seconds=30,
                default_seconds=12,
                daily_cents=500,
                monthly_cents=2000,
                visitor_daily_cents=120,
            ),
            admin=admin,
            db=db,
        )
        assert updated["enabled"] is True
        assert updated["has_api_key"] is True
        assert updated["has_access_code"] is True
        assert updated["origin"] == "https://workbench.example.test"
        assert updated["ready_to_serve"] is True
        assert "decart-secret-key" not in str(updated)
        assert "admin-chosen-access-code-1234" not in str(updated)

        # Preserve existing key and code when omitted
        kept = rt.update_config(rt.RealtimeConfigUpdate(api_key="   ", max_seconds=25), admin=admin, db=db)
        assert kept["has_api_key"] is True
        assert kept["has_access_code"] is True
        assert kept["max_seconds"] == 25

        # Generate strong code
        gen = rt.generate_access_code(admin=admin, db=db)
        assert len(gen["access_code"]) >= 16
        assert gen["config"]["has_access_code"] is True
    engine.dispose()


def test_zero_cost_connection_check_and_ai_config_provider_test():
    engine = _make_db()
    admin = SimpleNamespace(username="tester")
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {
                    "apiKey": "ephemeral-client-tok",
                    "constraints": {"realtime": {"maxSessionDuration": 10}},
                },
            )

    with (
        Session(engine) as db,
        patch("app.routers.realtime_tryon.encrypt_secret", side_effect=lambda v: f"enc:{v}"),
        patch("app.routers.realtime_tryon.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")),
        patch("app.routers.realtime_tryon.httpx.AsyncClient", FakeClient),
    ):
        _seed_ai_configs(db)
        rt.update_config(rt.RealtimeConfigUpdate(api_key="real-decart-key"), admin=admin, db=db)
        result = asyncio.run(rt.test_config(admin=admin, db=db))
        assert result["success"] is True
        assert result["status_code"] == 200
        assert "ephemeral-client-tok" not in str(result)
        assert "real-decart-key" not in str(result)
        assert calls[0][0] == "https://api.decart.ai/v1/client/tokens"
        assert calls[0][1]["json"] == {
            "expiresIn": 10,
            "allowedModels": ["lucy-vton-3.6"],
            "constraints": {"realtime": {"maxSessionDuration": 10}},
        }

        from app.routers.ai_config import test_provider

        provider = db.query(AIAPIProvider).filter_by(provider_key="decart").one()
        with patch("app.routers.ai_config.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")):
            generic = asyncio.run(test_provider(provider.id, admin=admin, db=db))
        assert generic["success"] is True
        assert db.query(AIAPITestLog).filter_by(provider_key="decart").count() >= 1
    engine.dispose()


def test_overview_sessions_force_stop_reconcile_and_emergency_stop():
    engine = _make_db()
    admin = SimpleNamespace(username="tester")
    now = time.time()
    day_str, _, _ = rt._calendar(now)

    with Session(engine) as db:
        _seed_ai_configs(db)
        provider = db.query(AIAPIProvider).filter_by(provider_key="decart").one()
        feature = db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime").one()
        provider.enabled = True
        feature.enabled = True

        db.add_all([
            # Confirmed ended session
            WorkbenchRealtimeSession(
                id="s_confirmed".ljust(32, "0"),
                visitor_hash="visitor_alpha_123456",
                budget_day=day_str,
                created_at=now - 120,
                claim_before=now - 105,
                hold_until=0.0,
                state="ended",
                stop_requested=False,
                limit_seconds=20,
                cents_per_second=2,
                accounted_cents=12,
                provider_session_id="decart_sess_1",
                provider_seconds=5.4,
                reason="timeout",
                ended_at=now - 100,
            ),
            # Unconfirmed expired hold session (can reconcile)
            WorkbenchRealtimeSession(
                id="s_held".ljust(32, "1"),
                visitor_hash="visitor_alpha_123456",
                budget_day=day_str,
                created_at=now - 90,
                claim_before=now - 75,
                hold_until=now - 10,
                state="claimed",
                stop_requested=False,
                limit_seconds=20,
                cents_per_second=2,
                accounted_cents=40,
                provider_session_id=None,
                provider_seconds=None,
                reason=None,
                ended_at=None,
            ),
            # Currently claimed active session
            WorkbenchRealtimeSession(
                id="s_active".ljust(32, "2"),
                visitor_hash="visitor_beta_999999",
                budget_day=day_str,
                created_at=now - 5,
                claim_before=now + 10,
                hold_until=now + 25,
                state="claimed",
                stop_requested=False,
                limit_seconds=20,
                cents_per_second=2,
                accounted_cents=40,
                provider_session_id="decart_live_2",
                provider_seconds=None,
                reason=None,
                ended_at=None,
            ),
            # Currently reserved ticket
            WorkbenchRealtimeSession(
                id="s_reserved".ljust(32, "3"),
                visitor_hash="visitor_gamma_88888",
                budget_day=day_str,
                created_at=now - 2,
                claim_before=now + 13,
                hold_until=now + 13,
                state="reserved",
                stop_requested=False,
                limit_seconds=15,
                cents_per_second=2,
                accounted_cents=30,
                provider_session_id=None,
                provider_seconds=None,
                reason=None,
                ended_at=None,
            ),
        ])
        db.commit()

        ov = rt.get_overview(admin=admin, db=db)
        assert ov["active_sessions"] == 2
        assert ov["daily"]["accounted_cents"] == 122
        assert ov["daily"]["confirmed_cents"] == 12
        assert ov["daily"]["held_unconfirmed_cents"] == 110
        assert len(ov["visitors_today"]) == 3

        active_list = rt.list_sessions(page=1, size=20, state="active", admin=admin, db=db)
        assert active_list["total"] == 2

        ended_list = rt.list_sessions(page=1, size=20, state="ended", reason="usage_unconfirmed", admin=admin, db=db)
        assert ended_list["total"] == 1
        held_id = ended_list["items"][0]["id"]

        # Reconcile held session from 40c down to 4.1s -> ceil(4.1)*2 = 10c
        reconciled = rt.reconcile_session(
            held_id,
            rt.ReconcileRequest(confirmed_seconds=4.1, provider_session_id="decart_manual_1"),
            admin=admin,
            db=db,
        )
        assert reconciled["session"]["accounted_cents"] == 10
        assert reconciled["session"]["reason"] == "admin_reconciled"

        # Active session cannot be reconciled before stopping
        with pytest.raises(HTTPException) as exc:
            rt.reconcile_session(
                "s_active".ljust(32, "2"),
                rt.ReconcileRequest(confirmed_seconds=5),
                admin=admin,
                db=db,
            )
        assert exc.value.status_code == 400

        # Force stop active claimed session
        stopped = asyncio.run(rt.force_stop_session("s_active".ljust(32, "2"), admin=admin, db=db))
        assert stopped["session"]["stop_requested"] is True

        # Emergency stop disables feature and cancels remaining reserved tickets
        emg = asyncio.run(rt.emergency_stop(admin=admin, db=db))
        assert emg["disabled"] is True
        assert emg["canceled_reserved"] == 1
        assert db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime").one().enabled is False
        assert db.query(AIAPIProvider).filter_by(provider_key="decart").one().enabled is False
        assert db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime_xmax").one().enabled is False
        assert db.query(AIAPIProvider).filter_by(provider_key="xmax").one().enabled is False
    engine.dispose()


def test_xmax_config_balance_test_sync_usage_and_scoped_emergency_stop():
    engine = _make_db()
    admin = SimpleNamespace(username="tester")
    now = time.time()
    day_str, _, _ = rt._calendar(now)
    http_calls = []

    class FakeXmaxClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            http_calls.append(("GET", url))
            if url.endswith("/balance"):
                return SimpleNamespace(status_code=200, text="ok", json=lambda: {"success": True, "code": 200, "data": {"currentBalance": 1280.5}})
            if url.endswith("/points/consume/range-stats"):
                return SimpleNamespace(status_code=200, text="ok", json=lambda: {"success": True, "code": 200, "data": {"sum": 42}})
            if "/temporary-api-key/" in url and url.endswith("/status"):
                return SimpleNamespace(status_code=200, text="ok", json=lambda: {"success": True, "code": 200, "data": {"status": "inactive", "consumedCredit": 18}})
            return SimpleNamespace(status_code=404, text="not found", json=lambda: {"success": False, "code": 404})

        async def delete(self, url, **kwargs):
            http_calls.append(("DELETE", url))
            return SimpleNamespace(status_code=200, text="ok", json=lambda: {"success": True, "code": 200, "data": {}})

        async def put(self, url, **kwargs):
            http_calls.append(("PUT", url))
            return SimpleNamespace(status_code=200, text="ok", json=lambda: {"success": True, "code": 200, "data": {}})

    with (
        Session(engine) as db,
        patch("app.routers.realtime_tryon.encrypt_secret", side_effect=lambda v: f"enc:{v}"),
        patch("app.routers.realtime_tryon.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")),
        patch("app.routers.realtime_tryon.httpx.AsyncClient", FakeXmaxClient),
    ):
        _seed_ai_configs(db)
        x_prov = db.query(AIAPIProvider).filter_by(provider_key="xmax").one()
        x_feat = db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime_xmax").one()
        assert x_prov.enabled is False
        assert x_feat.enabled is False

        gen = rt.generate_xmax_access_code(admin=admin, db=db)
        assert len(gen["access_code"]) >= 16

        updated = rt.update_xmax_config(
            rt.XmaxRealtimeConfigUpdate(
                enabled=True,
                api_key="uk-xmax-secret",
                environment="global",
                default_model="x2.1",
                allowed_models=["x2.1", "x2.1-flash"],
                max_seconds=60,
                default_seconds=30,
                cents_per_minute=10,
                min_account_credits=100,
                origin="https://workbench.example.test",
            ),
            admin=admin,
            db=db,
        )
        assert updated["enabled"] is True
        assert updated["ready_to_serve"] is True
        assert "uk-xmax-secret" not in str(updated)

        tested = asyncio.run(rt.test_xmax_config(admin=admin, db=db))
        assert tested["success"] is True
        assert tested["current_balance"] == 1280.5

        from app.routers.ai_config import test_provider

        with patch("app.routers.ai_config.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")):
            generic = asyncio.run(test_provider(x_prov.id, admin=admin, db=db))
        assert generic["success"] is True

        bal = asyncio.run(rt.get_xmax_balance(admin=admin, db=db))
        assert bal["current_balance"] == 1280.5
        assert bal["consumed_24h"] == 42.0

        # Add held Xmax session + active Decart session -> test provider filtering & sync-usage & scoped kill switch
        db.add_all([
            WorkbenchRealtimeSession(
                id="x_held".ljust(32, "a"),
                provider_key="xmax",
                model_id="x2.1",
                visitor_hash="visitor_xmax_111111",
                budget_day=day_str,
                created_at=now - 60,
                claim_before=now - 45,
                hold_until=now - 5,
                state="claimed",
                stop_requested=False,
                limit_seconds=30,
                cents_per_second=0,
                cents_per_minute=10,
                credits_per_second=1.0,
                max_credits=30,
                accounted_cents=5,
                provider_session_id="ums-x-1",
                provider_temp_key_uid="utk-x-1",
                provider_temp_key_encrypted="enc:tk-x-1",
            ),
            WorkbenchRealtimeSession(
                id="d_res".ljust(32, "b"),
                provider_key="decart",
                model_id="lucy-vton-3.6",
                visitor_hash="visitor_decart_222",
                budget_day=day_str,
                created_at=now - 5,
                claim_before=now + 10,
                hold_until=now + 10,
                state="reserved",
                stop_requested=False,
                limit_seconds=15,
                cents_per_second=2,
                accounted_cents=30,
            ),
        ])
        db.commit()

        ov_x = rt.get_overview(provider="xmax", admin=admin, db=db)
        assert ov_x["daily"]["accounted_cents"] == 5
        assert ov_x["daily"]["session_count"] == 1

        synced = asyncio.run(rt.sync_session_usage("x_held".ljust(32, "a"), admin=admin, db=db))
        assert synced["synced"] is True
        assert synced["session"]["provider_credits"] == 18.0
        # ceil((18/1)*10/60) = 3 cents
        assert synced["session"]["accounted_cents"] == 3
        assert db.get(WorkbenchRealtimeSession, "x_held".ljust(32, "a")).provider_temp_key_encrypted is None

        # Credit reconcile
        rec = rt.reconcile_session(
            "x_held".ljust(32, "a"),
            rt.ReconcileRequest(confirmed_credits=24, provider_session_id="ums-x-1"),
            admin=admin,
            db=db,
        )
        assert rec["session"]["accounted_cents"] == 4
        assert rec["session"]["provider_seconds"] == 24.0

        # Scoped emergency stop for xmax leaves Decart reserved ticket untouched
        db.query(AIAPIProvider).filter_by(provider_key="decart").update({"enabled": True})
        db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime").update({"enabled": True})
        db.commit()
        emg_x = asyncio.run(rt.emergency_stop(provider="xmax", admin=admin, db=db))
        assert emg_x["provider"] == "xmax"
        assert db.query(AIAPIProvider).filter_by(provider_key="xmax").one().enabled is False
        assert db.query(AIAPIProvider).filter_by(provider_key="decart").one().enabled is True
    engine.dispose()


def test_reactor_config_balance_sync_reconcile_and_fetch_official():
    engine = _make_db()
    admin = SimpleNamespace(username="tester")
    now = time.time()
    day_str, _, _ = rt._calendar(now)
    requests_seen = []

    class FakeReactorClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, **kwargs):
            requests_seen.append((method, url, kwargs))
            if url.endswith("/sessions/rsess-held-1") and method == "DELETE":
                return SimpleNamespace(status_code=200, text="ok", json=lambda: {"ok": True})
            return SimpleNamespace(status_code=404, text="not found", json=lambda: {})

        async def get(self, url, **kwargs):
            requests_seen.append(("GET", url, kwargs))
            if url.endswith("/pricing"):
                return SimpleNamespace(
                    status_code=200,
                    text="ok",
                    json=lambda: {
                        "credits_per_dollar": 10000,
                        "models": [
                            {"model": "reactor/xmax-x2-1", "amount_per_sec": 17, "amount_per_sec_usd": "0.0017"},
                            {"model": "xmax/x2", "amount_per_sec": 17, "amount_per_sec_usd": "0.0017"},
                        ],
                    },
                )
            if url.endswith("/me"):
                return SimpleNamespace(status_code=200, text="ok", json=lambda: {"account_id": "acct_r_99"})
            if url.endswith("/accounts/acct_r_99/credits"):
                return SimpleNamespace(
                    status_code=200,
                    text="ok",
                    json=lambda: {"balance": 54321, "balance_usd": 5.4321, "currency_code": "USD"},
                )
            if url.endswith("/accounts/acct_r_99/quotas"):
                return SimpleNamespace(status_code=200, text="ok", json=lambda: {"max_concurrent_sessions": 2})
            if url.endswith("/sessions/rsess-held-1"):
                return SimpleNamespace(
                    status_code=200,
                    text="ok",
                    json=lambda: {"id": "rsess-held-1", "state": "CLOSED", "billed_seconds": 12.0},
                )
            return SimpleNamespace(status_code=404, text="not found", json=lambda: {})

    with (
        Session(engine) as db,
        patch("app.routers.realtime_tryon.encrypt_secret", side_effect=lambda v: f"enc:{v}"),
        patch("app.routers.realtime_tryon.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")),
        patch("app.routers.realtime_tryon.httpx.AsyncClient", FakeReactorClient),
    ):
        _seed_ai_configs(db)
        r_prov = db.query(AIAPIProvider).filter_by(provider_key="reactor").one()
        r_feat = db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime_reactor").one()
        assert r_prov.enabled is False
        assert r_feat.enabled is False
        assert r_prov.default_model == "reactor/xmax-x2-1"

        # Fetch official BEFORE saving any key or mutating DB
        official_r = asyncio.run(rt.fetch_official_realtime_data("reactor", body=None, admin=admin, db=db))
        assert official_r["ok"] is True
        assert official_r["source"] == "live_api"
        assert official_r["suggested_fields"]["credits_per_second"] == 17
        assert official_r["suggested_fields"]["cents_per_minute"] == 11
        assert official_r["suggested_fields"]["default_model"] == "reactor/xmax-x2-1"
        assert db.query(AIAPIProvider).filter_by(provider_key="reactor").one().api_key_encrypted is None

        # Fetch official for xmax, decart, and reject unsupported provider
        official_x = asyncio.run(rt.fetch_official_realtime_data("xmax", body=None, admin=admin, db=db))
        assert official_x["suggested_fields"]["default_model"] == "x2.1"
        official_d = asyncio.run(rt.fetch_official_realtime_data("decart", body=None, admin=admin, db=db))
        assert official_d["suggested_fields"]["cents_per_second"] == 2
        with pytest.raises(HTTPException) as exc:
            asyncio.run(rt.fetch_official_realtime_data("unknown", body=None, admin=admin, db=db))
        assert exc.value.status_code == 400

        updated = rt.update_reactor_config(
            rt.ReactorRealtimeConfigUpdate(
                enabled=True,
                api_key="rk_secret_key",
                access_code="reactor-access-code-1234",
                default_model="reactor/xmax-x2-1",
                allowed_models=["reactor/xmax-x2-1", "xmax/x2"],
                credits_per_second=17,
                cents_per_minute=11,
            ),
            admin=admin,
            db=db,
        )
        assert updated["enabled"] is True
        assert updated["ready_to_serve"] is True
        assert updated["default_model"] == "reactor/xmax-x2-1"
        assert "rk_secret_key" not in str(updated)

        tested = asyncio.run(rt.test_reactor_config(admin=admin, db=db))
        assert tested["success"] is True
        assert tested["current_balance"] == 54321.0
        assert tested["account_id"] == "acct_r_99"

        from app.routers.ai_config import test_provider

        with patch("app.routers.ai_config.decrypt_secret", side_effect=lambda v: v.removeprefix("enc:")):
            generic = asyncio.run(test_provider(r_prov.id, admin=admin, db=db))
        assert generic["success"] is True

        bal = asyncio.run(rt.get_reactor_balance(admin=admin, db=db))
        assert bal["balance"] == 54321.0
        assert bal["balance_usd"] == 5.4321
        assert bal["quotas"]["max_concurrent_sessions"] == 2

        db.add(
            WorkbenchRealtimeSession(
                id="r_held".ljust(32, "c"),
                provider_key="reactor",
                model_id="reactor/xmax-x2-1",
                visitor_hash="visitor_reactor_111",
                budget_day=day_str,
                created_at=now - 60,
                claim_before=now - 45,
                hold_until=now - 5,
                state="claimed",
                stop_requested=False,
                limit_seconds=30,
                cents_per_second=0,
                cents_per_minute=11,
                credits_per_second=17.0,
                max_credits=510,
                accounted_cents=6,
                provider_session_id="rsess-held-1",
            )
        )
        db.commit()

        ov_r = rt.get_overview(provider="reactor", admin=admin, db=db)
        assert ov_r["daily"]["accounted_cents"] == 6
        assert "reactor" in ov_r["providers"]

        synced = asyncio.run(rt.sync_session_usage("r_held".ljust(32, "c"), admin=admin, db=db))
        assert synced["synced"] is True
        assert synced["session"]["provider_seconds"] == 12.0
        assert synced["session"]["provider_credits"] == 204.0
        # ceil(12.0 * 11 / 60) = 3 cents
        assert synced["session"]["accounted_cents"] == 3

        rec = rt.reconcile_session(
            "r_held".ljust(32, "c"),
            rt.ReconcileRequest(confirmed_credits=340, provider_session_id="rsess-held-1"),
            admin=admin,
            db=db,
        )
        assert rec["session"]["provider_seconds"] == 20.0
        # ceil(20 * 11 / 60) = 4 cents
        assert rec["session"]["accounted_cents"] == 4

        emg = asyncio.run(rt.emergency_stop(provider="reactor", admin=admin, db=db))
        assert emg["provider"] == "reactor"
        assert db.query(AIAPIProvider).filter_by(provider_key="reactor").one().enabled is False

    # Also verify graceful catalog_fallback when outbound pricing request raises
    class FailingClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            raise RuntimeError("network offline")

    with (
        Session(engine) as db,
        patch("app.routers.realtime_tryon.httpx.AsyncClient", FailingClient),
    ):
        _seed_ai_configs(db)
        fallback = asyncio.run(rt.fetch_official_realtime_data("reactor", body=None, admin=admin, db=db))
        assert fallback["ok"] is True
        assert fallback["source"] == "catalog_fallback"
        assert fallback["warning"]
        assert fallback["suggested_fields"]["credits_per_second"] == 17
        assert fallback["suggested_fields"]["cents_per_minute"] == 11
    engine.dispose()

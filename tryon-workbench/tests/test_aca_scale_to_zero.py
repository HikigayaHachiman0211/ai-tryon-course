"""Acceptance tests for Azure Container Apps scale-to-zero workbench architecture."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import PIL.Image
import pytest
from starlette.requests import Request

CLOUD_ROOT = Path(__file__).resolve().parents[1]
if str(CLOUD_ROOT) not in sys.path:
    sys.path.insert(0, str(CLOUD_ROOT))

from app import object_storage, queue_worker, task_db, task_queue


def _run_coro(coro):
    """Drive an async coroutine to completion without spawning a socket event loop."""
    try:
        while True:
            next_val = coro.send(None)
            if next_val is not None:
                raise AssertionError(f"Unexpected suspension in synchronous test runner: {next_val!r}")
    except StopIteration as stop:
        return stop.value
    finally:
        coro.close()


def _make_request(
    *,
    method: str = "GET",
    path: str = "/",
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    query_string: str = "",
) -> Request:
    raw_headers: list[tuple[bytes, bytes]] = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_str.encode("latin-1")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("ascii"),
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "https",
    }
    return Request(scope)


def _png_bytes(color: str = "navy") -> bytes:
    buf = io.BytesIO()
    img = PIL.Image.new("RGB", (64, 64), color)
    for x in range(0, 64, 4):
        img.putpixel((x, x), (255, (x * 7) % 256, 128))
    img.save(buf, "PNG")
    return buf.getvalue()


def _configure_env(monkeypatch, tmp_path: Path):
    db_file = tmp_path / "shared_state.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    uploads = tmp_path / "uploads"
    assets = tmp_path / "assets"
    history = tmp_path / "history"
    obj_root = tmp_path / "object_store"
    queue_dir = tmp_path / "queue_store"
    for d in (uploads, assets, history, obj_root, queue_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("TASK_DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("TASK_EXECUTION_MODE", "queue")
    monkeypatch.setenv("TASK_QUEUE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_TASK_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(obj_root))
    monkeypatch.setattr(object_storage, "_cached_storage", None)
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setenv("ASSET_DIR", str(assets))
    monkeypatch.setenv("HISTORY_DIR", str(history))
    monkeypatch.setenv("ENABLE_ADMIN_REPORTING", "false")
    monkeypatch.setenv("INGEST_SECRET_KEY", "test-ingest-secret")
    monkeypatch.setenv("TASK_TOKEN_SECRET", "test-task-signing-secret")
    task_db.reset_engine_cache()
    task_db.ensure_task_tables(db_url)

    class _NoopTask:
        def __await__(self):
            return iter(())

    def _sync_create_task(coro):
        coro.close()
        return _NoopTask()

    async def _sync_wait_for(coro, timeout=None):
        del timeout
        return await coro

    monkeypatch.setattr(
        queue_worker,
        "asyncio",
        SimpleNamespace(
            Event=lambda: SimpleNamespace(set=lambda: None, is_set=lambda: True),
            create_task=_sync_create_task,
            wait_for=_sync_wait_for,
            TimeoutError=TimeoutError,
        ),
    )
    monkeypatch.setattr(
        queue_worker,
        "resolve_tryon_runtime_config",
        lambda: {"enabled": True, "api_key": "fake", "provider_key": "totokens", "timeout_seconds": 30},
    )
    return db_url, uploads, assets, obj_root, queue_dir


def test_aca_queue_idempotency_worker_completion_and_cross_replica_auth(monkeypatch, tmp_path):
    db_url, uploads, assets, obj_root, queue_dir = _configure_env(monkeypatch, tmp_path)

    (uploads / "model.png").write_bytes(_png_bytes("red"))
    (uploads / "garment.png").write_bytes(_png_bytes("blue"))

    import main

    monkeypatch.setattr(main, "UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(main, "ASSET_DIR", str(assets))
    monkeypatch.setattr(main, "_TASK_QUEUE", task_queue.LocalTaskQueue(queue_dir))
    monkeypatch.setattr(main, "_require_tryon_runtime_config", lambda: {"enabled": True, "api_key": "fake"})
    monkeypatch.setattr(main, "resolve_tryon_runtime_config", lambda: {"enabled": True, "api_key": "fake"})

    # 1. Submit task with explicit idempotency key on Replica 1
    req1 = _make_request(method="POST", path="/submit-task")
    resp1 = _run_coro(
        main.submit_task(
            request=req1,
            target_image=["model.png"],
            reference_image="garment.png",
            custom_prompt="",
            prompt_mode="append",
            freedom=5,
            garment_type="top",
            model="flash",
            target_image_cloud_url=None,
            reference_image_cloud_url=None,
            locale="zh-CN",
            idempotency_key="client-idem-001",
        )
    )
    assert resp1.status_code == 200
    body1 = json.loads(resp1.body.decode("utf-8"))
    assert body1["status"] == "queued"
    assert body1["idempotent_reused"] is False
    task_id = body1["task_id"]
    task_token = body1["task_token"]

    # 2. Duplicate submit with same token + idempotency key reuses task without enqueueing a second message
    req2 = _make_request(
        method="POST",
        path="/submit-task",
        headers={"x-task-token": task_token},
    )
    resp2 = _run_coro(
        main.submit_task(
            request=req2,
            target_image=["model.png"],
            reference_image="garment.png",
            custom_prompt="",
            prompt_mode="append",
            freedom=5,
            garment_type="top",
            model="flash",
            target_image_cloud_url=None,
            reference_image_cloud_url=None,
            locale="zh-CN",
            idempotency_key="client-idem-001",
        )
    )
    body2 = json.loads(resp2.body.decode("utf-8"))
    assert body2["task_id"] == task_id
    assert body2["idempotent_reused"] is True
    assert len(list(queue_dir.glob("*.json"))) == 1

    # 3. Simulate scale-to-zero: wipe local disk uploads & process memory so worker/Replica 2 must use Blob + DB
    (uploads / "model.png").unlink()
    (uploads / "garment.png").unlink()
    main.TASKS.clear()
    main._PENDING_DEDUP.clear()

    generated_calls = []

    async def fake_generate(**kwargs):
        generated_calls.append(kwargs["prompt"])
        return _png_bytes("green")

    q = task_queue.LocalTaskQueue(queue_dir)
    processed = _run_coro(
        queue_worker.run_worker_batch(
            max_messages=5,
            lease_seconds=60,
            renew_interval=999,
            task_queue=q,
            db_url=db_url,
            generate_fn=fake_generate,
        )
    )
    assert processed == 1
    rec_after_done = task_db.get_task_record(task_id, db_url=db_url)
    assert rec_after_done is not None
    assert rec_after_done.get("error_detail") is None, f"worker failed: {rec_after_done}"
    assert len(generated_calls) == 1
    assert "FREEDOM LEVEL: 5/10" in generated_calls[0]
    assert len(list(queue_dir.glob("*.json"))) == 0

    # 4. Simulate Replica 2 query (unauthorized rejected, authorized returns signed media URL)
    unauth_resp = _run_coro(main.get_task(task_id, _make_request()))
    assert unauth_resp.status_code == 403

    status_payload = _run_coro(
        main.get_task(task_id, _make_request(headers={"x-task-token": task_token}))
    )
    assert isinstance(status_payload, dict)
    assert status_payload["status"] == "completed"
    signed_url = status_payload["result_url"]
    parsed_signed = urlparse(signed_url)
    result_filename = os.path.basename(parsed_signed.path)
    assert parsed_signed.path == f"/api/media/results/{result_filename}"
    assert "st=" in parsed_signed.query

    # Signed media proxy enforcement
    bad_media = _run_coro(
        main.serve_authorized_result(result_filename, _make_request(query_string="st=invalid"))
    )
    assert bad_media.status_code == 403

    ok_media = _run_coro(
        main.serve_authorized_result(result_filename, _make_request(query_string=parsed_signed.query))
    )
    assert ok_media.status_code == 200
    assert ok_media.body[:8] == b"\x89PNG\r\n\x1a\n"

    # Authorized download works; unauthorized rejected
    bad_dl = _run_coro(main.download_single(url=f"/assets/{result_filename}", request=_make_request()))
    assert bad_dl.status_code == 403
    ok_dl = _run_coro(
        main.download_single(
            url=f"/assets/{result_filename}",
            request=_make_request(headers={"x-task-token": task_token}),
        )
    )
    assert ok_dl.status_code == 200

    # Duplicate message for already completed task is skipped without calling AI again
    q.enqueue(task_id)
    processed_dup = _run_coro(
        queue_worker.run_worker_batch(
            max_messages=5,
            task_queue=q,
            db_url=db_url,
            generate_fn=fake_generate,
        )
    )
    assert processed_dup == 1
    assert len(generated_calls) == 1

    # Fallback recovery from private Blob manifest if DB row is missing
    SessionFactory, _ = task_db.get_session_factory(db_url)
    with SessionFactory() as session:
        rec = session.get(task_db.WorkbenchTaskRecord, task_id)
        session.delete(rec)
        session.commit()
    recovered_payload = _run_coro(
        main.get_task(task_id, _make_request(headers={"x-task-token": task_token}))
    )
    assert isinstance(recovered_payload, dict)
    assert recovered_payload["status"] in {"queued", "completed"}


def test_aca_worker_lease_recovery_and_unknown_timeout_contract(monkeypatch, tmp_path):
    db_url, uploads, assets, obj_root, queue_dir = _configure_env(monkeypatch, tmp_path)

    from app.object_storage import get_object_storage
    import main

    monkeypatch.setattr(main, "UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(main, "ASSET_DIR", str(assets))
    monkeypatch.setattr(main, "_TASK_QUEUE", task_queue.LocalTaskQueue(queue_dir))

    storage = get_object_storage()
    storage.upload_bytes("tryon-uploads/m2.png", _png_bytes("white"), content_type="image/png")
    storage.upload_bytes("tryon-uploads/g2.png", _png_bytes("black"), content_type="image/png")

    token_hash = task_db.hash_access_token("visitor-lease-token")
    task_id = "task-lease-recovery-1"
    task_db.create_or_get_task(
        task_id=task_id,
        idempotency_key="idem-lease-1",
        access_token_hash=token_hash,
        locale="zh-CN",
        model_key="pro",
        freedom=5,
        garment_type="",
        custom_prompt=None,
        prompt_mode="append",
        target_filename="m2.png",
        reference_filename="g2.png",
        input_target_blob="tryon-uploads/m2.png",
        input_reference_blob="tryon-uploads/g2.png",
        status="queued",
        db_url=db_url,
    )

    # Simulate crashed worker 1 holding an expired lease before upstream started
    SessionFactory, _ = task_db.get_session_factory(db_url)
    with SessionFactory() as session:
        rec = session.get(task_db.WorkbenchTaskRecord, task_id)
        rec.status = "processing"
        rec.lease_owner = "dead-worker"
        rec.lease_expires_at = 1.0  # expired long ago
        rec.upstream_status = "not_started"
        session.commit()

    attempts = 0

    async def timeout_generate(**kwargs):
        del kwargs
        nonlocal attempts
        attempts += 1
        raise queue_worker.UpstreamResultUnknownError("upstream timeout during image generation")

    q = task_queue.LocalTaskQueue(queue_dir)
    q.enqueue(task_id)
    processed = _run_coro(
        queue_worker.run_worker_batch(
            max_messages=2,
            task_queue=q,
            db_url=db_url,
            generate_fn=timeout_generate,
        )
    )
    assert processed == 1
    assert attempts == 1

    rec_after = task_db.get_task_record(task_id, db_url=db_url)
    assert rec_after is not None
    assert rec_after["status"] == "unknown"
    assert rec_after["upstream_status"] == "unknown_timeout"

    # Admin retry endpoint auth & unknown guard
    no_auth = _run_coro(
        main.retry_failed_task(
            _make_request(method="POST", path="/api/retry"),
            payload={"task_id": task_id},
        )
    )
    assert no_auth.status_code == 403

    blocked_unknown = _run_coro(
        main.retry_failed_task(
            _make_request(method="POST", path="/api/retry", headers={"x-ingest-key": "test-ingest-secret"}),
            payload={"task_id": task_id, "allow_unknown_retry": False},
        )
    )
    assert blocked_unknown.status_code == 400

    allowed_retry = _run_coro(
        main.retry_failed_task(
            _make_request(method="POST", path="/api/retry", headers={"x-ingest-key": "test-ingest-secret"}),
            payload={"task_id": task_id, "allow_unknown_retry": True},
        )
    )
    assert allowed_retry["ok"] is True
    assert allowed_retry["status"] == "queued"
    assert len(list(queue_dir.glob("*.json"))) == 1


def test_shared_rate_limit_and_frontend_contract(monkeypatch, tmp_path):
    db_url, *_ = _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("TRYON_MONTHLY_LIMIT", "2")

    limits = {"rpm": 60, "tpm": 100000, "rpd": 1000}
    res1 = task_db.check_and_consume_shared_rate_limit(
        identity="tryon_config", model_key="flash", token_cost=10, limits=limits, db_url=db_url
    )
    res2 = task_db.check_and_consume_shared_rate_limit(
        identity="tryon_config", model_key="flash", token_cost=10, limits=limits, db_url=db_url
    )
    assert res1["monthly_used"] == 1 and res2["monthly_used"] == 2
    with pytest.raises(RuntimeError, match="月度"):
        task_db.check_and_consume_shared_rate_limit(
            identity="tryon_config", model_key="flash", token_cost=10, limits=limits, db_url=db_url
        )

    script_text = (CLOUD_ROOT / "static/js/script.js").read_text(encoding="utf-8")
    assert "idempotency_key" in script_text
    assert "X-Task-Token" in script_text
    assert "sessionStorage" in script_text
    assert "visibilitychange" in script_text
    assert "pagehide" in script_text
    assert "d.status === 'unknown'" in script_text



def test_workbench_health_deep_and_direct_db_admin_report(monkeypatch, tmp_path):
    import asyncio
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from app import admin_report, object_storage, task_db

    db_file = tmp_path / "wb_health.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("TASK_DATABASE_URL", db_url)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_DIR", str(tmp_path / "objects"))
    monkeypatch.setenv("TASK_QUEUE_PROVIDER", "local")
    monkeypatch.setenv("TASK_QUEUE_LOCAL_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("ADMIN_REPORT_MODE", "db")
    monkeypatch.setenv("ADMIN_API_URL", "")
    task_db.reset_engine_cache()
    object_storage._cached_storage = None

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS page_views ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, source VARCHAR(50), "
            "page VARCHAR(512), session_id VARCHAR(64), user_agent VARCHAR(512), ip VARCHAR(50))"
        ))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS tryon_tasks ("
            "id VARCHAR(36) PRIMARY KEY, created_at DATETIME, updated_at DATETIME, "
            "status VARCHAR(20), user_photo_url VARCHAR(1024), product_id INTEGER, "
            "result_image_url VARCHAR(1024), error_type VARCHAR(50), error_detail TEXT, "
            "duration_ms FLOAT, model_used VARCHAR(100))"
        ))

    import main as wb_main
    wb_main._task_queue = None
    with TestClient(wb_main.app) as client:
        resp = client.get("/health/deep")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"]["ok"] is True
        assert data["checks"]["object_storage"]["ok"] is True
        assert data["checks"]["task_queue"]["ok"] is True

    asyncio.run(admin_report.report_page_view(source="tryon_workbench", page="/", ip="1.2.3.4"))
    asyncio.run(admin_report.report_tryon_task("task-db-1", "queued", product_id=7, model_used="flash"))
    asyncio.run(admin_report.report_tryon_task(
        "task-db-1", "completed", result_image_url="/api/media/results/out.png", duration_ms=512.5, model_used="flash"
    ))

    with engine.connect() as conn:
        pv_count = conn.execute(text("SELECT COUNT(*) FROM page_views WHERE source = 'tryon_workbench'")).scalar()
        task_row = conn.execute(text("SELECT status, result_image_url, duration_ms, product_id FROM tryon_tasks WHERE id = 'task-db-1'")).first()
    assert pv_count == 1
    assert task_row == ("completed", "/api/media/results/out.png", 512.5, 7)
    task_db.reset_engine_cache()


def test_intake_image_falls_back_to_data_url_when_url_fetch_fails(monkeypatch, tmp_path):
    import base64
    from fastapi.testclient import TestClient

    _configure_env(monkeypatch, tmp_path)
    import main as wb_main

    async def fail_fetch(_url: str):
        raise ValueError("loopback blocked")

    monkeypatch.setattr(wb_main, "_fetch_remote_image_bytes", fail_fetch)
    data_url = "data:image/png;base64," + base64.b64encode(_png_bytes("purple")).decode("ascii")

    with TestClient(wb_main.app) as client:
        resp = client.post(
            "/api/intake-image",
            json={
                "role": "model",
                "locale": "zh-CN",
                "image_url": "http://127.0.0.1:5173/sample-models/male/mannequin-male-1.png",
                "image_data_url": data_url,
            },
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["ok"] is True
        assert body["source_type"] == "data_url"
        assert body["filename"].endswith(".png")
    task_db.reset_engine_cache()

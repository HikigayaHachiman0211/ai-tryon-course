"""Acceptance tests for Main and Admin ACA scale-to-zero deployment adaptations."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import PIL.Image
import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

APP_ROOT = Path(__file__).resolve().parents[3]
MAIN_BACKEND = APP_ROOT / "backend"
ADMIN_BACKEND = APP_ROOT / "admin" / "backend"


def _make_request(headers: dict[str, str] | None = None, path: str = "/") -> Request:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "https",
    }
    return Request(scope)


def _run_coro(coro):
    try:
        while True:
            val = coro.send(None)
            if val is not None:
                raise AssertionError(f"Unexpected awaitable suspension: {val!r}")
    except StopIteration as stop:
        return stop.value
    finally:
        coro.close()


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PIL.Image.new("RGB", (8, 8), "teal").save(buf, "PNG")
    return buf.getvalue()


def test_main_history_db_private_media_and_debug_auth(monkeypatch, tmp_path):
    if str(MAIN_BACKEND) not in sys.path:
        sys.path.insert(0, str(MAIN_BACKEND))

    from app import admin_report, database, gcs_storage, history, object_storage
    from app import main as main_app
    from app.errors import AppError

    db_url = f"sqlite:///{(tmp_path / 'main_test.db').as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    database.Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(database, "ENGINE", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr(history, "ENGINE", engine)
    monkeypatch.setattr(history, "SessionLocal", session_factory)
    monkeypatch.setenv("HISTORY_DB_ENABLED", "true")

    obj_root = tmp_path / "obj"
    obj_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(obj_root))
    monkeypatch.setattr(object_storage, "_cached_storage", None)
    monkeypatch.setenv("FORCE_PRIVATE_USER_PHOTOS", "true")
    monkeypatch.setenv("INGEST_SECRET_KEY", "test-ingest-secret")
    monkeypatch.setattr(admin_report, "INGEST_SECRET_KEY", "test-ingest-secret")

    hist_dir = tmp_path / "hist"
    monkeypatch.setattr(history, "LOCAL_HISTORY_DIR", hist_dir)
    monkeypatch.setattr(history, "LOCAL_RESULTS_DIR", hist_dir / "results")
    monkeypatch.setattr(history, "LOCAL_THUMBS_DIR", hist_dir / "thumbnails")
    monkeypatch.setattr(history, "LOCAL_INDEX_PATH", hist_dir / "index.json")

    monkeypatch.setattr(history, "_resolve_first_image_url", lambda *_: "https://example.invalid/thumb.png")
    monkeypatch.setattr(history, "_download_image_bytes", lambda *_: _png_bytes())

    # 1. Private user photo returns signed URL; unauthorized denied; valid token allowed
    photo_url = gcs_storage.save_user_photo("res123", _png_bytes(), content_type="image/png")
    assert photo_url is not None and photo_url.startswith("/api/media/user-photos/res123.png?st=")
    st_token = photo_url.split("st=", 1)[1]

    with pytest.raises(HTTPException) as exc_info:
        main_app.get_private_user_photo(_make_request(), "res123.png", st="bad")
    assert exc_info.value.status_code == 403

    photo_resp = main_app.get_private_user_photo(_make_request(), "res123.png", st=st_token)
    assert photo_resp.status_code == 200
    assert photo_resp.body == _png_bytes()

    # 2. Save history -> simulate scale-to-zero by deleting all local disk files -> still readable from DB + Blob
    entry = history.save_history(
        {
            "locale": "zh-CN",
            "inference": {"resolved_style": "休闲", "resolved_size": "L"},
            "items": [{"product_key": "p1", "title": "测试羽绒服", "price": 299.0, "image_url": "/static/products/a.png"}],
        },
        "recommend",
        base_url="https://tryon-main.example",
    )
    assert entry["thumbnail_url"] == f"/api/history/{entry['id']}/thumbnail"

    for f in (hist_dir / "results").glob("*"):
        f.unlink()
    for f in (hist_dir / "thumbnails").glob("*"):
        f.unlink()
    if (hist_dir / "index.json").exists():
        (hist_dir / "index.json").unlink()

    items = history.list_history(limit=10, locale="zh-CN")
    assert len(items) == 1
    assert items[0]["id"] == entry["id"]
    assert items[0]["thumbnail_url"] == f"/api/history/{entry['id']}/thumbnail"

    detail = history.get_history_detail(entry["id"])
    assert detail is not None and detail["items"][0]["product_key"] == "p1"

    thumb_bytes = history.get_thumbnail_bytes(entry["id"])
    assert thumb_bytes is not None and thumb_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    # 3. Debug endpoint disabled for anonymous, enabled for X-Ingest-Key
    monkeypatch.setattr(main_app, "debug_pages_enabled", False)
    with pytest.raises(AppError) as dbg_err:
        main_app.get_recent_error_events(_make_request())
    assert dbg_err.value.status_code == 403

    internal_res = main_app.get_recent_error_events(_make_request(headers={"X-Ingest-Key": "test-ingest-secret"}))
    assert "items" in internal_res


@pytest.fixture
def isolated_admin_app(monkeypatch):
    def is_app_module(name):
        return name == "app" or name.startswith("app.")

    saved_modules = {name: module for name, module in sys.modules.copy().items() if is_app_module(name)}
    for name in saved_modules:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(ADMIN_BACKEND))
    try:
        yield
    finally:
        for name in list(sys.modules):
            if is_app_module(name):
                del sys.modules[name]
        sys.modules.update(saved_modules)


def test_admin_db_init_job_voice_clone_and_retry(isolated_admin_app, monkeypatch, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'admin_test.db').as_posix()}"
    obj_root = tmp_path / "admin_obj"
    obj_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_DIR", str(obj_root))
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-jwt-secret")
    monkeypatch.setenv("FERNET_SECRET_KEY", "test-fernet-unused")
    monkeypatch.setenv("INGEST_SECRET_KEY", "test-ingest-secret")
    monkeypatch.setenv("MAIN_SITE_URL", "https://main.example")
    monkeypatch.setenv("TRYON_WORKBENCH_URL", "https://workbench.example/static/index.html")

    from app import config as admin_config
    from app import database as admin_db
    from app import db_init_job
    from app.routers import system as system_router
    from app.routers import tryon_tasks as tasks_router
    from app.routers import voice_clone as vc_router
    from app.services import gcs as admin_gcs

    admin_config.get_settings.cache_clear()
    admin_db._engine = None
    admin_db._SessionLocal = None

    # 1. Verify _build_product_kwargs populates product_url, size_tags, size_notes, and brand tags + init_db idempotency
    kwargs = admin_db._build_product_kwargs(
        {
            "商品标题": "波司登 2026新款 羽绒服 M/L 建议体重110-130斤",
            "价格": 599,
            "图片路径": "羽绒服_png/test.png",
            "款式类型": "短款",
            "精准颜色色系": "黑色系",
            "版型与身材适配度": "常规",
            "风格特征": ["休闲"],
            "功能属性": ["防风"],
            "品牌": "波司登",
            "商品链接": "https://item.jd.com/123456.html",
        }
    )
    assert kwargs["product_url"] == "https://item.jd.com/123456.html"
    assert "M" in kwargs["size_tags"] and "L" in kwargs["size_tags"]
    assert "建议体重" in (kwargs["size_notes"] or "")
    assert "品牌:波司登" in kwargs["style_features"]

    seed_file = tmp_path / "seed_database.json"
    seed_file.write_text(
        json.dumps(
            [
                {
                    "商品标题": "波司登 2026新款 羽绒服 M/L 建议体重110-130斤",
                    "价格": 599,
                    "图片路径": "羽绒服_png/test1.png",
                    "款式类型": "短款",
                    "精准颜色色系": "黑色系",
                    "版型与身材适配度": "常规",
                    "风格特征": ["休闲"],
                    "功能属性": ["防风"],
                    "品牌": "波司登",
                    "商品链接": "https://item.jd.com/123456.html",
                },
                {
                    "商品标题": "优衣库 轻薄羽绒服 S/M",
                    "价格": 399,
                    "图片路径": "羽绒服_png/test2.png",
                    "款式类型": "短款",
                    "精准颜色色系": "白色系",
                    "版型与身材适配度": "常规",
                    "风格特征": ["简约"],
                    "功能属性": ["保暖"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(admin_db, "_resolve_seed_json_path", lambda: seed_file)

    summary1 = db_init_job.run_db_init_job()
    summary2 = db_init_job.run_db_init_job()
    assert summary1["products"] == 2
    assert summary1["products"] == summary2["products"]
    assert summary1["products_with_url"] == 1

    # 2. Voice clone private Blob upload/download/delete
    stored_blobs: dict[str, bytes] = {}
    monkeypatch.setattr(
        admin_gcs,
        "upload_blob",
        lambda name, data, content_type="application/octet-stream": stored_blobs.__setitem__(name, data) or name,
    )
    monkeypatch.setattr(admin_gcs, "download_blob", lambda name: stored_blobs.get(name))
    monkeypatch.setattr(admin_gcs, "delete_blob", lambda name: stored_blobs.pop(name, None) is not None)

    admin_user = SimpleNamespace(username="admin")
    Factory = admin_db.get_session_factory()
    with Factory() as session:
        created = vc_router.create_voice_clone(
            name="test-voice",
            description="",
            gender="female",
            language="zh",
            admin=admin_user,
            db=session,
        )
        pid = created["id"]

        class _FakeUpload:
            def __init__(self, filename: str, data: bytes):
                self.filename = filename
                self._data = data

            async def read(self) -> bytes:
                return self._data

        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        upload_obj = _FakeUpload(filename="sample.wav", data=wav_bytes)
        up_res = _run_coro(vc_router.upload_reference_audio(pid, audio=upload_obj, admin=admin_user, db=session))
        assert up_res["ok"] is True
        assert up_res["blob_path"].startswith(f"voice-clones/{pid}/")
        assert up_res["blob_path"] in stored_blobs

        dl_res = vc_router.download_reference_audio(pid, admin=admin_user, db=session)
        assert dl_res.status_code == 200
        assert dl_res.body == wav_bytes

        del_res = vc_router.delete_voice_clone(pid, admin=admin_user, db=session)
        assert del_res["ok"] is True
        assert len(stored_blobs) == 0

    # 3. Admin retry_task normalizes URL, sends X-Ingest-Key & allow_unknown_retry, supports unknown status
    assert tasks_router._normalize_workbench_root("https://wb.example/static/index.html/") == "https://wb.example"
    captured_calls: list[tuple[str, dict, dict]] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured_calls.append((url, headers or {}, json or {}))
            return SimpleNamespace(status_code=200, text="ok")

        async def get(self, url, params=None, headers=None):
            captured_calls.append((url, headers or {}, params or {}))
            return SimpleNamespace(status_code=200, json=lambda: {"items": [{"code": "E1"}]})

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with Factory() as session:
        t = admin_db.TryonTask(
            id="tryon-unknown-1",
            status="unknown",
            user_photo_url="/uploads/u1.png",
            product_id=1,
            model_used="flash",
        )
        session.add(t)
        session.commit()

        retry_res = _run_coro(tasks_router.retry_task("tryon-unknown-1", admin=admin_user, db=session))
        assert retry_res["status"] == "queued"
        post_url, post_headers, post_json = captured_calls[0]
        assert post_url == "https://workbench.example/api/retry"
        assert post_headers.get("X-Ingest-Key") == "test-ingest-secret"
        assert post_json == {"task_id": "tryon-unknown-1", "allow_unknown_retry": True}

    err_res = _run_coro(system_router.proxy_errors(limit=10, admin=admin_user))
    assert err_res == {"items": [{"code": "E1"}]}
    get_url, get_headers, _ = captured_calls[1]
    assert get_url == "https://main.example/api/debug/errors/recent"
    assert get_headers.get("X-Ingest-Key") == "test-ingest-secret"



def test_main_admin_report_db_writes_request_logs_and_user_profiles(monkeypatch, tmp_path):
    from sqlalchemy import create_engine, text

    db_url = f"sqlite:///{(tmp_path / 'shared_admin.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS request_logs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, endpoint VARCHAR(100), "
            "method VARCHAR(10), status_code INTEGER, duration_ms FLOAT, user_ip VARCHAR(50), request_params JSON)"
        ))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS user_profiles ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id VARCHAR(64), created_at DATETIME, "
            "photo_url VARCHAR(1024), gender VARCHAR(20), mbti VARCHAR(10), color_preference VARCHAR(100), "
            "size_input VARCHAR(20), style_input VARCHAR(100), ai_recommended_size VARCHAR(20), "
            "ai_body_shape VARCHAR(50), ai_suggested_style VARCHAR(100), ai_reasoning TEXT, "
            "used_fallback BOOLEAN, recommendation_count INTEGER DEFAULT 0)"
        ))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS page_views ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, source VARCHAR(50), "
            "page VARCHAR(512), session_id VARCHAR(64), user_agent VARCHAR(512), ip VARCHAR(50))"
        ))

    from app import admin_report, database
    monkeypatch.setattr(admin_report, "ADMIN_REPORT_MODE", "db")
    monkeypatch.setattr(admin_report, "ADMIN_API_URL", "")
    monkeypatch.setattr(database, "ENGINE", engine)

    admin_report.report_request_log(
        endpoint="/api/recommend", method="POST", status_code=200, duration_ms=42.5,
        user_ip="127.0.0.1", request_params={"q": "down"},
    )
    admin_report.report_user_profile(
        session_id="sess-1", gender="female", mbti="INTJ", color_preference="black",
        size_input="M", style_input="casual", ai_recommended_size="M",
        ai_body_shape="balanced", ai_suggested_style="casual", ai_reasoning="fit", used_fallback=False,
    )
    admin_report.report_page_view(source="main_site", page="/", session_id="sess-1", user_agent="pytest", ip="127.0.0.1")

    with engine.connect() as conn:
        req_count = conn.execute(text("SELECT COUNT(*) FROM request_logs WHERE endpoint = '/api/recommend'")).scalar()
        prof_row = conn.execute(text("SELECT session_id, recommendation_count FROM user_profiles WHERE session_id = 'sess-1'")).first()
        pv_count = conn.execute(text("SELECT COUNT(*) FROM page_views WHERE source = 'main_site'")).scalar()
    assert req_count == 1
    assert prof_row == ("sess-1", 0)
    assert pv_count == 1


def test_azure_save_user_photo_always_returns_signed_proxy_url_when_media_public_url_unset(monkeypatch):
    if str(MAIN_BACKEND) not in sys.path:
        sys.path.insert(0, str(MAIN_BACKEND))

    from app import gcs_storage

    class _FakeAzureStorage:
        settings = SimpleNamespace(provider="azure")

        def upload_bytes(self, name, data, *, content_type=None, cache_control=None):
            del name, data, content_type, cache_control
            return "https://tryonst.blob.core.windows.net/product-images/ai-tryon-results/user_photos/x.webp"

    monkeypatch.delenv("FORCE_PRIVATE_USER_PHOTOS", raising=False)
    monkeypatch.delenv("PUBLIC_MEDIA_BASE_URL", raising=False)
    monkeypatch.setattr(gcs_storage, "get_object_storage", lambda: _FakeAzureStorage())

    url = gcs_storage.save_user_photo("res-az-1", b"RIFFWEBP", content_type="image/webp")
    assert url is not None
    assert url.startswith("/api/media/user-photos/res-az-1.webp?st=")

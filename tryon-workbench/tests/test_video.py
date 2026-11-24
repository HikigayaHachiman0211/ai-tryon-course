"""Video integration contracts. All databases and upstream traffic are isolated."""
import asyncio
import copy
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PARAMS = [
    {"name": "prompt", "type": "text", "required": True, "maxLength": 1000},
    {"name": "image_url", "type": "image"},
    {"name": "duration", "type": "integer", "default": 5, "min": 3, "max": 15},
    {"name": "resolution", "type": "enum", "options": ["720p", "1080p"], "default": "720p"},
    {"name": "generate_audio", "type": "boolean", "default": False},
    {"name": "image_urls", "type": "images", "maxItems": 2},
]
MODEL = {"slug": "video-model", "type": "video", "name": "Video Model", "params": PARAMS,
         "providers": [{"provider": "fal", "params": PARAMS[:-1]}]}


def test_dynamic_parameter_validation_preserves_types_and_defaults():
    from app.video_gateway import validate_input
    result = validate_input(PARAMS, {"prompt": "保留羽绒服细节，缓慢转身", "generate_audio": False})
    assert result["duration"] == 5
    assert result["generate_audio"] is False
    assert result["resolution"] == "720p"
    assert validate_input(PARAMS, {"prompt": "test", "image_url": "http://images.example.org/photo.png"})["image_url"].startswith("http://")


@pytest.mark.parametrize("values", [
    {"prompt": ""}, {"prompt": "a", "duration": 1}, {"prompt": "a", "duration": 5.5},
    {"prompt": "a", "duration": True}, {"prompt": "a", "generate_audio": "false"},
    {"prompt": "a", "resolution": "4K"}, {"prompt": "a", "unknown": 1},
    {"prompt": "a", "image_urls": ["https://example.org/1.png"] * 3},
    {"prompt": "a", "image_url": "file:///private/photo.png"},
    {"prompt": "a", "image_url": "https://127.0.0.1/photo.png"},
    {"prompt": "a" * 1001},
])
def test_invalid_model_parameters_are_rejected(values):
    from app.video_gateway import VideoError, validate_input
    with pytest.raises(VideoError):
        validate_input(PARAMS, values)


def test_provider_constraints_and_project_aliases():
    from app.video_gateway import VideoError, parameters_for
    model = copy.deepcopy(MODEL)
    model["providers"][0]["params"][2]["max"] = 6
    assert parameters_for(model, "fal")[2]["max"] == 6
    with pytest.raises(VideoError):
        parameters_for(model, "other")
    assert parameters_for({"params": PARAMS, "provider": "fal"}, "")[0]["name"] == "prompt"


def test_connection_validation_allows_only_official_live_or_sandbox():
    from app.video_config import normalize_base_url
    assert normalize_base_url("https://01router.com/api/v1/") == "https://01router.com/api/v1"
    assert normalize_base_url("https://01router.com/api/sandbox/v1")
    for value in ("http://01router.com/api/v1", "https://evil.test/api/v1", "https://01router.com@evil.test", "https://01router.com/api/v1?key=secret"):
        with pytest.raises(ValueError):
            normalize_base_url(value)


def test_native_gateway_transport_authentication_and_ambiguous_failures(monkeypatch):
    from app import video_gateway
    real_client = httpx.AsyncClient
    cfg = {"base_url": "https://01router.com/api/v1", "api_key": "private-key", "timeout_seconds": 30}
    seen = []

    async def upstream(request):
        seen.append(request)
        if request.url.path.endswith("/generations"):
            raise httpx.ReadTimeout("unconfirmed", request=request)
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(video_gateway.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))

    async def scenario():
        await video_gateway.gateway_request("GET", "/models", cfg, params={"type": "video"})
        await video_gateway.gateway_request("POST", "/quote", cfg, body={"model": "selected", "input": {"prompt": "turn"}})
        with pytest.raises(video_gateway.VideoError) as failure:
            await video_gateway.gateway_request("POST", "/generations", cfg, body={"model": "selected", "input": {"prompt": "turn"}}, protected=True)
        assert failure.value.code == "submission_unknown"
        assert "private-key" not in str(failure.value)
    run(scenario())
    assert str(seen[0].url) == "https://01router.com/api/v1/models?type=video"
    assert "authorization" not in seen[0].headers
    assert "authorization" not in seen[1].headers
    assert seen[2].headers["authorization"] == "Bearer private-key"
    assert seen[2].headers["content-type"] == "application/json"
    assert len(seen) == 3


def test_video_locale_resources_have_identical_nested_keys():
    import json
    root = Path(__file__).resolve().parents[1] / "static/i18n"

    def keys(value, prefix=""):
        result = set()
        for key, child in value.items():
            path = prefix + key
            result |= keys(child, path + ".") if isinstance(child, dict) else {path}
        return result

    bundles = [json.loads((root / f"{locale}.json").read_text(encoding="utf-8"))["video"] for locale in ("zh-CN", "en", "ja")]
    assert keys(bundles[0]) == keys(bundles[1]) == keys(bundles[2])
    assert "脸部" in bundles[0]["prompts"]["turn"]
    assert "facial" in bundles[1]["prompts"]["turn"].lower()
    assert "顔" in bundles[2]["prompts"]["turn"]


def test_runtime_keeps_admin_disable_authoritative_and_supports_env_fallback(monkeypatch):
    from app import video_config
    video_config.clear_config_cache()
    monkeypatch.setenv("ROUTER01_API_KEY", "environment-test-key")
    monkeypatch.setenv("ROUTER01_BASE_URL", video_config.LIVE_BASE_URL)
    monkeypatch.setattr(video_config, "_read_video_config", lambda: {"enabled": False, "api_key": "", "base_url": video_config.LIVE_BASE_URL, "source": "admin_db"})
    assert video_config.resolve_video_config()["enabled"] is False
    assert video_config.resolve_video_config()["api_key"] == ""
    video_config.clear_config_cache()
    monkeypatch.setattr(video_config, "_read_video_config", lambda: None)
    assert video_config.resolve_video_config()["api_key"] == "environment-test-key"
    video_config.clear_config_cache()


@pytest.fixture
def integration(monkeypatch, tmp_path):
    from app import task_db, video_gateway, video_routes
    task_db.reset_engine_cache()
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}")
    config = {"base_url": "https://01router.com/api/v1", "api_key": "test-secret",
              "project_id": "", "enabled": True, "timeout_seconds": 30,
              "rate_limit_per_minute": 10, "daily_quota_limit": 50, "source": "test"}
    calls = []
    state = {"timeout": False, "cancel": False}

    async def upstream(method, path, cfg, *, body=None, params=None, protected=False):
        calls.append((method, path, body, params, protected))
        if path == "/models":
            return {"object": "list", "data": [MODEL, {"slug": "image-only", "type": "image"}]}
        if path == "/quote":
            return {"providers": [{"provider": "fal", "price_usd": 0.25, "credits": 25}], "unavailable": []}
        if path == "/generations" and state["timeout"]:
            raise video_gateway.VideoError(504, "submission_unknown", "Outcome unknown")
        return {"id": "gen_test", "type": "video", "status": "failed" if state["cancel"] else ("processing" if method == "POST" else "succeeded"),
                "outputs": [] if method == "POST" else ["https://example.org/result.mp4"],
                "error": "Canceled by user" if state["cancel"] else None, "price_usd": 0.25, "credits": 25}

    monkeypatch.setattr(video_routes, "resolve_video_config", lambda: config)
    monkeypatch.setattr(video_gateway, "gateway_request", upstream)
    video_gateway.clear_catalog_cache()
    app = FastAPI()
    app.include_router(video_routes.build_video_router(
        owner_token=lambda request: request.headers.get("x-test-owner", "owner-a"),
        resolve_image=lambda request, value: "https://media.example.org/photo.png" if value.startswith("/uploads/") else value,
    ))
    yield app, config, calls, state
    task_db.reset_engine_cache()


def run(coro):
    return asyncio.run(coro)


def test_catalog_quote_and_exact_submission_with_recovery(integration):
    app, cfg, calls, state = integration

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            models = await client.get("/api/video/models")
            assert [m["slug"] for m in models.json()["data"]] == ["video-model"]
            assert "test-secret" not in models.text
            body = {"model": "video-model", "provider": "fal", "input": {"prompt": "turn slowly", "image_url": "/uploads/a.png", "duration": 5}, "idempotency_key": "first-job"}
            quote = await client.post("/api/video/quote", json=body)
            assert quote.status_code == 200
            first = await client.post("/api/video/tasks", json=body)
            assert first.status_code == 200, first.text
            task_id = first.json()["id"]
            receipt = await client.get("/api/video/submissions/first-job")
            assert receipt.json()["id"] == task_id
            duplicate = await client.post("/api/video/tasks", json=body)
            assert duplicate.json()["id"] == task_id
            assert len([c for c in calls if c[1] == "/generations"]) == 1
            sent = [c[2] for c in calls if c[1] == "/generations"][0]
            assert sent["provider"] == "fal"
            assert sent["input"]["image_url"] == "https://media.example.org/photo.png"
            assert "project" not in sent
            assert "idempotency_key" not in sent
            other = await client.get(f"/api/video/tasks/{task_id}", headers={"x-test-owner": "owner-b"})
            assert other.status_code == 404
            result = await client.get(f"/api/video/tasks/{task_id}")
            assert result.json()["status"] == "succeeded"
            assert result.json()["outputs"] == ["https://example.org/result.mp4"]
            restored = await client.get("/api/video/tasks")
            assert restored.json()["data"][0]["id"] == task_id
            assert "test-secret" not in restored.text
    run(scenario())


def test_video_download_is_owned_and_streams_an_attachment(integration, monkeypatch):
    from app import video_gateway
    app, cfg, calls, state = integration
    real_client = httpx.AsyncClient
    seen = []

    async def media(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"video-content", headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr(video_gateway, "check_download_url", lambda url: None)

    async def scenario():
        async with real_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/video/tasks", json={"model": "video-model", "input": {"prompt": "test"}, "idempotency_key": "download"})
            task_id = response.json()["id"]
            await client.get(f"/api/video/tasks/{task_id}")
            with pytest.MonkeyPatch.context() as patcher:
                patcher.setattr(video_gateway.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(media), **kwargs))
                other = await client.get(f"/api/video/tasks/{task_id}/download", headers={"x-test-owner": "owner-b"})
                assert other.status_code == 404
                assert seen == []
                result = await client.get(f"/api/video/tasks/{task_id}/download")
                assert result.content == b"video-content"
                assert result.headers["content-type"].startswith("video/mp4")
                assert "attachment" in result.headers["content-disposition"]
                assert seen == ["https://example.org/result.mp4"]
                saved = (await client.get("/api/video/tasks")).json()["data"][0]
                signed = await client.get(saved["download_urls"][0], headers={"x-test-owner": "owner-b"})
                assert signed.content == b"video-content"
    run(scenario())


def test_ambiguous_submission_is_persisted_and_never_retried(integration):
    app, cfg, calls, state = integration
    state["timeout"] = True

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = {"model": "video-model", "input": {"prompt": "test"}, "idempotency_key": "ambiguous"}
            first = await client.post("/api/video/tasks", json=body)
            assert first.json()["status"] == "unknown"
            retry = await client.post("/api/video/tasks", json=body)
            assert retry.json()["id"] == first.json()["id"]
            assert len([c for c in calls if c[1] == "/generations"]) == 1
            changed = await client.post("/api/video/tasks", json={**body, "input": {"prompt": "changed"}})
            assert changed.status_code == 409
    run(scenario())


def test_missing_key_keeps_catalog_and_quote_public(integration):
    app, cfg, calls, state = integration
    cfg["api_key"] = ""
    cfg["project_id"] = "project-test"

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/video/models")).status_code == 200
            assert (await client.post("/api/video/quote", json={"model": "video-model", "input": {"prompt": "test"}})).status_code == 200
            response = await client.post("/api/video/tasks", json={"model": "video-model", "input": {"prompt": "test"}, "idempotency_key": "no-key"})
            assert response.status_code == 503
            assert [c for c in calls if c[1] == "/models"][0][3]["project"] == "project-test"
            assert [c for c in calls if c[1] == "/quote"][0][2]["project"] == "project-test"
    run(scenario())


def test_config_provides_a_private_visitor_session_for_embedded_browsers(integration):
    from app import video_routes
    original, cfg, calls, state = integration
    app = FastAPI()
    app.include_router(video_routes.build_video_router(
        owner_token=lambda request: request.headers.get("x-task-token") or request.cookies.get("tryon_visitor_token"),
        resolve_image=lambda request, value: value,
    ))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            config = await client.get("/api/video/config")
            token = config.json()["task_token"]
            assert len(token) >= 24
            assert token == client.cookies.get("tryon_visitor_token")
            assert config.headers["cache-control"] == "private, no-store"
            assert "test-secret" not in config.text
            client.cookies.clear()
            response = await client.post("/api/video/tasks", headers={"x-task-token": token}, json={"model": "video-model", "input": {"prompt": "test"}, "idempotency_key": "embedded"})
            assert response.status_code == 200
            assert (await client.get("/api/video/tasks", headers={"x-task-token": token})).json()["data"][0]["id"] == response.json()["id"]
    run(scenario())


def test_terminal_task_does_not_regress_when_a_stale_poll_arrives(integration):
    from app import video_tasks
    app, cfg, calls, state = integration
    task, created = video_tasks.reserve_task("owner", "unique", "hash", cfg, "video-model", "fal")
    video_tasks.save_result(task["id"], {"id": "gen_test", "status": "failed", "error": "Canceled by user"})
    updated = video_tasks.save_result(task["id"], {"id": "gen_test", "status": "processing"})
    assert updated["status"] == "failed"
    assert updated["error"] == "Canceled by user"


def test_cancel_and_config_change_protection(integration):
    app, cfg, calls, state = integration

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = {"model": "video-model", "input": {"prompt": "test"}, "idempotency_key": "cancel-job"}
            first = (await client.post("/api/video/tasks", json=body)).json()
            state["cancel"] = True
            result = await client.post(f"/api/video/tasks/{first['id']}/cancel")
            assert result.json()["status"] == "failed"
            assert any(c[1] == "/generations/gen_test/cancel" for c in calls)
            body["idempotency_key"] = "other-job"
            state["cancel"] = False
            task = (await client.post("/api/video/tasks", json=body)).json()
            cfg["project_id"] = "different-project"
            assert (await client.get(f"/api/video/tasks/{task['id']}")).status_code == 409
    run(scenario())


def test_workbench_images_require_ownership_and_public_origin(monkeypatch, tmp_path):
    from test_upload_request import isolated_main
    from starlette.requests import Request
    from app.video_gateway import VideoError
    main = isolated_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "get_media_file", lambda name: {"access_token_hash": "owner", "media_kind": "result", "task_id": "task"})
    monkeypatch.setattr(main, "_authorize_media_access", lambda *args: True)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"host", b"tryon.example.org")], "scheme": "https", "query_string": b"", "server": ("tryon.example.org", 443)})
    url = main._resolve_video_image_url(request, "/assets/result.png")
    assert url.startswith("https://tryon.example.org/api/media/results/result.png?")
    assert "st=" in url
    monkeypatch.setattr(main, "_authorize_media_access", lambda *args: False)
    with pytest.raises(VideoError):
        main._resolve_video_image_url(request, "/uploads/other.png")
    signed = main._issue_result_proxy_url("task", "result.png", "owner")
    assert "st=" in main._resolve_video_image_url(request, signed)
    for value in ("/unknown/image.png", "/uploads/../secret", "data:image/png;base64,abc"):
        with pytest.raises(VideoError):
            main._resolve_video_image_url(request, value)

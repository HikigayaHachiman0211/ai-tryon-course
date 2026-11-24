"""Visitor-scoped video API; paid requests are made once, only on explicit submission."""
import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app import video_gateway as gateway, video_tasks as tasks
from app.task_db import check_and_consume_shared_rate_limit, hash_access_token
from app.video_config import resolve_video_config


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=160)
    provider: str = Field(default="", max_length=80)
    input: dict[str, Any]
    idempotency_key: str = Field(default="", max_length=128)


def build_video_router(*, owner_token, resolve_image):
    router = APIRouter(prefix="/api/video", tags=["tryon-video"])

    async def settings(protected=False):
        try:
            cfg = await run_in_threadpool(resolve_video_config)
        except (ValueError, RuntimeError):
            raise gateway.VideoError(503, "configuration_error", "01Router configuration is invalid")
        if protected and (not cfg.get("enabled") or not cfg.get("api_key")):
            raise gateway.VideoError(503, "not_configured", "Enable video and configure the 01Router API key in administrator settings")
        return cfg

    def owner(request):
        token = owner_token(request)
        if not token:
            raise gateway.VideoError(401, "visitor_required", "Open the video workbench before submitting")
        return hash_access_token(token)

    def failure(exc):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}, headers={"Cache-Control": "private, no-store"})

    @router.get("/config")
    async def config(request: Request):
        try:
            cfg = await settings()
            token = owner_token(request)
            # Establish the same HttpOnly visitor session used by image uploads.
            from app.task_db import generate_access_token, is_production_env
            new_token = not token
            token = token or generate_access_token()
            response = JSONResponse({"enabled": bool(cfg.get("enabled")), "configured": bool(cfg.get("api_key")),
                                     "task_token": token,
                                     "sandbox": "/sandbox/" in cfg["base_url"], "project_id": cfg.get("project_id", ""),
                                     "source": cfg.get("source"), "poll_interval_ms": 4000})
            response.headers["Cache-Control"] = "private, no-store"
            if new_token:
                response.set_cookie("tryon_visitor_token", token, httponly=True, samesite="lax", secure=is_production_env(), max_age=604800)
            return response
        except gateway.VideoError as exc:
            return failure(exc)

    @router.get("/models")
    async def models(refresh: bool = False):
        try:
            cfg = await settings()
            return {"data": await gateway.catalog(cfg, refresh), "project": bool(cfg.get("project_id"))}
        except gateway.VideoError as exc:
            return failure(exc)

    async def prepare(payload, request, cfg):
        if len(json.dumps(payload.input, ensure_ascii=False)) > 200000:
            raise gateway.VideoError(400, "invalid_input", "Video inputs are too large")
        return await gateway.prepare_request(cfg, payload.model, payload.provider, payload.input, lambda value: resolve_image(request, value))

    @router.post("/quote")
    async def quote_video(payload: VideoRequest, request: Request):
        try:
            cfg = await settings()
            body = await prepare(payload, request, cfg)
            return await gateway.gateway_request("POST", "/quote", cfg, body=body)
        except gateway.VideoError as exc:
            return failure(exc)

    @router.post("/tasks")
    async def submit(payload: VideoRequest, request: Request):
        task = None
        try:
            cfg = await settings(protected=True)
            visitor = owner(request)
            if len(payload.idempotency_key) < 4:
                raise gateway.VideoError(400, "idempotency_required", "A unique submission key is required")
            fingerprint = tasks.digest([payload.model, payload.provider, payload.input])
            previous = await run_in_threadpool(tasks.existing_task, visitor, payload.idempotency_key, fingerprint)
            if previous:
                return previous
            body = await prepare(payload, request, cfg)
            task, created = await run_in_threadpool(tasks.reserve_task, visitor, payload.idempotency_key, fingerprint, cfg, payload.model, payload.provider)
            if not created:
                return task
            try:
                await run_in_threadpool(check_and_consume_shared_rate_limit,
                    identity="video:" + tasks.connection_hash(cfg), model_key="video", token_cost=0,
                    limits={"rpm": int(cfg.get("rate_limit_per_minute") or 3), "tpm": 0, "rpd": int(cfg.get("daily_quota_limit") or 20)})
            except RuntimeError as exc:
                raise gateway.VideoError(429, "rate_limited", "Video generation quota reached; try again later") from exc
            data = await gateway.gateway_request("POST", "/generations", cfg, body=body, protected=True)
            if not data.get("id") or data.get("status") not in {"queued", "processing", "succeeded", "failed"}:
                raise gateway.VideoError(502, "submission_unknown", "01Router did not return a valid task receipt")
            return await run_in_threadpool(tasks.save_result, task["id"], data)
        except gateway.VideoError as exc:
            if task:
                result = await run_in_threadpool(tasks.save_result, task["id"], {"status": "unknown" if exc.code == "submission_unknown" else "failed", "error": exc.message, "error_code": exc.code})
                if exc.code == "submission_unknown":
                    return result
            return failure(exc)

    @router.get("/tasks")
    async def history(request: Request):
        try:
            return JSONResponse({"data": await run_in_threadpool(tasks.list_tasks, owner(request))}, headers={"Cache-Control": "private, no-store"})
        except gateway.VideoError as exc:
            return failure(exc)

    @router.get("/submissions/{submission_key}")
    async def receipt(submission_key: str, request: Request):
        try:
            task = await run_in_threadpool(tasks.existing_task, owner(request), submission_key, None)
            if task is None:
                raise gateway.VideoError(404, "task_not_found", "Video submission not found")
            return task
        except gateway.VideoError as exc:
            return failure(exc)

    @router.get("/tasks/{task_id}/download")
    async def download(task_id: str, request: Request, index: int = 0):
        try:
            visitor = hash_access_token(owner_token(request)) if owner_token(request) else ""
            task = await run_in_threadpool(tasks.get_download_task, task_id, visitor, index, request.query_params.get("st", ""))
            outputs = task.get("outputs") or []
            if index < 0 or index >= len(outputs):
                raise gateway.VideoError(404, "result_not_found", "Video result not found")
            return await gateway.download_result(outputs[index], f"tryon-video-{task_id}-{index + 1}.mp4")
        except gateway.VideoError as exc:
            return failure(exc)

    @router.get("/tasks/{task_id}")
    async def poll(task_id: str, request: Request):
        try:
            cfg = await settings(protected=True)
            task = await run_in_threadpool(tasks.get_task, task_id, owner(request), cfg)
            if task["status"] not in {"queued", "processing"} or not task.get("upstream_id"):
                return task
            if not await run_in_threadpool(tasks.claim_poll, task_id):
                return task
            data = await gateway.gateway_request("GET", "/generations/" + quote(task["upstream_id"], safe=""), cfg, protected=True)
            return await run_in_threadpool(tasks.save_result, task_id, data)
        except gateway.VideoError as exc:
            return failure(exc)

    @router.post("/tasks/{task_id}/cancel")
    async def cancel(task_id: str, request: Request):
        try:
            cfg = await settings(protected=True)
            task = await run_in_threadpool(tasks.get_task, task_id, owner(request), cfg)
            if task["status"] in {"failed", "succeeded"}:
                return task
            if not task.get("upstream_id"):
                raise gateway.VideoError(409, "not_cancelable", "The submission has no confirmed upstream ID")
            data = await gateway.gateway_request("POST", "/generations/" + quote(task["upstream_id"], safe="") + "/cancel", cfg, protected=True)
            return await run_in_threadpool(tasks.save_result, task_id, data)
        except gateway.VideoError as exc:
            return failure(exc)

    return router

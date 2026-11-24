"""Independent queue worker entrypoint for Azure Container Apps Event-driven Jobs."""

from __future__ import annotations

import argparse
import asyncio
import base64
import inspect
import json
import os
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional
from zoneinfo import ZoneInfo

import httpx

from app import admin_report as _admin_report
from app.admin_runtime_config import resolve_tryon_runtime_config
from app.object_storage import get_object_storage
from app.task_db import (
    check_and_consume_shared_rate_limit,
    claim_task_for_worker,
    complete_task,
    ensure_task_tables,
    fail_task,
    get_task_record,
    mark_task_unknown,
    mark_upstream_in_flight,
    register_media_file,
    renew_task_lease,
    update_task_progress,
    upsert_task_from_manifest,
)
from app.task_queue import QueueMessage, create_task_queue

SHANGHAI_ZONE = ZoneInfo("Asia/Shanghai")
RESULTS_PREFIX = str(os.environ.get("RESULTS_GCS_PREFIX", "tryon-results") or "tryon-results").strip().strip("/")
TASKS_META_PREFIX = str(os.environ.get("TASKS_META_PREFIX", "tryon-tasks-meta") or "tryon-tasks-meta").strip().strip("/")

# 1x1 transparent PNG bytes used when api_key == "mock" and no demo asset is bundled
_MOCK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class UpstreamResultUnknownError(RuntimeError):
    """Raised when an upstream generation call timed out or its billing/outcome state is unknown."""


def _is_unknown_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (UpstreamResultUnknownError, TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return True
    msg = str(exc).lower()
    return any(token in msg for token in ("timed out", "timeout", "deadline_exceeded", "deadline exceeded", "504"))


def _task_manifest_blob_name(task_id: str) -> str:
    return f"{TASKS_META_PREFIX}/{task_id}.json"


def _load_task_manifest_from_storage(task_id: str, storage: Any) -> Optional[Dict[str, Any]]:
    try:
        raw = storage.download_bytes(_task_manifest_blob_name(task_id))
        if not raw:
            return None
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _download_input_bytes(storage: Any, blob_name: Optional[str], fallback_local_path: str) -> bytes:
    if blob_name:
        data = storage.download_bytes(blob_name)
        if data:
            return data
    if fallback_local_path and os.path.isfile(fallback_local_path):
        with open(fallback_local_path, "rb") as f:
            return f.read()
    raise RuntimeError(f"无法读取输入图片: {blob_name or fallback_local_path}")


async def _lease_renew_loop(
    *,
    task_id: str,
    worker_id: str,
    task_queue: Any,
    msg_holder: Dict[str, QueueMessage],
    lease_seconds: int,
    renew_interval: float,
    stop_event: asyncio.Event,
    db_url: Optional[str] = None,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=renew_interval)
            break
        except asyncio.TimeoutError:
            pass
        try:
            still_owned = renew_task_lease(task_id, worker_id, lease_seconds=lease_seconds, db_url=db_url)
            if not still_owned:
                break
            msg_holder["msg"] = task_queue.renew(msg_holder["msg"], visibility_timeout=lease_seconds)
        except Exception as exc:
            print(f"[QueueWorker] lease/visibility renew failed for {task_id}: {exc}")


async def process_queue_message(
    queue_msg: QueueMessage,
    *,
    worker_id: str,
    task_queue: Any,
    object_storage: Any = None,
    lease_seconds: int = 90,
    renew_interval: float = 25.0,
    db_url: Optional[str] = None,
    generate_fn: Optional[Callable[..., Awaitable[bytes]]] = None,
    runtime_config_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    report_fn: Optional[Callable[..., Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """Process one queue message with DB lease, visibility renewal, and no blind paid retries."""
    storage = object_storage or get_object_storage()
    report = report_fn or _admin_report.report_tryon_task
    task_id = queue_msg.task_id

    existing = get_task_record(task_id, db_url=db_url)
    if existing is None:
        manifest = _load_task_manifest_from_storage(task_id, storage)
        if manifest is not None:
            upsert_task_from_manifest(manifest, db_url=db_url)

    claim = claim_task_for_worker(task_id, worker_id, lease_seconds=lease_seconds, db_url=db_url)
    action = claim["action"]
    task = claim.get("task")

    if action == "not_found":
        return {"status": "not_found", "task_id": task_id, "deleted": False}

    if action == "ack_already_terminal":
        task_queue.delete(queue_msg)
        return {"status": "already_terminal", "task_id": task_id, "task_status": task["status"], "deleted": True}

    if action == "skip_active_lease":
        return {"status": "skipped_active_lease", "task_id": task_id, "deleted": False}

    if action == "marked_unknown":
        await report(
            task_id,
            "unknown",
            locale=task.get("locale", "zh-CN"),
            error_type=task.get("error_code"),
            error_detail=task.get("error_detail"),
            model_used=task.get("model_key", "flash"),
        )
        task_queue.delete(queue_msg)
        return {"status": "marked_unknown", "task_id": task_id, "deleted": True}

    assert task is not None
    msg_holder = {"msg": queue_msg}
    stop_event = asyncio.Event()
    renew_task = asyncio.create_task(
        _lease_renew_loop(
            task_id=task_id,
            worker_id=worker_id,
            task_queue=task_queue,
            msg_holder=msg_holder,
            lease_seconds=lease_seconds,
            renew_interval=renew_interval,
            stop_event=stop_event,
            db_url=db_url,
        )
    )

    import main as workbench_main

    model_key = task.get("model_key") or "flash"
    req_provider = task.get("provider_key")
    req_model_id = task.get("model_id")
    detail_options = task.get("detail_options") or {}
    reported_model = req_model_id or model_key
    locale = task.get("locale") or "zh-CN"
    freedom = workbench_main._normalize_freedom(task.get("freedom"))
    started_at = time.time()
    upstream_dispatched = False

    def _caller_accepts_extended_args(fn) -> bool:
        try:
            sig = inspect.signature(fn)
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                return True
            return {"provider", "model_id", "detail_options"}.issubset(sig.parameters.keys())
        except (TypeError, ValueError):
            return False

    try:
        cfg_resolver = runtime_config_fn or resolve_tryon_runtime_config
        runtime_cfg = cfg_resolver()
        if not runtime_cfg.get("enabled"):
            raise RuntimeError("试衣服务当前已由管理员停用")

        if str(runtime_cfg.get("api_key", "")).strip().lower() == "mock":
            demo_path = os.path.join(workbench_main.ASSET_DIR, "demo_result.png")
            if os.path.isfile(demo_path):
                with open(demo_path, "rb") as f:
                    img_bytes = f.read()
            else:
                img_bytes = _MOCK_PNG_BYTES
        else:
            resolved_upstream = None
            if req_provider or req_model_id or generate_fn is None or runtime_cfg.get("provider_key") == "totokens" or model_key == "chatgpt":
                resolved_upstream = workbench_main._resolve_tryon_generation_config(
                    model_key,
                    provider=req_provider,
                    model_id=req_model_id,
                    detail_options=detail_options,
                    runtime_cfg=runtime_cfg,
                )
                active_key = resolved_upstream.get("api_key")
            else:
                active_key = (
                    runtime_cfg.get("relay_api_key") or runtime_cfg.get("api_key")
                    if model_key == "chatgpt"
                    else runtime_cfg.get("api_key")
                )
            if not active_key:
                raise RuntimeError("试衣服务 API Key 未配置或无法解密，请联系管理员")

            prompt_text = workbench_main._build_prompt(
                task.get("custom_prompt"),
                task.get("prompt_mode") or "append",
                freedom,
                task.get("garment_type"),
            )
            token_cost = workbench_main._estimate_token_cost(prompt_text)
            limits = workbench_main.MODEL_LIMITS.get(model_key, workbench_main.MODEL_LIMITS["flash"])

            update_task_progress(
                task_id,
                worker_id,
                progress=18,
                status="checking_quota",
                message_code="checking_quota",
                db_url=db_url,
            )
            check_and_consume_shared_rate_limit(
                identity=workbench_main._rate_identity(),
                model_key=model_key,
                token_cost=token_cost,
                limits=limits,
                db_url=db_url,
            )

            update_task_progress(
                task_id,
                worker_id,
                progress=25,
                status="processing",
                message_code="processing",
                db_url=db_url,
            )

            with tempfile.TemporaryDirectory(prefix=f"tryon-job-{task_id[:8]}-") as work_dir:
                target_bytes = _download_input_bytes(
                    storage,
                    task.get("input_target_blob"),
                    os.path.join(workbench_main.UPLOAD_DIR, task["target_filename"]),
                )
                ref_bytes = _download_input_bytes(
                    storage,
                    task.get("input_reference_blob"),
                    os.path.join(workbench_main.UPLOAD_DIR, task["reference_filename"]),
                )
                target_ext = workbench_main._validate_and_resolve_image_suffix(target_bytes)
                ref_ext = workbench_main._validate_and_resolve_image_suffix(ref_bytes)
                local_target = os.path.join(work_dir, f"target{target_ext}")
                local_ref = os.path.join(work_dir, f"reference{ref_ext}")
                with open(local_target, "wb") as f:
                    f.write(target_bytes)
                with open(local_ref, "wb") as f:
                    f.write(ref_bytes)

                if not mark_upstream_in_flight(task_id, worker_id, db_url=db_url):
                    raise RuntimeError("Worker lost task lease before upstream generation")
                upstream_dispatched = True

                caller = generate_fn or workbench_main._call_ai_studio_image
                timeout_s = float(
                    (resolved_upstream or {}).get("timeout_seconds")
                    or (runtime_cfg.get("relay_timeout_seconds") if model_key == "chatgpt" else runtime_cfg.get("timeout_seconds"))
                    or 120.0
                )
                call_kwargs: Dict[str, Any] = {
                    "prompt": prompt_text,
                    "model_path": local_target,
                    "garment_path": local_ref,
                    "model_key": model_key,
                }
                if _caller_accepts_extended_args(caller):
                    call_kwargs["provider"] = req_provider
                    call_kwargs["model_id"] = req_model_id
                    call_kwargs["detail_options"] = detail_options
                img_bytes = await asyncio.wait_for(
                    caller(**call_kwargs),
                    timeout=timeout_s + 5.0,
                )

        result_filename = f"generated_{uuid.uuid4().hex}.png"
        date_prefix = datetime.now(SHANGHAI_ZONE).strftime("%Y/%m/%d")
        output_blob = "/".join(part for part in [RESULTS_PREFIX, date_prefix, result_filename] if part)

        storage.upload_bytes(
            output_blob,
            img_bytes,
            content_type="image/png",
            cache_control="no-store, max-age=0",
        )
        local_result_path = os.path.join(workbench_main.ASSET_DIR, result_filename)
        try:
            with open(local_result_path, "wb") as f:
                f.write(img_bytes)
        except OSError:
            pass

        register_media_file(
            filename=result_filename,
            blob_name=output_blob,
            media_kind="result",
            access_token_hash=task["access_token_hash"],
            content_type="image/png",
            task_id=task_id,
            db_url=db_url,
        )
        completed = complete_task(
            task_id,
            worker_id,
            result_filename=result_filename,
            output_result_blob=output_blob,
            freedom=freedom,
            db_url=db_url,
        )
        dur_ms = (time.time() - float(task.get("created_at") or started_at)) * 1000.0
        await report(
            task_id,
            "completed",
            locale=locale,
            result_image_url=f"/api/media/results/{result_filename}",
            duration_ms=dur_ms,
            model_used=reported_model,
        )
        task_queue.delete(msg_holder["msg"])
        return {"status": "completed", "task_id": task_id, "task": completed, "deleted": True}

    except Exception as exc:
        dur_ms = (time.time() - float(task.get("created_at") or started_at)) * 1000.0
        if upstream_dispatched and _is_unknown_timeout_error(exc):
            unknown_task = mark_task_unknown(
                task_id,
                worker_id,
                error_code=type(exc).__name__,
                error_detail=str(exc)[:500],
                db_url=db_url,
            )
            await report(
                task_id,
                "unknown",
                locale=locale,
                error_type=type(exc).__name__,
                error_detail=str(exc)[:500],
                duration_ms=dur_ms,
                model_used=reported_model,
            )
            task_queue.delete(msg_holder["msg"])
            return {"status": "unknown", "task_id": task_id, "task": unknown_task, "deleted": True}

        failed_task = fail_task(
            task_id,
            worker_id,
            error_code=type(exc).__name__,
            error_detail=str(exc)[:500],
            upstream_status="failed_known",
            db_url=db_url,
        )
        await report(
            task_id,
            "failed",
            locale=locale,
            error_type=type(exc).__name__,
            error_detail=str(exc)[:500],
            duration_ms=dur_ms,
            model_used=reported_model,
        )
        task_queue.delete(msg_holder["msg"])
        return {"status": "failed", "task_id": task_id, "task": failed_task, "deleted": True}
    finally:
        stop_event.set()
        try:
            await renew_task
        except Exception:
            pass


async def run_worker_batch(
    *,
    max_messages: int = 5,
    lease_seconds: int = 90,
    renew_interval: float = 25.0,
    worker_id: Optional[str] = None,
    task_queue: Any = None,
    object_storage: Any = None,
    db_url: Optional[str] = None,
    generate_fn: Optional[Callable[..., Awaitable[bytes]]] = None,
) -> int:
    ensure_task_tables(db_url)
    queue = task_queue or create_task_queue()
    storage = object_storage or get_object_storage()
    wid = worker_id or f"worker-{uuid.uuid4().hex[:10]}"
    processed = 0

    while processed < max_messages:
        messages = queue.receive(max_messages=1, visibility_timeout=lease_seconds)
        if not messages:
            break
        for msg in messages:
            await process_queue_message(
                msg,
                worker_id=wid,
                task_queue=queue,
                object_storage=storage,
                lease_seconds=lease_seconds,
                renew_interval=renew_interval,
                db_url=db_url,
                generate_fn=generate_fn,
            )
            processed += 1
            if processed >= max_messages:
                break
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Try-On Queue Worker")
    parser.add_argument("--max-messages", type=int, default=int(os.environ.get("WORKER_MAX_MESSAGES", "5")))
    parser.add_argument("--lease-seconds", type=int, default=int(os.environ.get("WORKER_LEASE_SECONDS", "90")))
    parser.add_argument(
        "--renew-interval",
        type=float,
        default=float(os.environ.get("WORKER_RENEW_INTERVAL_SECONDS") or os.environ.get("WORKER_RENEW_INTERVAL", "25")),
    )
    args = parser.parse_args()

    count = asyncio.run(
        run_worker_batch(
            max_messages=max(1, args.max_messages),
            lease_seconds=max(15, args.lease_seconds),
            renew_interval=max(5.0, args.renew_interval),
        )
    )
    print(f"[QueueWorker] finished batch; processed={count}")


if __name__ == "__main__":
    main()

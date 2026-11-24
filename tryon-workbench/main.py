from fastapi import FastAPI, Form, Request
from fastapi.staticfiles import StaticFiles
from pydantic.fields import FieldInfo
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse, Response

import os
import io
import json
import uuid
import time
import shutil
import zipfile
import base64
import asyncio
import pathlib
import tempfile
import re
import glob
import ipaddress
import socket
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urljoin, unquote, quote, parse_qs
from typing import Optional, List, Dict, Any, Tuple

import PIL.Image
import httpx
from python_multipart.multipart import MultipartParser, parse_options_header
try:
    from google import genai
except ImportError:
    genai = None
from app.object_storage import get_object_storage, load_object_storage_settings
from app.products import load_catalog, list_products, get_filter_options
from app.admin_runtime_config import resolve_tryon_runtime_config, get_tryon_runtime_status
from app.tryon_options import (
    extract_provider_records,
    get_model_capabilities,
    infer_model_protocol,
    infer_preset_key,
    normalize_tryon_options,
    parse_detail_options,
    resolve_totokens_route,
    validate_model_id,
    validate_provider_key,
    validate_totokens_profile_id,
)
from app import admin_report as _admin_report
from app.realtime_routes import router as realtime_router
from app.queue_worker import UpstreamResultUnknownError
from app.task_db import (
    check_and_consume_shared_rate_limit,
    create_or_get_task,
    derive_idempotent_task_id,
    ensure_task_tables,
    generate_access_token,
    get_media_file,
    get_shared_rate_status_snapshot,
    get_task_record,
    hash_access_token,
    issue_short_lived_media_token,
    register_media_file,
    reset_task_for_retry,
    upsert_task_from_manifest,
    verify_short_lived_media_token,
)
from app.task_queue import create_task_queue

SUPPORTED_LOCALES = ("zh-CN", "en", "ja")
DEFAULT_LOCALE = "zh-CN"


def normalize_locale(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw == "zh" or raw.startswith("zh-"):
        return "zh-CN"
    if raw == "en" or raw.startswith("en-"):
        return "en"
    if raw == "ja" or raw.startswith("ja-"):
        return "ja"
    return DEFAULT_LOCALE


def _valid_locale(value: Optional[str]) -> bool:
    raw = str(value or "").strip().lower().replace("_", "-")
    return raw == "zh" or raw.startswith("zh-") or raw == "en" or raw.startswith("en-") or raw == "ja" or raw.startswith("ja-")


def resolve_locale(request: Optional[Request] = None, explicit: Optional[str] = None) -> str:
    if _valid_locale(explicit):
        return normalize_locale(explicit)
    if request is not None:
        query = request.query_params.get("lang") or request.query_params.get("locale")
        if query and _valid_locale(query):
            return normalize_locale(query)
        choices = []
        for order, part in enumerate(request.headers.get("accept-language", "").split(",")):
            pieces = [piece.strip() for piece in part.split(";")]
            quality = 1.0
            for parameter in pieces[1:]:
                if parameter.lower().startswith("q="):
                    try:
                        quality = max(0.0, min(1.0, float(parameter[2:])))
                    except ValueError:
                        quality = 0.0
            if quality > 0 and _valid_locale(pieces[0]):
                choices.append((quality, order, normalize_locale(pieces[0])))
        if choices:
            choices.sort(key=lambda item: (-item[0], item[1]))
            return choices[0][2]
    return DEFAULT_LOCALE


_TASK_MESSAGES = {
    "zh-CN": {"pending": "任务已提交", "queued": "任务已进入队列，等待处理…", "initializing": "任务初始化完成", "checking_quota": "检查额度限制…", "processing": "正在生成图片…", "completed": "生成完成", "failed": "任务失败", "unknown": "上游结果状态未知，已停止自动重试以避免重复扣费"},
    "en": {"pending": "Task submitted", "queued": "Task queued, waiting for worker…", "initializing": "Task initialized", "checking_quota": "Checking quota…", "processing": "Generating image…", "completed": "Generation complete", "failed": "Task failed", "unknown": "Upstream outcome unknown; automatic retry stopped to avoid duplicate billing"},
    "ja": {"pending": "タスクを送信しました", "queued": "タスクはキューに入り、処理待ちです…", "initializing": "タスクを初期化しました", "checking_quota": "利用枠を確認中…", "processing": "画像を生成中…", "completed": "生成が完了しました", "failed": "タスクに失敗しました", "unknown": "上流の結果が不明なため、重複課金を防ぐため自動再試行を停止しました"},
}


def task_message(code: str, locale: str, fallback: str = "") -> str:
    target = normalize_locale(locale)
    messages = _TASK_MESSAGES.get(target, _TASK_MESSAGES[DEFAULT_LOCALE])
    if code in messages:
        return messages[code]
    return fallback if target == DEFAULT_LOCALE and fallback else messages["unknown"]


_ERROR_MESSAGES = {
    "zh-CN": {"validation_error": "请求参数无效", "runtime_unavailable": "试衣服务暂不可用", "rate_limited": "请求过于频繁，请稍后再试", "task_not_found": "任务不存在", "forbidden": "无权访问该任务或媒体资源", "missing_url": "缺少图片地址", "upstream_error": "上游图片服务请求失败", "download_not_found": "图片不存在或内容为空", "download_invalid": "下载参数无效", "download_failed": "图片下载失败", "internal_error": "服务处理失败", "sync_disabled": "生产环境已禁用同步生成，请使用队列异步提交"},
    "en": {"validation_error": "The request parameters are invalid.", "runtime_unavailable": "The try-on service is temporarily unavailable.", "rate_limited": "Too many requests. Please try again later.", "task_not_found": "The task was not found.", "forbidden": "You do not have permission to access this task or media.", "missing_url": "The image URL is required.", "upstream_error": "The upstream image service failed.", "download_not_found": "The image was not found or was empty.", "download_invalid": "The download parameters are invalid.", "download_failed": "The image download failed.", "internal_error": "The service could not complete the request.", "sync_disabled": "Synchronous generation is disabled in production; use /submit-task instead."},
    "ja": {"validation_error": "リクエストパラメータが無効です。", "runtime_unavailable": "試着サービスは一時的に利用できません。", "rate_limited": "リクエストが多すぎます。しばらくしてから再試行してください。", "task_not_found": "タスクが見つかりません。", "forbidden": "このタスクまたはメディアへのアクセス権限がありません。", "missing_url": "画像 URL が必要です。", "upstream_error": "上流の画像サービスに失敗しました。", "download_not_found": "画像が見つからないか、空です。", "download_invalid": "ダウンロードパラメータが無効です。", "download_failed": "画像のダウンロードに失敗しました。", "internal_error": "サービスがリクエストを完了できませんでした。", "sync_disabled": "本番環境では同期生成は無効です。/submit-task を使用してください。"},
}


def error_payload(code: str, locale: str, *, detail: Optional[str] = None) -> dict:
    target = normalize_locale(locale)
    payload = {
        "code": code,
        "message_code": code,
        "locale": target,
        "error": _ERROR_MESSAGES.get(target, _ERROR_MESSAGES[DEFAULT_LOCALE]).get(code, _ERROR_MESSAGES[DEFAULT_LOCALE]["internal_error"]),
    }
    if detail:
        payload["error_detail"] = detail[:500]
    return payload
OBJECT_STORAGE_SETTINGS = load_object_storage_settings()

# Optional GCP clients are imported only for explicit GCS compatibility mode.
# Azure mode must not initialize Firestore or Cloud Storage.
firestore = None
storage = None
if OBJECT_STORAGE_SETTINGS.provider == "gcs":
    try:
        from google.cloud import firestore
        from google.cloud import storage
    except Exception:
        firestore = None
        storage = None


# ===== Project Config =====
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "").strip()
GCP_LOCATION = os.environ.get("GCP_LOCATION", "asia-east1")
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")
RECOMMEND_APP_URL = str(os.environ.get("VITE_RECOMMEND_APP_URL", "") or "").strip()
TRYON_EMBED_MODE = str(os.environ.get("VITE_TRYON_EMBED_MODE", "standalone") or "standalone").strip().lower()
if TRYON_EMBED_MODE not in ("standalone", "embed"):
    TRYON_EMBED_MODE = "standalone"
RESULTS_GCS_BUCKET = str(os.environ.get("RESULTS_GCS_BUCKET", "") or "").strip()
RESULTS_GCS_PREFIX = str(os.environ.get("RESULTS_GCS_PREFIX", "tryon-results") or "tryon-results").strip().strip("/")
UPLOADS_GCS_PREFIX = str(os.environ.get("UPLOADS_GCS_PREFIX", "tryon-uploads") or "tryon-uploads").strip().strip("/")
INTAKE_MAX_IMAGE_BYTES = 15 * 1024 * 1024
# CGNAT (RFC 6598, 100.64.0.0/10) is not flagged as private by ipaddress in Python 3.10
_SSRF_BLOCKED_NETWORKS = [ipaddress.ip_network("100.64.0.0/10")]
IMAGE_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)

MODEL_MAP = {
    "flash": {
        "ids": ["gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"],
        "name": "Gemini Flash Image",
    },
    "pro": {
        "ids": ["gemini-3-pro-image-preview", "gemini-3-pro-image"],
        "name": "Gemini Pro Image",
    },
    "chatgpt": {
        "ids": ["gpt-image-2", "chatgpt-image-latest", "gpt-image-1.5", "gpt-image-1"],
        "name": "ChatGPT Image",
    },
}
DEFAULT_MODEL = "flash"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.txt")

UPLOAD_DIR = os.path.abspath(os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads")))
ASSET_DIR = os.path.abspath(os.environ.get("ASSET_DIR", os.path.join(BASE_DIR, "assets")))
HISTORY_DIR = os.path.abspath(os.environ.get("HISTORY_DIR", os.path.join(BASE_DIR, "history")))
HISTORY_FILES_DIR = os.path.join(HISTORY_DIR, "files")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ASSET_DIR, exist_ok=True)
os.makedirs(HISTORY_FILES_DIR, exist_ok=True)

AI_STUDIO_DOC_LINKS = [
    "https://ai.google.dev/gemini-api/docs/quickstart?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/pricing?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/safety-settings",
]

if OBJECT_STORAGE_SETTINGS.provider == "gcs" and firestore is not None:
    try:
        db = firestore.Client()
        print("[DB] Firestore connected")
    except Exception as e:
        db = None
        print(f"[DB] Firestore unavailable, fallback to memory only: {e}")
else:
    db = None
    print(f"[DB] Optional persistent task store disabled for provider={OBJECT_STORAGE_SETTINGS.provider}; using memory")

if OBJECT_STORAGE_SETTINGS.provider == "gcs" and storage is not None and RESULTS_GCS_BUCKET:
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        print(f"[Storage] GCS connected, bucket={RESULTS_GCS_BUCKET}")
    except Exception as e:
        storage_client = None
        print(f"[Storage] GCS unavailable, fallback to local assets only: {e}")
else:
    storage_client = None


def _rate_identity() -> str:
    """Rate limit identity based on config source, not raw key."""
    return "tryon_config"


# ===== Cleanup =====
TEMP_FILE_MAX_AGE_SECONDS = int(os.environ.get("TEMP_FILE_MAX_AGE_SECONDS", str(12 * 3600)))
TASK_STORE_MAX_ENTRIES = int(os.environ.get("TASK_STORE_MAX_ENTRIES", "500"))
_PENDING_DEDUP: Dict[str, float] = {}  # hash -> timestamp, prevent duplicate submits


def _cleanup_old_files(directory: str, max_age: int) -> int:
    removed = 0
    now = time.time()
    try:
        for fp in glob.glob(os.path.join(directory, "*")):
            if os.path.isfile(fp):
                try:
                    if now - os.path.getmtime(fp) > max_age:
                        os.unlink(fp)
                        removed += 1
                except OSError:
                    pass
    except Exception as e:
        print(f"[Cleanup] {directory}: {e}")
    return removed


def _prune_old_tasks():
    if len(TASKS) <= TASK_STORE_MAX_ENTRIES:
        return
    completed = [(tid, t) for tid, t in TASKS.items() if t.get("status") in ("completed", "failed")]
    completed.sort(key=lambda x: x[1].get("created_at", 0))
    for tid, _ in completed[:len(TASKS) - TASK_STORE_MAX_ENTRIES]:
        del TASKS[tid]


async def _periodic_cleanup():
    while True:
        await asyncio.sleep(3600)
        try:
            for d in [UPLOAD_DIR, ASSET_DIR, HISTORY_FILES_DIR]:
                cnt = _cleanup_old_files(d, TEMP_FILE_MAX_AGE_SECONDS)
                if cnt:
                    print(f"[Cleanup] removed {cnt} files from {os.path.basename(d)}")
            _prune_old_tasks()
            # Prune dedup cache
            now = time.time()
            stale = [k for k, v in _PENDING_DEDUP.items() if now - v > 300]
            for k in stale:
                _PENDING_DEDUP.pop(k, None)
        except Exception as e:
            print(f"[Cleanup] error: {e}")


# ===== App =====
app = FastAPI()
cors_origins = [origin.strip() for origin in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if origin.strip()]
if not cors_origins:
    cors_origins = ["http://127.0.0.1:8080", "http://localhost:8080"]
production_mode = os.environ.get("APP_ENV", "").strip().lower() in {"production", "prod"}
if cors_origins == ["*"] and production_mode:
    raise RuntimeError("CORS_ALLOW_ORIGINS must contain exact origins in production")
allow_all_origins = cors_origins == ["*"] and not production_mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    ensure_task_tables()
    asyncio.create_task(_periodic_cleanup())
    load_catalog()

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/history-files", StaticFiles(directory=HISTORY_FILES_DIR), name="history-files")


_TASK_QUEUE = None
TASKS_META_PREFIX = str(os.environ.get("TASKS_META_PREFIX", "tryon-tasks-meta") or "tryon-tasks-meta").strip().strip("/")


def _get_task_queue():
    global _TASK_QUEUE
    if _TASK_QUEUE is None:
        _TASK_QUEUE = create_task_queue()
    return _TASK_QUEUE


def _is_queue_execution_mode() -> bool:
    mode = str(os.environ.get("TASK_EXECUTION_MODE", "") or "").strip().lower()
    if mode in {"queue", "worker"}:
        return True
    if mode in {"inline", "memory"}:
        return False
    if production_mode:
        return True
    return str(os.environ.get("TASK_QUEUE_PROVIDER", "") or "").strip().lower() == "azure"


def _extract_visitor_token(request: Request) -> str:
    return str(
        request.headers.get("x-task-token")
        or request.query_params.get("token")
        or request.cookies.get("tryon_visitor_token")
        or ""
    ).strip()


def _resolve_or_create_visitor_token(request: Request) -> Tuple[str, bool]:
    existing = _extract_visitor_token(request)
    if existing:
        return existing, False
    return generate_access_token(), True


def _set_visitor_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="tryon_visitor_token",
        value=token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=production_mode,
        path="/",
    )


def _has_valid_ingest_key(request: Request) -> bool:
    expected = str(os.environ.get("INGEST_SECRET_KEY", "") or "").strip()
    provided = str(request.headers.get("x-ingest-key") or "").strip()
    return bool(expected and provided and provided == expected)


def _authorize_media_access(request: Request, filename: str, media_meta: Optional[Dict[str, Any]]) -> bool:
    if _has_valid_ingest_key(request):
        return True
    if media_meta is None:
        return False
    expected_hash = media_meta.get("access_token_hash") or ""
    if not expected_hash:
        return False
    signed_token = str(request.query_params.get("st") or request.query_params.get("mt") or "").strip()
    if signed_token and verify_short_lived_media_token(
        filename, signed_token, expected_access_token_hash=expected_hash
    ):
        return True
    visitor_token = _extract_visitor_token(request)
    if visitor_token and hash_access_token(visitor_token) == expected_hash:
        return True
    return False


def _make_blob_name(prefix: str, filename: str) -> str:
    date_prefix = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y/%m/%d")
    return "/".join(part for part in [prefix, date_prefix, filename] if part)


def _issue_upload_proxy_url(filename: str, access_token_hash: str) -> str:
    mt = issue_short_lived_media_token(filename, access_token_hash)
    return f"/uploads/{quote(filename)}?mt={quote(mt)}"


def _issue_result_proxy_url(task_id: str, filename: str, access_token_hash: str) -> str:
    st = issue_short_lived_media_token(filename, access_token_hash)
    return f"/api/media/results/{quote(filename)}?task_id={quote(task_id)}&st={quote(st)}"


def _resolve_video_image_url(request: Request, value: str) -> str:
    """Refresh private image capabilities before the external video provider reads them."""
    from app.video_gateway import VideoError, public_media_url

    parsed = urlparse(value)
    public_base = str(os.getenv("ROUTER01_MEDIA_BASE_URL", "") or request.base_url).rstrip("/")
    if not os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip() and public_base.startswith("http://"):
        forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        if forwarded_proto == "https":
            public_base = "https://" + public_base[len("http://"):]
    local_hosts = {urlparse(str(request.base_url)).netloc, urlparse(public_base).netloc}
    is_local = not parsed.netloc or parsed.netloc in local_hosts
    if not is_local:
        if not public_media_url(value):
            raise VideoError(400, "invalid_image", "Use a public HTTPS image URL")
        return value
    match = re.fullmatch(r"(?:/mp-tryon)?/(uploads|assets|api/media/results)/([^/]+)", parsed.path)
    if not match:
        raise VideoError(400, "invalid_image", "Choose an uploaded image or a try-on result")
    filename = unquote(match.group(2))
    if filename != os.path.basename(filename) or "\\" in filename or filename in {".", ".."}:
        raise VideoError(400, "invalid_image", "Invalid image filename")
    media = get_media_file(filename)
    source_tokens = parse_qs(parsed.query)
    source_token = (source_tokens.get("st") or source_tokens.get("mt") or [""])[0]
    signed_access = bool(media and verify_short_lived_media_token(filename, source_token, expected_access_token_hash=media.get("access_token_hash")))
    if not signed_access and not _authorize_media_access(request, filename, media):
        raise VideoError(403, "image_forbidden", "You cannot use this image")
    if not public_media_url(public_base + "/"):
        raise VideoError(400, "media_not_public", "01Router needs a publicly reachable workbench URL; configure ROUTER01_MEDIA_BASE_URL or enter a public image URL")
    if match.group(1) == "uploads":
        path = _issue_upload_proxy_url(filename, media["access_token_hash"])
    else:
        path = _issue_result_proxy_url(media.get("task_id") or "", filename, media["access_token_hash"])
    return public_base + path


from app.video_routes import build_video_router
app.include_router(build_video_router(owner_token=_extract_visitor_token, resolve_image=_resolve_video_image_url))
app.include_router(realtime_router)


def _download_media_from_storage(blob_name: Optional[str]) -> Optional[bytes]:
    if not blob_name:
        return None
    try:
        return get_object_storage().download_bytes(blob_name)
    except Exception:
        return None


# ===== Task Store =====
TASKS: Dict[str, Dict[str, Any]] = {}
TASKS_COLLECTION = "generation_tasks"

ERROR_LOGS: List[Dict[str, Any]] = []
KEY_USAGE: Dict[str, Dict[str, Any]] = {}

MODEL_PRICING = {
    "flash": 0.067,
    "pro": 0.134,
    "chatgpt": 0.0,
}

# Model limits aligned with Gemini image model quota panel (RPM / TPM / RPD).
MODEL_LIMITS = {
    "flash": {"rpm": 100, "tpm": 200000, "rpd": 1000},
    "pro": {"rpm": 20, "tpm": 100000, "rpd": 250},
    "chatgpt": {"rpm": 30, "tpm": 120000, "rpd": 300},
}

PT_ZONE = ZoneInfo("America/Los_Angeles")
RATE_LIMIT_STATE: Dict[str, Dict[str, Dict[str, Any]]] = {}
RATE_LIMIT_LOCK = asyncio.Lock()


def _record_key_usage(model_key: str, success: bool):
    """Record model usage stats (no key exposure)."""
    row = KEY_USAGE.get("tryon") or {
        "calls": 0,
        "success": 0,
        "failed": 0,
        "cost": 0.0,
        "last_used": "",
    }
    row["calls"] += 1
    if success:
        row["success"] += 1
    else:
        row["failed"] += 1
    try:
        relay = resolve_tryon_runtime_config().get("provider_key") == "totokens" or model_key == "chatgpt"
    except RuntimeError:
        relay = True  # The provider is unknown, so don't invent a price.
    if relay:
        row["cost"] = None
        row["cost_known"] = False
    elif row["cost"] is not None:
        row["cost"] += float(MODEL_PRICING.get(model_key, MODEL_PRICING["flash"]))
    row["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    KEY_USAGE["tryon"] = row


def _append_error_log(message: str, context: str = "", detail: str = "", analysis: str = "") -> Dict[str, Any]:
    item = {
        "id": f"err_{uuid.uuid4().hex[:12]}",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "message": str(message or "")[:2000],
        "context": str(context or "")[:200],
        "detail": str(detail or "")[:3000],
        "analysis": str(analysis or "")[:6000],
    }
    ERROR_LOGS.insert(0, item)
    if len(ERROR_LOGS) > 500:
        del ERROR_LOGS[500:]
    return item


def _pt_day_key(now_ts: Optional[float] = None) -> str:
    now = datetime.now(PT_ZONE) if now_ts is None else datetime.fromtimestamp(now_ts, tz=PT_ZONE)
    return now.strftime("%Y-%m-%d")


def _seconds_until_next_minute(now_ts: Optional[float] = None) -> int:
    now = datetime.utcnow() if now_ts is None else datetime.utcfromtimestamp(now_ts)
    next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
    return max(0, int((next_minute - now).total_seconds()))


def _seconds_until_next_pt_midnight(now_ts: Optional[float] = None) -> int:
    now = datetime.now(PT_ZONE) if now_ts is None else datetime.fromtimestamp(now_ts, tz=PT_ZONE)
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0, int((next_day - now).total_seconds()))


def _estimate_token_cost(prompt_text: str) -> int:
    # Rough TPM estimate for multimodal image generation request.
    # Keep conservative to avoid quota bursts.
    n = len(prompt_text or "")
    est = 1200 + (n // 3)
    return max(800, min(15000, est))


def _rate_status_snapshot(identity: str, model_key: str) -> Dict[str, Any]:
    limits = MODEL_LIMITS.get(model_key, MODEL_LIMITS[DEFAULT_MODEL])
    snap = get_shared_rate_status_snapshot(identity=identity, model_key=model_key, limits=limits)
    model_name = MODEL_MAP.get(model_key, MODEL_MAP[DEFAULT_MODEL])["name"]
    try:
        runtime = resolve_tryon_runtime_config()
        if model_key == "chatgpt":
            model_name = runtime.get("chatgpt_model") or (runtime.get("pro_model") if runtime.get("provider_key") == "totokens" else "") or model_name
        elif runtime.get("provider_key") == "totokens":
            model_name = runtime.get("flash_model" if model_key == "flash" else "pro_model") or model_name
    except RuntimeError:
        pass
    return {
        "model": model_key,
        "model_name": model_name,
        **snap,
    }


async def _check_and_consume_rate_limit(
    identity: str,
    model_key: str,
    token_cost: int,
) -> Dict[str, Any]:
    limits = MODEL_LIMITS.get(model_key, MODEL_LIMITS[DEFAULT_MODEL])
    check_and_consume_shared_rate_limit(
        identity=identity,
        model_key=model_key,
        token_cost=token_cost,
        limits=limits,
    )
    return _rate_status_snapshot(identity, model_key)


def _normalize_freedom(value: Optional[int]) -> int:
    return max(0, min(10, int(5 if value is None else value)))


def _task_public_payload(task: Optional[dict]) -> dict:
    if not isinstance(task, dict):
        return {}

    logs = task.get("logs", [])
    if not isinstance(logs, list):
        logs = [str(logs)]

    locale = normalize_locale(task.get("locale"))
    message_code = str(task.get("message_code") or "")
    payload = {
        "locale": locale,
        "status": task.get("status", "pending"),
        "status_code": task.get("status", "pending"),
        "message_code": message_code or None,
        "progress": int(task.get("progress", 0) or 0),
        "message": task_message(message_code, locale, str(task.get("message", ""))),
        "result_url": task.get("result_url"),
        "result_cloud_url": task.get("result_cloud_url"),
        "result_display_url": task.get("result_display_url"),
        "result_data_url": task.get("result_data_url"),
        "freedom": _normalize_freedom(task.get("freedom")),
        "logs": [str(x) for x in logs][-500:],
        "error": task.get("error") or (task_message(message_code, locale) if message_code == "failed" else None),
        "error_detail": task.get("error_detail"),
        "error_code": task.get("error_code"),
        "created_at": float(task.get("created_at", 0) or 0),
    }
    if task.get("provider_key"):
        payload["provider"] = task.get("provider_key")
    if task.get("model_id"):
        payload["model_id"] = task.get("model_id")
    if task.get("detail_options"):
        payload["detail_options"] = task.get("detail_options")
    return payload


def _persist_task(task_id: str):
    if db is None:
        return
    task = TASKS.get(task_id)
    if not task:
        return
    try:
        payload = _task_public_payload(task)
        payload["updated_at"] = firestore.SERVER_TIMESTAMP
        db.collection(TASKS_COLLECTION).document(task_id).set(payload, merge=True)
    except Exception as e:
        print(f"[TaskStore] persist failed: {task_id} -> {e}")


def _load_task_from_store(task_id: str) -> Optional[dict]:
    if db is None:
        return None
    try:
        doc = db.collection(TASKS_COLLECTION).document(task_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        updated_at = data.get("updated_at")
        if hasattr(updated_at, "isoformat"):
            data["updated_at"] = updated_at.isoformat()
        return _task_public_payload(data)
    except Exception as e:
        print(f"[TaskStore] load failed: {task_id} -> {e}")
        return None


# ===== Utility =====
FINISH_REASON_MAP = {
    0: "FINISH_REASON_UNSPECIFIED",
    1: "STOP",
    2: "MAX_TOKENS",
    3: "SAFETY",
    4: "RECITATION",
    5: "LANGUAGE",
    6: "OTHER",
    7: "BLOCKLIST",
    8: "PROHIBITED_CONTENT",
    9: "SPII",
    10: "MALFORMED_FUNCTION_CALL",
    11: "IMAGE_SAFETY",
    15: "IMAGE_OTHER",
}


def _finish_reason_desc(reason) -> str:
    try:
        code = int(reason)
        return FINISH_REASON_MAP.get(code, f"UNKNOWN({reason})")
    except Exception:
        return str(reason)


def _read_base_prompt() -> str:
    try:
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    except Exception:
        pass
    return (
        "Generate a high-fidelity virtual try-on image. "
        "Input 1 is the model photo. Input 2 is the garment photo."
    )


def _normalize_garment_type(garment_type: Optional[str]) -> Dict[str, str]:
    raw = str(garment_type or "").strip()
    if not raw:
        return {"label": "", "instruction": "", "category": ""}

    compact = raw.lower().replace(" ", "")
    compact = re.sub(r"[\u3000,，、/／|｜+＋]", "", compact)

    upper_aliases = [
        "上衣", "上装", "衬衫", "衬衣", "t恤", "tshirt", "t-shirt", "tee", "shirt", "blouse",
        "top", "毛衣", "针织衫", "卫衣", "吊带", "背心", "抹胸", "上半身",
    ]
    lower_aliases = [
        "下装", "裤子", "长裤", "短裤", "半身裙", "短裙", "超短裙", "短裤裙", "裙裤", "裙",
        "pants", "trousers", "jeans", "skirt", "mini", "mini-skirt", "shorts",
    ]
    outerwear_aliases = [
        "外套", "夹克", "大衣", "风衣", "开衫", "jacket", "coat", "outerwear", "cardigan", "blazer", "hoodie",
    ]
    dress_aliases = ["连衣裙", "dress", "gown", "onepiece", "one-piece"]
    set_aliases = ["套装", "成套", "两件套", "套裙", "上下套", "套系", "set", "outfit", "twopiece", "twopieces", "two-piece", "twoset"]
    jumpsuit_aliases = ["连体衣", "连体裤", "jumpsuit", "romper", "bodysuit"]

    has_upper = any(alias in compact for alias in upper_aliases)
    has_lower = any(alias in compact for alias in lower_aliases)
    has_outerwear = any(alias in compact for alias in outerwear_aliases)
    has_dress = any(alias in compact for alias in dress_aliases)
    has_set = any(alias in compact for alias in set_aliases)
    has_jumpsuit = any(alias in compact for alias in jumpsuit_aliases)
    has_two_piece_combo = (has_upper or has_outerwear) and has_lower

    safe_label = raw[:40]

    if has_set or has_two_piece_combo:
        return {
            "label": safe_label or "上下套装",
            "category": "set",
            "instruction": (
                "The garment is a coordinated top-and-bottom outfit. This is a hard replacement-scope rule: "
                "replace both the upper-body clothing and the lower-body garment from Input 1 with the matching pieces from Input 2. "
                "Do not keep the original skirt, shorts, pants, or other lower-body clothing from Input 1 visible underneath or mixed into the result. "
                "Preserve the matching relationship, waistline, hem length, color balance, material, lace, trim, and decorative details across both pieces."
            ),
        }

    if has_dress:
        return {
            "label": safe_label or "连衣裙",
            "category": "dress",
            "instruction": (
                "The garment is a one-piece dress. It must cover the upper body and continue naturally through the waist into the lower body as one connected dress. "
                "Do not leave the original lower-body garment from Input 1 visible underneath the dress section."
            ),
        }

    if has_jumpsuit:
        return {
            "label": safe_label or "连体衣",
            "category": "onepiece",
            "instruction": (
                "The garment is a one-piece suit. It should connect continuously through the torso, waist, hips, and lower body as a single garment, "
                "without preserving the original separate lower-body clothing from Input 1."
            ),
        }

    if has_lower:
        return {
            "label": safe_label or "下装",
            "category": "lower",
            "instruction": (
                "The garment is a lower-body item. Keep the upper-body clothing from Input 1 as much as possible and replace only the waist, hips, and legs with the reference garment. "
                "The original lower-body clothing from Input 1 should be removed wherever the reference garment covers it."
            ),
        }

    if has_outerwear:
        return {
            "label": safe_label or "外套",
            "category": "outerwear",
            "instruction": (
                "The garment is outerwear. Layer it over the existing inner clothing when appropriate, keep natural overlap at the collar, sleeves, and front opening, "
                "and do not accidentally convert it into a full dress or bottom piece."
            ),
        }

    if has_upper:
        return {
            "label": safe_label or "上衣",
            "category": "upper",
            "instruction": (
                "The garment is an upper-body item. Wear it on the upper body only, keep the lower body from Input 1 intact, and do not extend it into a dress or add a matching bottom unless Input 2 clearly contains one."
            ),
        }

    return {
        "label": safe_label,
        "category": "custom",
        "instruction": f'Use the user-provided garment type "{safe_label}" as a strong hint when deciding where and how the garment should be worn on the body.',
    }


def _build_prompt(custom_prompt: Optional[str], prompt_mode: str, freedom: int, garment_type: Optional[str] = None) -> str:
    base = _read_base_prompt()
    guide = (
        "\n\n[Core Try-On Rules]:"
        "\n1. Input 1 is the model person photo. Input 2 is the garment reference photo."
        "\n2. Keep the same identity, face geometry, hair, body proportions, pose, camera angle, lighting, and background from Input 1."
        "\n3. Reproduce the exact garment from Input 2 on the person in Input 1."
        "\n4. Preserve garment category, neckline, collar, sleeve length, cuffs, hem, trim, lace, bow, buttons, seams, silhouette, color, and pattern."
        "\n5. Do not convert the garment into a different outfit type."
        "\n6. Do not remove major garment details or expose extra skin that is not implied by the garment itself."
        "\n7. Preserve head size, shoulder width, neck length, chest position, waist placement, arm length, wrist size, and hand anatomy from Input 1."
        "\n8. This is a clothing replacement task, not a face or body redesign task. Avoid beauty-filter effects, doll-like facial changes, or body reshaping."
        "\n9. Keep anatomy, hands, shoulders, and cloth drape natural and physically plausible."
        "\n10. Match the clothing coverage of Input 2 exactly. If Input 2 includes a skirt, shorts, pants, dress section, or any lower-body piece, replace the original lower-body clothing from Input 1 instead of leaving it visible."
        "\n11. If Input 2 is a coordinated two-piece outfit or set, replace both the upper-body and lower-body garments together as one matched outfit."
        "\n12. Never mix the original lower-body garment from Input 1 with a replacement lower-body garment from Input 2 in the same covered area."
        "\n13. Make the result look like a single original photograph, not a collage or pasted overlay."
        "\n14. Match the garment sharpness, blur level, sensor noise, contrast, saturation, white balance, color temperature, and dynamic range to Input 1."
        "\n15. Blend edges at the collar, shoulders, armpits, waist, hips, cuffs, and hem naturally, with no cutout edges, halos, double outlines, or compositing seams."
        "\n16. Keep realistic contact shadows, ambient occlusion, wrinkle transitions, and lighting direction so the clothing integrates naturally with the body and background."
    )

    garment_type_note = ""
    garment_type_meta = _normalize_garment_type(garment_type)
    if garment_type_meta["instruction"]:
        garment_type_note = (
            "\n\n[Garment Type Hint - Strong Scope Rule]: "
            f'The user marked the garment type as "{garment_type_meta["label"]}". '
            f'{garment_type_meta["instruction"]}'
        )

    prompt = base + guide + garment_type_note
    cp = (custom_prompt or "").strip()
    if cp:
        if (prompt_mode or "append") == "override":
            prompt = (
                base
                + guide
                + garment_type_note
                + "\n\n[User Preference]: Apply the following additional styling request only if it does not break the core try-on rules above.\n"
                + cp
            )
        else:
            prompt = (
                prompt
                + "\n\n[User Preference]: Apply the following request only if it keeps the same identity and the same garment structure.\n"
                + cp
            )

    freedom = max(0, min(10, int(freedom)))
    if freedom <= 3:
        freedom_note = (
            "Favor maximum garment fidelity. Stay very close to the exact product photo and avoid creative redesign."
        )
    elif freedom <= 7:
        freedom_note = (
            "Balance garment fidelity with flattering realism, but never alter garment category or key structural details."
        )
    else:
        freedom_note = (
            "Allow limited aesthetic enhancement, while still preserving identity and the exact garment structure."
        )
    prompt += f"\n\n[FREEDOM LEVEL: {freedom}/10] {freedom_note}"
    return prompt


def _public_gcs_url(bucket: str, blob_name: str) -> str:
    return f"https://storage.googleapis.com/{bucket}/{quote(blob_name, safe='/')}"


def _upload_bytes_to_gcs(img_bytes: bytes, filename: str, prefix: str, content_type: str = "image/png") -> Optional[str]:
    """Upload media through the selected adapter (legacy name retained)."""

    date_prefix = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y/%m/%d")
    blob_name = "/".join(part for part in [prefix, date_prefix, filename] if part)
    try:
        return get_object_storage().upload_bytes(
            blob_name,
            img_bytes,
            content_type=content_type,
            cache_control="no-store, max-age=0",
        )
    except Exception as e:
        print(f"[Storage] upload failed ({prefix}/{filename}): {type(e).__name__}")
        return None


def _upload_generated_bytes_to_gcs(img_bytes: bytes, filename: str) -> Optional[str]:
    return _upload_bytes_to_gcs(img_bytes, filename, RESULTS_GCS_PREFIX, "image/png")


def _content_type_from_ext(ext: str) -> str:
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
        ext.lstrip(".").lower(), "image/png"
    )


def _save_generated_bytes(img_bytes: bytes, *, access_token_hash: str = "", task_id: Optional[str] = None) -> Dict[str, Any]:
    filename = f"generated_{uuid.uuid4().hex}.png"
    path = os.path.join(ASSET_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    blob_name = _make_blob_name(RESULTS_GCS_PREFIX, filename)
    try:
        get_object_storage().upload_bytes(
            blob_name,
            img_bytes,
            content_type="image/png",
            cache_control="no-store, max-age=0",
        )
    except Exception as e:
        print(f"[Storage] upload failed ({RESULTS_GCS_PREFIX}/{filename}): {type(e).__name__}")
        blob_name = None
    if access_token_hash and blob_name:
        register_media_file(
            filename=filename,
            blob_name=blob_name,
            media_kind="result",
            access_token_hash=access_token_hash,
            content_type="image/png",
            task_id=task_id,
        )
        display_url = _issue_result_proxy_url(task_id or "inline", filename, access_token_hash)
    else:
        display_url = f"/assets/{filename}"
    return {
        "filename": filename,
        "blob_name": blob_name,
        "result_url": display_url,
        "result_cloud_url": display_url if blob_name else None,
        "result_display_url": display_url,
        "result_data_url": None,
    }


def _build_direct_generate_config(
    detail_options: Optional[Dict[str, Any]] = None,
    model_id: Optional[str] = None,
):
    from google.genai import types as genai_types

    opts = dict(detail_options or {})
    config_kwargs: Dict[str, Any] = {
        "safety_settings": [
            genai_types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            genai_types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            genai_types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            genai_types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        ],
        "response_modalities": ["TEXT", "IMAGE"],
    }
    if opts.get("temperature") is not None:
        config_kwargs["temperature"] = float(opts["temperature"])
    if opts.get("seed") is not None:
        config_kwargs["seed"] = int(opts["seed"])

    image_cfg_kwargs: Dict[str, Any] = {}
    aspect_ratio = str(opts.get("aspect_ratio") or "").strip()
    if aspect_ratio and aspect_ratio.lower() != "auto":
        image_cfg_kwargs["aspect_ratio"] = aspect_ratio
    image_size = str(opts.get("image_size") or "").strip().upper()
    if image_size and image_size != "AUTO":
        caps = get_model_capabilities("gemini", model_id or "")
        if caps.get("supports_image_size", True):
            image_cfg_kwargs["image_size"] = image_size
    if image_cfg_kwargs:
        config_kwargs["image_config"] = genai_types.ImageConfig(**image_cfg_kwargs)

    return genai_types.GenerateContentConfig(**config_kwargs)


def _extract_error_status_text(error: Exception) -> str:
    raw = " ".join(str(error or "").split())
    match = re.search(r"'status':\s*'([^']+)'", raw)
    if match:
        return match.group(1).strip()
    match = re.search(r'"status":\s*"([^"]+)"', raw)
    if match:
        return match.group(1).strip()
    return ""


def _summarize_direct_generation_error(error: Exception) -> str:
    raw = " ".join(str(error or "").split())
    lower = raw.lower()

    if "consumer_invalid" in lower or ("permission_denied" in lower and "aiplatform.googleapis.com" in lower):
        return (
            "Google AI Studio / Gemini API 返回权限或项目配置错误。请检查：\n"
            "1. API Key 是否属于当前项目；\n"
            "2. Gemini API 是否已启用；\n"
            "3. 当前 Key 是否有可用配额和账单；\n"
            "4. 模型 ID 是否支持当前接口。"
        )
    if "permission_denied" in lower or "403" in lower:
        return "Google AI Studio 返回了 HTTP 403。请检查 API Key 是否有效、Gemini API 是否已启用。"
    if "resource_exhausted" in lower or "429" in lower or "quota" in lower or "rate" in lower:
        return "Google AI Studio 触发了配额或限流。请稍后重试，或检查 API Key 配额。"
    if "api key not valid" in lower or "invalid api key" in lower:
        return "Google AI Studio 拒绝了当前 API 密钥。请确认密钥有效且属于当前项目。"
    if "returned empty parts" in lower or "does not contain image bytes" in lower:
        return "Google AI Studio 已返回响应，但没有生成可用的图片数据。"

    status_text = _extract_error_status_text(error)
    if status_text:
        return f"Google AI Studio 请求失败，状态为 {status_text}：{raw[:420]}"
    return f"Google AI Studio 请求失败：{raw[:420]}"

def _extract_image_bytes_from_genai_response(response) -> bytes:
    parts = getattr(response, "parts", None)
    if not parts:
        reason = None
        if getattr(response, "candidates", None):
            cand = response.candidates[0]
            reason = _finish_reason_desc(getattr(cand, "finish_reason", None))
        raise RuntimeError(f"Google AI Studio 返回了空的 parts，finish_reason={reason}")

    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "mime_type", "").startswith("image/"):
            data = inline.data
            if data and len(data) > 80:
                return data

    if hasattr(response, "images") and response.images:
        buf = io.BytesIO()
        response.images[0].save(buf, format="PNG")
        data = buf.getvalue()
        if data:
            return data

    raise RuntimeError("Google AI Studio response does not contain image bytes")


def _resolve_tryon_generation_config(
    model_key: str = DEFAULT_MODEL,
    *,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    detail_options: Optional[Dict[str, Any]] = None,
    runtime_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve generation config from admin DB via runtime config module."""
    try:
        config = runtime_cfg if runtime_cfg is not None else resolve_tryon_runtime_config()
    except RuntimeError as exc:
        raise RuntimeError(str(exc))

    if not config.get("enabled"):
        raise RuntimeError("试衣服务当前已由管理员停用")

    req_provider = validate_provider_key(provider)
    req_model_id = validate_model_id(model_id)

    if req_provider or req_model_id:
        provider_records = extract_provider_records(config)
        primary_provider = str(config.get("provider_key") or "gemini").strip().lower()
        if primary_provider not in ("gemini", "totokens"):
            primary_provider = "gemini"

        if req_provider:
            chosen_provider = req_provider
        elif model_key == "chatgpt" or (
            req_model_id and ("gpt" in req_model_id.lower() or "chatgpt" in req_model_id.lower())
        ):
            chosen_provider = "totokens"
        else:
            chosen_provider = primary_provider

        if (
            chosen_provider == "gemini"
            and req_model_id
            and ("gpt" in req_model_id.lower() or "chatgpt" in req_model_id.lower())
        ):
            raise ValueError("Google Gemini 直连通道不支持 GPT 图像模型，请切换到 ToTokens 中转站")

        rec = provider_records.get(chosen_provider) or {}
        if not rec.get("enabled"):
            label = "ToTokens 中转站" if chosen_provider == "totokens" else "Google Gemini 直连"
            raise RuntimeError(f"{label}当前已由管理员停用，请先在后台启用")

        if req_model_id:
            resolved_model_ids = [req_model_id]
        elif chosen_provider == "totokens":
            fallback_id = (
                config.get("chatgpt_model")
                if model_key == "chatgpt"
                else config.get("pro_model")
                if (model_key == "pro" and primary_provider == "totokens")
                else config.get("flash_model")
                if (model_key == "flash" and primary_provider == "totokens")
                else rec.get("default_model")
            ) or "gpt-image-2"
            resolved_model_ids = [str(fallback_id).strip()]
        else:
            if model_key == "pro":
                cand = config.get("pro_model") if primary_provider == "gemini" else ""
                resolved_model_ids = [cand] if cand else []
            else:
                cand = config.get("flash_model") if primary_provider == "gemini" else ""
                resolved_model_ids = [cand] if cand else []
            for fallback_id in MODEL_MAP.get(model_key, {}).get("ids") or []:
                if fallback_id and fallback_id not in resolved_model_ids:
                    resolved_model_ids.append(fallback_id)

        cleaned_ids = [item for item in resolved_model_ids if item]
        if chosen_provider == "totokens":
            route = resolve_totokens_route(
                config,
                model_id=cleaned_ids[0] if cleaned_ids else "",
                model_key=model_key,
                detail_options=detail_options,
            )
            return {
                "api_key": route["api_key"],
                "model_ids": cleaned_ids,
                "provider_key": "totokens",
                "base_url": route["base_url"],
                "timeout_seconds": route["timeout_seconds"],
                "totokens_profile_id": route["profile_id"],
                "effective_detail_options": route["effective_detail_options"],
            }

        if not rec.get("api_key"):
            raise RuntimeError("Google Gemini API Key 未配置，请联系管理员在后台设置")

        return {
            "api_key": rec["api_key"],
            "model_ids": cleaned_ids,
            "provider_key": chosen_provider,
            "base_url": rec.get("base_url") or "",
            "timeout_seconds": rec.get("timeout_seconds") or 120,
        }

    if model_key == "chatgpt":
        if "relay_enabled" in config and not config.get("relay_enabled"):
            raise RuntimeError("中转站服务当前已由管理员停用，请先启用 ToTokens Provider")
        chatgpt_model = str(
            config.get("chatgpt_model")
            or (config.get("pro_model") if config.get("provider_key") == "totokens" else "")
            or "gpt-image-2"
        ).strip()
        route = resolve_totokens_route(
            config,
            model_id=chatgpt_model,
            model_key="chatgpt",
            detail_options=detail_options,
        )
        return {
            "api_key": route["api_key"],
            "model_ids": [chatgpt_model],
            "provider_key": "totokens",
            "base_url": route["base_url"],
            "timeout_seconds": route["timeout_seconds"],
            "totokens_profile_id": route["profile_id"],
            "effective_detail_options": route["effective_detail_options"],
        }

    flash_model = config.get("flash_model", "")
    pro_model = config.get("pro_model", "")

    if model_key == "flash":
        model_ids = [flash_model] if flash_model else []
    else:
        model_ids = [pro_model] if pro_model else []

    if config.get("provider_key") == "totokens":
        cleaned_ids = [item for item in model_ids if item]
        route = resolve_totokens_route(
            config,
            model_id=cleaned_ids[0] if cleaned_ids else "",
            model_key=model_key,
            detail_options=detail_options,
        )
        return {
            "api_key": route["api_key"],
            "model_ids": cleaned_ids,
            "provider_key": "totokens",
            "base_url": route["base_url"],
            "timeout_seconds": route["timeout_seconds"],
            "totokens_profile_id": route["profile_id"],
            "effective_detail_options": route["effective_detail_options"],
        }

    api_key = config.get("api_key", "")
    if not api_key:
        raise RuntimeError("试衣服务 API Key 未配置，请联系管理员")

    # A relay request must not silently fall back to another billable model.
    for model_id in MODEL_MAP.get(model_key, {}).get("ids") or []:
        if model_id and model_id not in model_ids:
            model_ids.append(model_id)

    return {
        "api_key": api_key,
        "model_ids": [item for item in model_ids if item],
        "provider_key": config.get("provider_key", "gemini"),
        "base_url": config.get("base_url", ""),
        "timeout_seconds": config.get("timeout_seconds", 120),
    }


def _validate_model_key(model: Optional[str]) -> str:
    value = str(model or DEFAULT_MODEL).strip().lower()
    if value not in MODEL_MAP:
        raise ValueError("不支持的模型类型，仅允许 flash、pro 或 chatgpt")
    return value


def _unwrap_form(value: Any) -> Any:
    return value.default if isinstance(value, FieldInfo) else value


def _prepare_tryon_submission(
    *,
    model: Optional[str],
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    aspect_ratio: Any = None,
    image_size: Any = None,
    quality: Any = None,
    temperature: Any = None,
    seed: Any = None,
    totokens_profile: Any = None,
    runtime_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    req_provider = validate_provider_key(_unwrap_form(provider))
    req_model_id = validate_model_id(_unwrap_form(model_id))
    raw_model = _unwrap_form(model)
    if raw_model is None or str(raw_model).strip() == "":
        model_key = infer_preset_key(req_model_id)
    else:
        model_key = _validate_model_key(raw_model)

    # First pass validates bounds/enums for all provided fields cleanly.
    raw_options = normalize_tryon_options(
        aspect_ratio=_unwrap_form(aspect_ratio),
        image_size=_unwrap_form(image_size),
        quality=_unwrap_form(quality),
        temperature=_unwrap_form(temperature),
        seed=_unwrap_form(seed),
        totokens_profile=_unwrap_form(totokens_profile),
    )

    cfg = runtime_cfg if runtime_cfg is not None else _require_tryon_runtime_config()
    is_mock = str((cfg or {}).get("api_key", "")).strip().lower() == "mock"
    effective_provider = req_provider or str((cfg or {}).get("provider_key") or "gemini").strip().lower()
    effective_model_id = req_model_id or ""
    if not is_mock:
        resolved = _resolve_tryon_generation_config(
            model_key,
            provider=req_provider,
            model_id=req_model_id,
            detail_options=raw_options,
            runtime_cfg=cfg,
        )
        effective_provider = str(resolved.get("provider_key") or effective_provider or "gemini")
        model_ids = resolved.get("model_ids") or []
        effective_model_id = str(req_model_id or (model_ids[0] if model_ids else "")).strip()

    effective_protocol = infer_model_protocol(effective_provider, effective_model_id)
    detail_options = normalize_tryon_options(
        aspect_ratio=raw_options.get("aspect_ratio"),
        image_size=raw_options.get("image_size"),
        quality=raw_options.get("quality"),
        temperature=raw_options.get("temperature"),
        seed=raw_options.get("seed"),
        totokens_profile=raw_options.get("totokens_profile") if effective_provider == "totokens" else None,
        protocol=effective_protocol,
        model_id=effective_model_id,
    )
    return {
        "model_key": model_key,
        "provider_key": req_provider,
        "model_id": req_model_id,
        "effective_provider": effective_provider,
        "effective_model_id": effective_model_id,
        "detail_options": detail_options,
        "runtime_cfg": cfg,
    }


def _require_tryon_runtime_config() -> Dict[str, Any]:
    try:
        config = resolve_tryon_runtime_config()
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc
    if not config.get("enabled"):
        raise RuntimeError("试衣服务当前已由管理员停用")
    has_profile_key = any(
        bool(p.get("enabled") and p.get("api_key"))
        for p in (config.get("totokens_apis_internal") or [])
        if isinstance(p, dict)
    )
    if not (config.get("api_key") or config.get("relay_api_key") or has_profile_key):
        raise RuntimeError("试衣服务 API Key 未配置或无法解密，请联系管理员")
    return config




async def _call_ai_studio_image(
    prompt: str,
    model_path: str,
    garment_path: str,
    model_key: str,
    *,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    detail_options: Optional[Dict[str, Any]] = None,
) -> bytes:
    resolved = _resolve_tryon_generation_config(
        model_key,
        provider=provider,
        model_id=model_id,
        detail_options=detail_options,
    )
    request_key = resolved["api_key"]
    effective_opts = resolved.get("effective_detail_options") or detail_options
    model_ids = list(resolved.get("model_ids") or [])
    if not model_ids:
        raise RuntimeError(f"AI Studio 模型配置缺少 model_key={model_key} 对应的模型 ID")

    timeout_seconds = float(resolved.get("timeout_seconds") or 120.0)
    if resolved["provider_key"] == "totokens":
        from app.totokens_image import generate_image

        try:
            return await generate_image(
                base_url=resolved["base_url"], api_key=request_key,
                model_id=model_ids[0], model_key=model_key, prompt=prompt,
                model_path=model_path, garment_path=garment_path,
                timeout_seconds=timeout_seconds,
                fetch_remote_image=_fetch_remote_image_bytes,
                generation_options=effective_opts,
            )
        except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise UpstreamResultUnknownError("上游中转生图请求超时，结果状态未知，已停止自动重试") from exc

    client = genai.Client(api_key=request_key)
    img_model = PIL.Image.open(model_path)
    img_garment = PIL.Image.open(garment_path)
    request_contents = [prompt, img_model, img_garment]

    loop = asyncio.get_event_loop()
    primary_model = model_ids[0]
    config = _build_direct_generate_config(detail_options=detail_options, model_id=primary_model)

    # Execute a single upstream call without blind automatic retries on unknown outcomes.
    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda current_model=primary_model: client.models.generate_content(
                    model=current_model,
                    contents=request_contents,
                    config=config,
                ),
            ),
            timeout=timeout_seconds,
        )
        return _extract_image_bytes_from_genai_response(response)
    except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException) as exc:
        raise UpstreamResultUnknownError("Google AI Studio 生图请求超时，结果状态未知，已停止自动重试") from exc
    except Exception as e:
        err_lower = str(e).lower()
        if any(tok in err_lower for tok in ("timed out", "timeout", "deadline_exceeded", "deadline exceeded", "504")):
            raise UpstreamResultUnknownError(f"上游生图请求超时，结果状态未知：{str(e)[:300]}") from e
        raise RuntimeError(_summarize_direct_generation_error(e))


async def _ensure_local_file(filename: str, cloud_url: Optional[str]) -> str:
    """Ensure a file exists locally in UPLOAD_DIR; download from private storage or cloud_url if missing."""
    local_path = _safe_media_path(UPLOAD_DIR, filename)
    if os.path.exists(local_path):
        return local_path
    media_lookup = globals().get("get_media_file")
    storage_getter = globals().get("get_object_storage")
    if callable(media_lookup) and callable(storage_getter):
        meta = media_lookup(filename)
        if meta and meta.get("blob_name"):
            blob_bytes = storage_getter().download_bytes(meta["blob_name"])
            if blob_bytes:
                _validate_and_resolve_image_suffix(blob_bytes)
                with open(local_path, "wb") as f:
                    f.write(blob_bytes)
                return local_path
    url = str(cloud_url or "").strip()
    if not url:
        return local_path  # caller will detect missing file
    data = None
    for source_path in _extract_local_candidates(url):
        if os.path.isfile(source_path):
            with open(source_path, "rb") as source:
                data = source.read(INTAKE_MAX_IMAGE_BYTES + 1)
            break
    if data is None:
        data, _ = await _fetch_remote_image_bytes(url)
    _validate_and_resolve_image_suffix(data)
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path


async def _generate_tryon_image_bytes(
    model_filename: str,
    garment_filename: str,
    custom_prompt: Optional[str],
    prompt_mode: str,
    freedom: int,
    garment_type: Optional[str],
    model_key: str,
    model_cloud_url: Optional[str] = None,
    garment_cloud_url: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    detail_options: Optional[Dict[str, Any]] = None,
) -> bytes:
    model_path = await _ensure_local_file(model_filename, model_cloud_url)
    garment_path = await _ensure_local_file(garment_filename, garment_cloud_url)
    if not os.path.exists(model_path):
        raise RuntimeError(f"未找到模特图片：{model_filename}")
    if not os.path.exists(garment_path):
        raise RuntimeError(f"未找到服装图片：{garment_filename}")

    prompt = _build_prompt(custom_prompt, prompt_mode or "append", freedom, garment_type)

    return await _call_ai_studio_image(
        prompt=prompt,
        model_path=model_path,
        garment_path=garment_path,
        model_key=model_key,
        provider=provider,
        model_id=model_id,
        detail_options=detail_options,
    )


def _validate_single_model(target_image: List[str]):
    if not target_image:
        raise ValueError("请上传 1 张模特图片")
    if len(target_image) != 1:
        raise ValueError(f"模特图片数量必须为 1 张，当前为 {len(target_image)} 张")


async def _process_task(
    task_id: str,
    target_image: List[str],
    reference_image: str,
    custom_prompt: Optional[str],
    prompt_mode: Optional[str],
    freedom: Optional[int],
    garment_type: Optional[str],
    model: Optional[str],
    target_image_cloud_url: Optional[str] = None,
    reference_image_cloud_url: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    detail_options: Optional[Dict[str, Any]] = None,
):
    task = TASKS[task_id]
    model_key = _validate_model_key(model)
    reported_model = model_id or model_key

    def update(progress: Optional[int] = None, message: Optional[str] = None, status: Optional[str] = None, code: Optional[str] = None):
        if progress is not None:
            task["progress"] = int(progress)
        if message is not None:
            task["message"] = str(message)
            task["logs"].append(str(message))
        if code is not None:
            task["message_code"] = code
        if status is not None:
            task["status"] = status
        _persist_task(task_id)

    try:
        update(5, status="processing", code="initializing")
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")

        # Check runtime config availability
        try:
            runtime_cfg = resolve_tryon_runtime_config()
        except RuntimeError as exc:
            raise RuntimeError(str(exc))

        if not runtime_cfg.get("enabled"):
            raise RuntimeError("试衣服务当前已由管理员停用")

        if runtime_cfg.get("api_key", "").lower() == "mock":
            task["status"] = "completed"
            task["progress"] = 100
            task["message_code"] = "completed"
            task["message"] = task_message("completed", task.get("locale", DEFAULT_LOCALE))
            task["result_url"] = "/assets/demo_result.png"
            _persist_task(task_id)
            return

        freedom_level = _normalize_freedom(freedom)
        prompt_text = _build_prompt(custom_prompt, prompt_mode or "append", freedom_level, garment_type)
        rate_identity = _rate_identity()
        token_cost = _estimate_token_cost(prompt_text)

        update(18, status="checking_quota", code="checking_quota")
        await _check_and_consume_rate_limit(
            identity=rate_identity,
            model_key=model_key,
            token_cost=token_cost,
        )

        update(25, status="processing", code="processing")
        img_bytes = await _generate_tryon_image_bytes(
            model_filename=target_image[0],
            garment_filename=reference_image,
            custom_prompt=custom_prompt,
            prompt_mode=prompt_mode or "append",
            freedom=freedom_level,
            garment_type=garment_type,
            model_key=model_key,
            model_cloud_url=target_image_cloud_url,
            garment_cloud_url=reference_image_cloud_url,
            provider=provider,
            model_id=model_id,
            detail_options=detail_options,
        )

        out = _save_generated_bytes(img_bytes)
        task["status"] = "completed"
        task["progress"] = 100
        task["message_code"] = "completed"
        task["message"] = task_message("completed", task.get("locale", DEFAULT_LOCALE))
        task["result_url"] = out["result_url"]
        task["result_cloud_url"] = out.get("result_cloud_url")
        task["result_display_url"] = out.get("result_display_url")
        task["result_data_url"] = out["result_data_url"]
        task["freedom"] = freedom_level
        _record_key_usage(model_key, True)
        _persist_task(task_id)
        _dur = (time.time() - float(task.get("created_at") or 0)) * 1000
        # Await (not fire-and-forget): a bare create_task here is dropped under
        # Cloud Run CPU throttling after the response returns, so the admin
        # dashboard never received completed try-on tasks. report_tryon_task is
        # self-contained (own timeout + try/except) so awaiting cannot raise.
        await _admin_report.report_tryon_task(
            task_id, "completed",
            locale=task.get("locale", DEFAULT_LOCALE),
            result_image_url=out.get("result_cloud_url") or out.get("result_display_url") or "",
            duration_ms=_dur,
            model_used=reported_model,
        )

    except Exception as e:
        task["status"] = "failed"
        task["progress"] = 0
        task["message_code"] = "failed"
        task["message"] = task_message("failed", task.get("locale", DEFAULT_LOCALE))
        task["error"] = task_message("failed", task.get("locale", DEFAULT_LOCALE))
        task["error_detail"] = str(e)[:500]
        task["error_code"] = type(e).__name__
        task["logs"].append(f"Error: {e}")
        _record_key_usage(model_key, False)
        _append_error_log(str(e), context="generation_task", detail=f"task_id={task_id}")
        _persist_task(task_id)
        _dur = (time.time() - float(task.get("created_at") or 0)) * 1000
        # Await for the same reason as the completed branch above.
        await _admin_report.report_tryon_task(
            task_id, "failed",
            locale=task.get("locale", DEFAULT_LOCALE),
            error_type=type(e).__name__,
            error_detail=str(e)[:500],
            duration_ms=_dur,
            model_used=reported_model,
        )


@app.get("/")
async def read_root(request: Request):
    import asyncio
    asyncio.create_task(_admin_report.report_page_view(
        source="tryon_workbench",
        page="/",
        user_agent=request.headers.get("user-agent", ""),
        ip=request.client.host if request.client else "",
    ))
    target = "/static/index.html"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "model-tryon-generator",
        "version": "3.1.0",
    }


@app.get("/health/deep")
async def health_deep():
    """Verify PostgreSQL, object storage, and Azure Storage Queue readiness."""
    checks: dict[str, Any] = {}
    ok = True

    try:
        from sqlalchemy import text
        from app.task_db import get_session_factory

        session_factory, _ = get_session_factory()
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        ok = False
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    try:
        storage_status = get_object_storage().health_check()
        checks["object_storage"] = storage_status
        if isinstance(storage_status, dict) and storage_status.get("ok") is False:
            ok = False
    except Exception as exc:
        ok = False
        checks["object_storage"] = {"ok": False, "error": type(exc).__name__}

    try:
        queue_status = _get_task_queue().health_check()
        checks["task_queue"] = {"ok": True, **queue_status} if isinstance(queue_status, dict) else {"ok": True}
    except Exception as exc:
        ok = False
        checks["task_queue"] = {"ok": False, "error": type(exc).__name__}

    try:
        checks["ai_runtime"] = get_tryon_runtime_status()
    except Exception as exc:
        checks["ai_runtime"] = {"ok": False, "error": type(exc).__name__}

    try:
        from app import realtime_budget

        checks["realtime_tryon"] = realtime_budget.diagnose_settings()
        checks["realtime_tryon_xmax"] = realtime_budget.diagnose_xmax_settings()
        checks["realtime_tryon_reactor"] = realtime_budget.diagnose_reactor_settings()
    except Exception as exc:
        checks["realtime_tryon"] = {"enabled": False, "available": False, "error": type(exc).__name__}
        checks["realtime_tryon_xmax"] = {"enabled": False, "available": False, "error": type(exc).__name__}
        checks["realtime_tryon_reactor"] = {"enabled": False, "available": False, "error": type(exc).__name__}

    return JSONResponse(
        {"status": "healthy" if ok else "unhealthy", "service": "model-tryon-generator", "checks": checks},
        status_code=200 if ok else 503,
    )


@app.get("/api/products")
async def api_products(
    request: Request,
    query: Optional[str] = None,
    gender: Optional[str] = None,
    platform: Optional[str] = None,
    style_type: Optional[str] = None,
    color: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    offset: int = 0,
    limit: int = 60,
    locale: Optional[str] = None,
):
    target_locale = resolve_locale(request, locale)
    return list_products(
        query=query, gender=gender, platform=platform,
        style_type=style_type, color=color,
        price_min=price_min, price_max=price_max,
        offset=offset, limit=limit, locale=target_locale,
    )


@app.get("/api/products/filters")
async def api_product_filters(request: Request, locale: Optional[str] = None):
    return get_filter_options(resolve_locale(request, locale))


@app.get("/uploads/{filename}")
async def serve_private_upload(filename: str, request: Request):
    try:
        local_path = _safe_media_path(UPLOAD_DIR, filename)
    except ValueError:
        return JSONResponse(status_code=400, content=error_payload("validation_error", resolve_locale(request)))
    media_meta = get_media_file(filename)
    if media_meta is not None:
        if not _authorize_media_access(request, filename, media_meta):
            return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
    elif production_mode or OBJECT_STORAGE_SETTINGS.provider == "azure":
        return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))

    data: Optional[bytes] = None
    if os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            data = f.read()
    elif media_meta and media_meta.get("blob_name"):
        data = _download_media_from_storage(media_meta["blob_name"])
    if not data:
        return JSONResponse(status_code=404, content=error_payload("download_not_found", resolve_locale(request)))
    content_type = (media_meta or {}).get("content_type") or _content_type_from_ext(os.path.splitext(filename)[1])
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, no-store"})


@app.get("/assets/{filename}")
async def serve_private_asset(filename: str, request: Request):
    try:
        local_path = _safe_media_path(ASSET_DIR, filename)
    except ValueError:
        return JSONResponse(status_code=400, content=error_payload("validation_error", resolve_locale(request)))
    if filename != "demo_result.png":
        media_meta = get_media_file(filename)
        if media_meta is not None:
            if not _authorize_media_access(request, filename, media_meta):
                return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
        elif production_mode or OBJECT_STORAGE_SETTINGS.provider == "azure":
            return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
    else:
        media_meta = None

    data: Optional[bytes] = None
    if os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            data = f.read()
    elif media_meta and media_meta.get("blob_name"):
        data = _download_media_from_storage(media_meta["blob_name"])
    if not data:
        return JSONResponse(status_code=404, content=error_payload("download_not_found", resolve_locale(request)))
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@app.get("/api/media/results/{filename}")
async def serve_authorized_result(filename: str, request: Request):
    try:
        local_path = _safe_media_path(ASSET_DIR, filename)
    except ValueError:
        return JSONResponse(status_code=400, content=error_payload("validation_error", resolve_locale(request)))
    media_meta = get_media_file(filename)
    if not _authorize_media_access(request, filename, media_meta):
        return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
    data: Optional[bytes] = None
    if os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            data = f.read()
    elif media_meta and media_meta.get("blob_name"):
        data = _download_media_from_storage(media_meta["blob_name"])
    if not data:
        return JSONResponse(status_code=404, content=error_payload("download_not_found", resolve_locale(request)))
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@app.get("/api/result-data-url/{filename}")
async def get_result_data_url(filename: str, request: Request):
    """Generate base64 data URL on demand instead of keeping it in memory."""
    safe_name = os.path.basename(filename)
    media_meta = get_media_file(safe_name)
    if media_meta is not None and not _authorize_media_access(request, safe_name, media_meta):
        return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
    if media_meta is None and (production_mode or OBJECT_STORAGE_SETTINGS.provider == "azure"):
        return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
    path = os.path.join(ASSET_DIR, safe_name)
    img_bytes: Optional[bytes] = None
    if os.path.isfile(path):
        with open(path, "rb") as f:
            img_bytes = f.read()
    elif media_meta and media_meta.get("blob_name"):
        img_bytes = _download_media_from_storage(media_meta["blob_name"])
    if not img_bytes:
        return JSONResponse(status_code=404, content=error_payload("download_not_found", resolve_locale(request)))
    data_url = f"data:image/png;base64,{base64.b64encode(img_bytes).decode('utf-8')}"
    return {"data_url": data_url}


@app.get("/prompt")
async def get_prompt():
    return {"prompt": _read_base_prompt()}


@app.get("/api/frontend-config")
async def get_frontend_config():
    return {
        "ok": True,
        "recommend_app_url": RECOMMEND_APP_URL,
        "tryon_embed_mode": TRYON_EMBED_MODE,
    }




async def _read_upload_request(request: Request) -> bytes:
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise ValueError("请使用 multipart/form-data 上传图片")
    data = bytearray()
    header_name, header_value = bytearray(), bytearray()
    state = {"disposition": b"", "target": False, "found": False, "complete": False}

    def part_begin():
        state["disposition"] = b""
        state["target"] = False

    def header_field(chunk, start, end):
        header_name.extend(chunk[start:end])

    def header_value_part(chunk, start, end):
        header_value.extend(chunk[start:end])

    def header_end():
        if bytes(header_name).lower() == b"content-disposition":
            state["disposition"] = bytes(header_value)
        header_name.clear()
        header_value.clear()

    def headers_finished():
        _, fields = parse_options_header(state["disposition"])
        if fields.get(b"name") == b"file" and b"filename" in fields:
            if state["found"]:
                raise ValueError("一次只能上传一张图片")
            state["target"] = True
            state["found"] = True

    def part_data(chunk, start, end):
        if state["target"]:
            if len(data) + end - start > INTAKE_MAX_IMAGE_BYTES:
                raise ValueError("图片过大，当前仅支持 15MB 以内图片")
            data.extend(chunk[start:end])

    def end():
        state["complete"] = True

    parser = MultipartParser(boundary, {
        "on_part_begin": part_begin, "on_header_field": header_field,
        "on_header_value": header_value_part, "on_header_end": header_end,
        "on_headers_finished": headers_finished, "on_part_data": part_data, "on_end": end,
    })
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > INTAKE_MAX_IMAGE_BYTES + 65536:
            raise ValueError("上传请求过大")
        parser.write(chunk)
    parser.finalize()
    if not state["found"] or not state["complete"]:
        raise ValueError("上传图片数据不完整")
    return bytes(data)


async def _save_upload_file(request: Request) -> Tuple[str, Optional[str]]:
    data = await _read_upload_request(request)
    ext = _validate_and_resolve_image_suffix(data)
    return _save_upload_bytes(data, ext)


def _guess_image_suffix(content_type: Optional[str]) -> str:
    normalized = str(content_type or "").split(";", 1)[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get(normalized, ".png")


def _validate_and_resolve_image_suffix(image_bytes: bytes, fallback_suffix: Optional[str] = None) -> str:
    if not image_bytes:
        raise ValueError("图片数据为空，无法自动导入")
    if len(image_bytes) > INTAKE_MAX_IMAGE_BYTES:
        raise ValueError("图片过大，当前自动导入仅支持 15MB 以内图片")

    try:
        with PIL.Image.open(io.BytesIO(image_bytes)) as img:
            fmt = str(img.format or "").strip().lower()
            img.load()
    except Exception as e:
        raise ValueError("无法识别图片数据，请改为手动上传原图") from e

    if fmt in ("jpeg", "jpg"):
        return ".jpg"
    if fmt == "png":
        return ".png"
    if fmt == "webp":
        return ".webp"
    return str(fallback_suffix or ".png")


def _save_upload_bytes(image_bytes: bytes, suffix: Optional[str] = None) -> Tuple[str, Optional[str]]:
    ext = str(suffix or ".png").lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(image_bytes)
    cloud_url = _upload_bytes_to_gcs(image_bytes, filename, UPLOADS_GCS_PREFIX, _content_type_from_ext(ext))
    return filename, cloud_url


def _check_url_safe_for_ssrf(url: str) -> None:
    """Raises ValueError if url resolves to a private/internal/metadata address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("只支持 http / https 图片地址")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("无效的图片地址（缺少主机名）")
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except OSError:
        raise ValueError("无法解析图片地址的主机名")
    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        raw_ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
            or any(addr in net for net in _SSRF_BLOCKED_NETWORKS)
        ):
            raise ValueError("不允许访问该图片地址")


async def _fetch_remote_image_bytes(raw_url: str) -> Tuple[bytes, str]:
    url = str(raw_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("自动导入只支持 http / https 图片地址")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        current_url = url
        for _hop in range(5):
            _check_url_safe_for_ssrf(current_url)
            async with client.stream("GET", current_url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if not location:
                        raise ValueError("重定向响应缺少 Location 头")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code != 200:
                    raise ValueError(f"远程图片下载失败 (HTTP {response.status_code})")
                try:
                    content_length = int(response.headers.get("content-length", ""))
                except (ValueError, TypeError):
                    content_length = None
                if content_length is not None and content_length > INTAKE_MAX_IMAGE_BYTES:
                    raise ValueError("远程图片文件过大")
                content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if content_type and not content_type.startswith("image/"):
                    raise ValueError("远程地址返回的不是图片资源")
                image_bytes = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    image_bytes.extend(chunk)
                    if len(image_bytes) > INTAKE_MAX_IMAGE_BYTES:
                        raise ValueError("远程图片文件过大")
                return bytes(image_bytes), content_type
        raise ValueError("远程图片重定向次数超过限制")


def _decode_recommended_image_data(raw_value: str) -> Tuple[bytes, str]:
    text = str(raw_value or "").strip()
    if not text:
        raise ValueError("缺少 data URL / base64 图片数据")

    content_type = ""
    payload = text
    matched = IMAGE_DATA_URL_RE.match(text)
    if matched:
        content_type = str(matched.group(1) or "").strip().lower()
        payload = str(matched.group(2) or "").strip()

    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except Exception as e:
        raise ValueError("data URL / base64 图片数据无效") from e

    return image_bytes, content_type


@app.post("/api/intake-image")
async def intake_image(request: Request, payload: Dict[str, Any]):
    try:
        image_url = str(payload.get("image_url") or "").strip()
        image_data_url = str(payload.get("image_data_url") or payload.get("image_base64") or "").strip()
        role = str(payload.get("role") or "image").strip() or "image"
        locale = resolve_locale(request, payload.get("locale"))

        if image_url:
            try:
                image_bytes, content_type = await _fetch_remote_image_bytes(image_url)
                source_type = "url"
            except Exception:
                if not image_data_url:
                    raise
                image_bytes, content_type = _decode_recommended_image_data(image_data_url)
                source_type = "data_url"
        elif image_data_url:
            image_bytes, content_type = _decode_recommended_image_data(image_data_url)
            source_type = "data_url"
        else:
            raise ValueError("缺少 image_url 或 image_data_url，无法自动预填图片")

        suffix = _validate_and_resolve_image_suffix(image_bytes, _guess_image_suffix(content_type))
        filename, _ = _save_upload_bytes(image_bytes, suffix)
        visitor_token, is_new = _resolve_or_create_visitor_token(request)
        token_hash = hash_access_token(visitor_token)
        blob_name = _make_blob_name(UPLOADS_GCS_PREFIX, filename)
        register_media_file(
            filename=filename,
            blob_name=blob_name,
            media_kind="upload",
            access_token_hash=token_hash,
            content_type=_content_type_from_ext(suffix),
        )
        proxy_url = _issue_upload_proxy_url(filename, token_hash)
        resp = JSONResponse({
            "ok": True,
            "role": role,
            "locale": locale,
            "source_type": source_type,
            "filename": filename,
            "url": proxy_url,
            "cloud_url": proxy_url,
            "task_token": visitor_token,
        })
        if is_new:
            _set_visitor_cookie(resp, visitor_token)
        return resp
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, **error_payload("validation_error", resolve_locale(request), detail=str(e))})

@app.get("/api/runtime-status")
async def get_runtime_status():
    """Non-sensitive runtime status. No auth required. No secrets returned."""
    return get_tryon_runtime_status()



UPLOAD_OPENAPI = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
    "type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]
}}}}}


@app.post("/upload/model", openapi_extra=UPLOAD_OPENAPI)
async def upload_model(request: Request):
    return await _upload_response(request)


@app.post("/upload/garment", openapi_extra=UPLOAD_OPENAPI)
async def upload_garment(request: Request):
    return await _upload_response(request)


@app.post("/upload/target", openapi_extra=UPLOAD_OPENAPI)
async def upload_target_alias(request: Request):
    return await _upload_response(request)


@app.post("/upload/reference", openapi_extra=UPLOAD_OPENAPI)
async def upload_reference_alias(request: Request):
    return await _upload_response(request)


async def _upload_response(request: Request):
    try:
        filename, cloud_url = await _save_upload_file(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token_fn = globals().get("_resolve_or_create_visitor_token")
    hash_fn = globals().get("hash_access_token")
    reg_fn = globals().get("register_media_file")
    proxy_fn = globals().get("_issue_upload_proxy_url")
    blob_fn = globals().get("_make_blob_name")
    cookie_fn = globals().get("_set_visitor_cookie")
    if callable(token_fn) and callable(hash_fn) and callable(reg_fn) and callable(proxy_fn) and callable(blob_fn):
        visitor_token, is_new = token_fn(request)
        token_hash = hash_fn(visitor_token)
        ext = os.path.splitext(filename)[1] or ".png"
        blob_name = blob_fn(UPLOADS_GCS_PREFIX, filename)
        reg_fn(
            filename=filename,
            blob_name=blob_name,
            media_kind="upload",
            access_token_hash=token_hash,
            content_type=_content_type_from_ext(ext),
        )
        proxy_url = proxy_fn(filename, token_hash)
        resp = JSONResponse({"filename": filename, "cloud_url": proxy_url, "url": proxy_url, "task_token": visitor_token})
        if is_new and callable(cookie_fn):
            cookie_fn(resp, visitor_token)
        return resp
    return {"filename": filename, "cloud_url": cloud_url}


def _ensure_input_blob_persisted(filename: str, access_token_hash: str) -> Optional[str]:
    meta = get_media_file(filename)
    if meta and meta.get("blob_name"):
        return str(meta["blob_name"])
    local_path = _safe_media_path(UPLOAD_DIR, filename)
    if not os.path.isfile(local_path):
        return None
    with open(local_path, "rb") as f:
        data = f.read(INTAKE_MAX_IMAGE_BYTES + 1)
    ext = _validate_and_resolve_image_suffix(data)
    blob_name = _make_blob_name(UPLOADS_GCS_PREFIX, filename)
    get_object_storage().upload_bytes(
        blob_name,
        data,
        content_type=_content_type_from_ext(ext),
        cache_control="no-store, max-age=0",
    )
    register_media_file(
        filename=filename,
        blob_name=blob_name,
        media_kind="upload",
        access_token_hash=access_token_hash,
        content_type=_content_type_from_ext(ext),
    )
    return blob_name


def _db_task_to_public_payload(task_record: Dict[str, Any], locale_override: Optional[str] = None) -> Dict[str, Any]:
    data = dict(task_record)
    if locale_override:
        data["locale"] = locale_override
    result_filename = data.get("result_filename")
    if data.get("status") == "completed" and result_filename:
        signed_url = _issue_result_proxy_url(
            data["task_id"],
            result_filename,
            data.get("access_token_hash") or "",
        )
        data["result_url"] = signed_url
        data["result_cloud_url"] = signed_url
        data["result_display_url"] = signed_url
    payload = _task_public_payload(data)
    payload["upstream_status"] = data.get("upstream_status")
    payload["attempt_count"] = int(data.get("attempt_count") or 0)
    return payload


@app.post("/submit-task")
async def submit_task(
    request: Request,
    target_image: List[str] = Form(...),
    reference_image: str = Form(...),
    custom_prompt: Optional[str] = Form(None),
    prompt_mode: Optional[str] = Form("append"),
    freedom: Optional[int] = Form(5),
    garment_type: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    target_image_cloud_url: Optional[str] = Form(None),
    reference_image_cloud_url: Optional[str] = Form(None),
    locale: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
    model_id: Optional[str] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    image_size: Optional[str] = Form(None),
    quality: Optional[str] = Form(None),
    temperature: Optional[str] = Form(None),
    seed: Optional[str] = Form(None),
    totokens_profile: Optional[str] = Form(None),
):
    target_locale = resolve_locale(request, locale)
    try:
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")
        prepared = _prepare_tryon_submission(
            model=model,
            provider=provider,
            model_id=model_id,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            quality=quality,
            temperature=temperature,
            seed=seed,
            totokens_profile=totokens_profile,
        )
    except Exception as e:
        status_code = 503 if isinstance(e, RuntimeError) else 400
        code = "runtime_unavailable" if status_code == 503 else "validation_error"
        return JSONResponse(status_code=status_code, content=error_payload(code, target_locale, detail=str(e)))

    model_key = prepared["model_key"]
    req_provider = prepared["provider_key"]
    req_model_id = prepared["model_id"]
    detail_options = prepared["detail_options"]
    reported_model = req_model_id or model_key

    freedom = _normalize_freedom(freedom)
    visitor_token, is_new_token = _resolve_or_create_visitor_token(request)
    token_hash = hash_access_token(visitor_token)
    raw_idem = str(idempotency_key or request.headers.get("x-idempotency-key") or "").strip()

    if not _is_queue_execution_mode():
        # Local/inline test compatibility path
        import hashlib
        if not raw_idem:
            dedup_hash = hashlib.md5(
                f"{target_image}:{reference_image}:{model_key}:{req_provider}:{req_model_id}:{freedom}".encode()
            ).hexdigest()
            now = time.time()
            if dedup_hash in _PENDING_DEDUP and now - _PENDING_DEDUP[dedup_hash] < 10:
                return JSONResponse(status_code=429, content=error_payload("rate_limited", target_locale))
            _PENDING_DEDUP[dedup_hash] = now
            task_id = str(uuid.uuid4())
        else:
            task_id = derive_idempotent_task_id(token_hash, raw_idem)
            if task_id in TASKS:
                return {"task_id": task_id, "status": TASKS[task_id].get("status", "pending")}

        TASKS[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "Task submitted",
            "message_code": "pending",
            "locale": target_locale,
            "result_url": None,
            "result_cloud_url": None,
            "result_display_url": None,
            "result_data_url": None,
            "freedom": freedom,
            "garment_type": str(garment_type or "").strip(),
            "provider_key": req_provider,
            "model_id": req_model_id,
            "detail_options": detail_options,
            "logs": [],
            "error": None,
            "created_at": time.time(),
            "access_token_hash": token_hash,
        }
        _prune_old_tasks()
        _persist_task(task_id)
        asyncio.create_task(_admin_report.report_tryon_task(
            task_id, "pending", model_used=reported_model, locale=target_locale,
        ))
        asyncio.create_task(
            _process_task(
                task_id=task_id,
                target_image=target_image,
                reference_image=reference_image,
                custom_prompt=custom_prompt,
                prompt_mode=prompt_mode,
                freedom=freedom,
                garment_type=garment_type,
                model=model_key,
                target_image_cloud_url=target_image_cloud_url,
                reference_image_cloud_url=reference_image_cloud_url,
                provider=req_provider,
                model_id=req_model_id,
                detail_options=detail_options,
            )
        )
        return {"task_id": task_id}

    # Queue-backed durable execution path (Azure Container Apps / multi-replica)
    effective_idem = raw_idem or str(uuid.uuid4())
    task_id = derive_idempotent_task_id(token_hash, effective_idem)

    existing = get_task_record(task_id)
    if existing is not None:
        resp = JSONResponse({
            "task_id": existing["task_id"],
            "status": existing["status"],
            "task_token": visitor_token,
            "idempotent_reused": True,
        })
        if is_new_token:
            _set_visitor_cookie(resp, visitor_token)
        return resp

    target_filename = target_image[0]
    ref_filename = reference_image
    try:
        target_blob = _ensure_input_blob_persisted(target_filename, token_hash)
        ref_blob = _ensure_input_blob_persisted(ref_filename, token_hash)
    except ValueError as exc:
        return JSONResponse(status_code=400, content=error_payload("validation_error", target_locale, detail=str(exc)))

    if not target_blob or not ref_blob:
        return JSONResponse(
            status_code=400,
            content=error_payload("validation_error", target_locale, detail="上传的模特或服装图片已过期，请重新上传"),
        )

    manifest = {
        "version": 1,
        "task_id": task_id,
        "idempotency_key": effective_idem,
        "access_token_hash": token_hash,
        "locale": target_locale,
        "model_key": model_key,
        "provider_key": req_provider,
        "model_id": req_model_id,
        "detail_options": detail_options,
        "freedom": freedom,
        "garment_type": str(garment_type or "").strip(),
        "custom_prompt": custom_prompt,
        "prompt_mode": prompt_mode or "append",
        "target_filename": target_filename,
        "reference_filename": ref_filename,
        "input_target_blob": target_blob,
        "input_reference_blob": ref_blob,
        "status": "queued",
        "message_code": "queued",
        "message": task_message("queued", target_locale),
    }
    get_object_storage().upload_bytes(
        f"{TASKS_META_PREFIX}/{task_id}.json",
        json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
        cache_control="no-store, max-age=0",
    )

    record, created = create_or_get_task(
        task_id=task_id,
        idempotency_key=effective_idem,
        access_token_hash=token_hash,
        locale=target_locale,
        model_key=model_key,
        provider_key=req_provider,
        model_id=req_model_id,
        detail_options=detail_options,
        freedom=freedom,
        garment_type=str(garment_type or "").strip(),
        custom_prompt=custom_prompt,
        prompt_mode=prompt_mode or "append",
        target_filename=target_filename,
        reference_filename=ref_filename,
        input_target_blob=target_blob,
        input_reference_blob=ref_blob,
        status="queued",
        message_code="queued",
        message=task_message("queued", target_locale),
    )
    if created:
        _get_task_queue().enqueue(task_id)
        try:
            await _admin_report.report_tryon_task(
                task_id, "queued", model_used=reported_model, locale=target_locale,
            )
        except Exception:
            pass

    resp = JSONResponse({
        "task_id": record["task_id"],
        "status": record["status"],
        "task_token": visitor_token,
        "idempotent_reused": not created,
    })
    if is_new_token:
        _set_visitor_cookie(resp, visitor_token)
    return resp


@app.get("/task/{task_id}")
async def get_task(task_id: str, request: Request):
    req_locale = resolve_locale(request) if (request.query_params.get("lang") or request.query_params.get("locale")) else None

    db_task = get_task_record(task_id)
    if db_task is None and _is_queue_execution_mode():
        # Recover waiting state from immutable private Blob manifest if DB insert raced
        raw_manifest = _download_media_from_storage(f"{TASKS_META_PREFIX}/{task_id}.json")
        if raw_manifest:
            try:
                db_task = upsert_task_from_manifest(json.loads(raw_manifest.decode("utf-8")))
            except Exception:
                db_task = None

    if db_task is not None:
        expected_hash = db_task.get("access_token_hash") or ""
        if expected_hash and not _has_valid_ingest_key(request):
            provided = _extract_visitor_token(request)
            if not provided or hash_access_token(provided) != expected_hash:
                return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
        return _db_task_to_public_payload(db_task, locale_override=req_locale)

    task = TASKS.get(task_id)
    if task:
        expected_hash = task.get("access_token_hash") or ""
        if expected_hash and not _has_valid_ingest_key(request):
            provided = _extract_visitor_token(request)
            if not provided or hash_access_token(provided) != expected_hash:
                return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
        payload_src = dict(task)
        if req_locale:
            payload_src["locale"] = req_locale
        return _task_public_payload(payload_src)

    stored = _load_task_from_store(task_id)
    if stored:
        return _task_public_payload(stored)
    return JSONResponse(status_code=404, content=error_payload("task_not_found", resolve_locale(request)))


@app.post("/api/retry")
async def retry_failed_task(request: Request, payload: Dict[str, Any]):
    if not _has_valid_ingest_key(request):
        return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
    task_id = str(payload.get("task_id") or "").strip()
    allow_unknown_retry = bool(payload.get("allow_unknown_retry", False))
    if not task_id:
        return JSONResponse(status_code=400, content=error_payload("validation_error", resolve_locale(request), detail="task_id is required"))
    try:
        updated = reset_task_for_retry(task_id, allow_unknown_retry=allow_unknown_retry)
    except LookupError:
        return JSONResponse(status_code=404, content=error_payload("task_not_found", resolve_locale(request)))
    except ValueError as exc:
        return JSONResponse(status_code=400, content=error_payload("validation_error", resolve_locale(request), detail=str(exc)))
    _get_task_queue().enqueue(task_id)
    return {"ok": True, "task_id": updated["task_id"], "status": updated["status"]}


@app.post("/generate")
async def generate_once(
    request: Request,
    target_image: List[str] = Form(...),
    reference_image: str = Form(...),
    custom_prompt: Optional[str] = Form(None),
    prompt_mode: Optional[str] = Form("append"),
    freedom: Optional[int] = Form(5),
    garment_type: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    target_image_cloud_url: Optional[str] = Form(None),
    reference_image_cloud_url: Optional[str] = Form(None),
    locale: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
    model_id: Optional[str] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    image_size: Optional[str] = Form(None),
    quality: Optional[str] = Form(None),
    temperature: Optional[str] = Form(None),
    seed: Optional[str] = Form(None),
    totokens_profile: Optional[str] = Form(None),
):
    target_locale = resolve_locale(request, locale)
    sync_enabled = os.environ.get("ENABLE_SYNC_GENERATE", "false").strip().lower() == "true"
    if production_mode and not sync_enabled:
        return JSONResponse(status_code=403, content=error_payload("sync_disabled", target_locale))

    try:
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")

        prepared = _prepare_tryon_submission(
            model=model,
            provider=provider,
            model_id=model_id,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            quality=quality,
            temperature=temperature,
            seed=seed,
            totokens_profile=totokens_profile,
        )
        model_key = prepared["model_key"]
        req_provider = prepared["provider_key"]
        req_model_id = prepared["model_id"]
        detail_options = prepared["detail_options"]
        freedom_level = _normalize_freedom(freedom)
        prompt_text = _build_prompt(custom_prompt, prompt_mode or "append", freedom_level, garment_type)
        rate_identity = _rate_identity()
        token_cost = _estimate_token_cost(prompt_text)
        await _check_and_consume_rate_limit(
            identity=rate_identity,
            model_key=model_key,
            token_cost=token_cost,
        )

        img_bytes = await _generate_tryon_image_bytes(
            model_filename=target_image[0],
            garment_filename=reference_image,
            custom_prompt=custom_prompt,
            prompt_mode=prompt_mode or "append",
            freedom=freedom_level,
            garment_type=garment_type,
            model_key=model_key,
            model_cloud_url=target_image_cloud_url,
            garment_cloud_url=reference_image_cloud_url,
            provider=req_provider,
            model_id=req_model_id,
            detail_options=detail_options,
        )

        visitor_token, is_new = _resolve_or_create_visitor_token(request)
        token_hash = hash_access_token(visitor_token)
        out = _save_generated_bytes(img_bytes, access_token_hash=token_hash)
        resp = JSONResponse({
            "status": "success",
            "locale": target_locale,
            "generated_image_url": out["result_url"],
            "result_url": out["result_url"],
            "result_cloud_url": out.get("result_cloud_url"),
            "result_display_url": out.get("result_display_url"),
            "result_data_url": out["result_data_url"],
            "provider": prepared["effective_provider"],
            "model_id": prepared["effective_model_id"],
            "detail_options": detail_options,
        })
        if is_new:
            _set_visitor_cookie(resp, visitor_token)
        return resp
    except Exception as e:
        if isinstance(e, ValueError):
            status_code = 400
        elif isinstance(e, RuntimeError):
            status_code = 503
        else:
            status_code = 500
        code = "validation_error" if status_code == 400 else "runtime_unavailable" if status_code == 503 else "internal_error"
        return JSONResponse(status_code=status_code, content=error_payload(code, resolve_locale(request), detail=str(e)))


def _safe_media_path(root: str, filename: str) -> str:
    if not isinstance(filename, str) or not filename:
        raise ValueError("无效的图片文件名")
    decoded = filename
    for _ in range(4):
        if decoded in ("", ".", "..") or any(ch in decoded for ch in ("/", "\\", ":", "\x00")):
            raise ValueError("无效的图片文件名")
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    else:
        raise ValueError("无效的图片文件名")
    root_path = os.path.realpath(root)
    local_path = os.path.realpath(os.path.join(root_path, decoded))
    if os.path.commonpath([root_path, local_path]) != root_path:
        raise ValueError("图片路径超出媒体目录")
    return local_path


def _extract_local_candidates(raw_url: str) -> List[str]:
    if not isinstance(raw_url, str):
        return []

    url = raw_url.strip()
    if not url or url.startswith("data:image/"):
        return []

    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return []
    if parsed.scheme and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        return []
    path = parsed.path
    if not path or "\\" in path:
        return []
    routes = {"assets": ASSET_DIR, "uploads": UPLOAD_DIR, "history-files": HISTORY_FILES_DIR}
    parts = path.lstrip("/").split("/")
    if len(parts) == 2 and parts[0] in routes:
        roots, filename = [routes[parts[0]]], parts[1]
    elif len(parts) == 4 and parts[0] == "api" and parts[1] == "media" and parts[2] == "results":
        roots, filename = [ASSET_DIR], parts[3]
    elif len(parts) == 1 and not path.startswith("/") and not parsed.scheme:
        roots, filename = list(routes.values()), parts[0]
    else:
        return []
    candidates = []
    for root in roots:
        try:
            candidates.append(_safe_media_path(root, filename))
        except ValueError:
            continue
    return candidates


def _build_download_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


@app.get("/download-single")
async def download_single(url: str, request: Request):
    """代理下载单张图片，避免浏览器端 CORS 限制。"""
    if not url or not url.strip():
        return JSONResponse(status_code=400, content=error_payload("missing_url", resolve_locale(request)))
    raw = url.strip()
    img_bytes = None
    # 优先查找本地文件（校验授权）
    for local_path in _extract_local_candidates(raw):
        if os.path.isfile(local_path):
            fname = os.path.basename(local_path)
            media_lookup = globals().get("get_media_file")
            auth_fn = globals().get("_authorize_media_access")
            if request is not None and callable(media_lookup) and callable(auth_fn):
                meta = media_lookup(fname)
                if meta and not auth_fn(request, fname, meta):
                    return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
            with open(local_path, "rb") as f:
                img_bytes = f.read()
            break
    # 跨副本从私有 Blob 获取已授权媒体
    if img_bytes is None:
        parsed_local = urlparse(raw)
        if not parsed_local.scheme and parsed_local.path.startswith(("/assets/", "/uploads/", "/api/media/results/")):
            fname = os.path.basename(parsed_local.path)
            media_lookup = globals().get("get_media_file")
            auth_fn = globals().get("_authorize_media_access")
            dl_fn = globals().get("_download_media_from_storage")
            if request is not None and callable(media_lookup) and callable(auth_fn) and callable(dl_fn):
                meta = media_lookup(fname)
                if meta:
                    if not auth_fn(request, fname, meta):
                        return JSONResponse(status_code=403, content=error_payload("forbidden", resolve_locale(request)))
                    img_bytes = dl_fn(meta.get("blob_name"))
    # 本地不存在则远程获取
    if img_bytes is None:
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            return JSONResponse(status_code=404, content=error_payload("download_not_found", resolve_locale(request)))
        try:
            img_bytes, _ = await _fetch_remote_image_bytes(raw)
        except (ValueError, httpx.HTTPError) as exc:
            return JSONResponse(status_code=502, content=error_payload("upstream_error", resolve_locale(request), detail=str(exc)))
    if not img_bytes or len(img_bytes) < 80:
        return JSONResponse(status_code=404, content=error_payload("download_not_found", resolve_locale(request)))
    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=tryon_result.png"},
    )


@app.post("/download-batch")
async def download_batch(request: Request, filenames: str = Form(...)):
    try:
        urls = json.loads(filenames)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content=error_payload("download_invalid", resolve_locale(request), detail="invalid filenames JSON"))

    if not isinstance(urls, list) or len(urls) == 0:
        return JSONResponse(status_code=400, content=error_payload("download_invalid", resolve_locale(request), detail="no files to download"))

    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    added_count = 0
    failed_count = 0
    batch_stamp = _build_download_stamp()

    try:
        with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for i, url in enumerate(urls, 1):
                arcname = f"试衣结果_{batch_stamp}_{i:02d}.png"
                img_bytes = None
                try:
                    if isinstance(url, str) and url.startswith("data:image/"):
                        _, b64_data = url.split(",", 1)
                        img_bytes = base64.b64decode(b64_data)
                    else:
                        for local_path in _extract_local_candidates(str(url)):
                            if os.path.isfile(local_path):
                                with open(local_path, "rb") as f:
                                    img_bytes = f.read()
                                break
                        if img_bytes is None:
                            raw = str(url).strip()
                            parsed_local = urlparse(raw)
                            if not parsed_local.scheme and parsed_local.path.startswith(("/assets/", "/uploads/", "/api/media/results/")):
                                fname = os.path.basename(parsed_local.path)
                                media_lookup = globals().get("get_media_file")
                                auth_fn = globals().get("_authorize_media_access")
                                dl_fn = globals().get("_download_media_from_storage")
                                if callable(media_lookup) and callable(auth_fn) and callable(dl_fn):
                                    meta = media_lookup(fname)
                                    if meta and auth_fn(request, fname, meta):
                                        img_bytes = dl_fn(meta.get("blob_name"))
                            elif parsed_local.scheme in ("http", "https"):
                                img_bytes, _ = await _fetch_remote_image_bytes(raw)

                    if not img_bytes or len(img_bytes) < 80:
                        raise ValueError("image payload empty or too small")

                    zf.writestr(arcname, img_bytes)
                    added_count += 1
                except Exception as item_error:
                    failed_count += 1
                    print(f"[download-batch] skip {url}: {item_error}")

        if added_count == 0:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return JSONResponse(
                status_code=400,
                content=error_payload("download_failed", resolve_locale(request), detail=f"total={len(urls)}, failed={failed_count}"),
            )

        async def stream_zip():
            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        file_size = os.path.getsize(tmp_path)
        zip_name = f"试衣结果_{added_count}张_{batch_stamp}.zip"
        ascii_name = f"tryon_batch_{added_count}_{batch_stamp}.zip"
        return StreamingResponse(
            stream_zip(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={ascii_name}; filename*=UTF-8''{quote(zip_name)}",
                "Content-Length": str(file_size),
            },
        )

    except Exception as e:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        _append_error_log(str(e), context="download_batch")
        return JSONResponse(status_code=500, content=error_payload("internal_error", resolve_locale(request), detail=str(e)))


@app.get("/api/rate-status")
async def get_rate_status(
    request: Request,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    totokens_profile: Optional[str] = None,
):
    try:
        validate_provider_key(provider)
        cleaned_id = validate_model_id(model_id) if model_id else None
        validate_totokens_profile_id(totokens_profile)
    except ValueError as exc:
        return JSONResponse(status_code=400, content=error_payload("validation_error", resolve_locale(request), detail=str(exc)))
    if model in MODEL_MAP:
        model_key = model
    elif cleaned_id:
        model_key = infer_preset_key(cleaned_id)
    else:
        model_key = DEFAULT_MODEL
    identity = _rate_identity()
    snap = _rate_status_snapshot(identity, model_key)
    if cleaned_id:
        snap["model_name"] = cleaned_id
    return {"ok": True, **snap}


@app.get("/api/key-usage")
async def get_key_usage():
    """Return aggregated usage stats (no key exposure)."""
    row = KEY_USAGE.get("tryon")
    if not row:
        return {
            "found": False,
            "calls": 0,
            "success": 0,
            "failed": 0,
            "cost": 0.0,
            "last_used": "",
        }
    return {"found": True, **row}


@app.get("/api/errors")
async def get_errors(request: Request):
    return {"locale": resolve_locale(request), "total": len(ERROR_LOGS), "errors": ERROR_LOGS[:200]}


@app.delete("/api/errors")
async def clear_errors(request: Request):
    ERROR_LOGS.clear()
    return {"ok": True, "locale": resolve_locale(request)}


@app.post("/api/errors/report")
async def report_error(request: Request, message: str = Form(...), context: Optional[str] = Form(None), detail: Optional[str] = Form(None)):
    item = _append_error_log(message, context=context or "frontend", detail=detail or "")
    return {"ok": True, "locale": resolve_locale(request), "error": item}


@app.put("/api/errors/{error_id}/analysis")
async def update_error_analysis(request: Request, error_id: str, analysis: str = Form(...)):
    for row in ERROR_LOGS:
        if row.get("id") == error_id:
            row["analysis"] = str(analysis or "")[:6000]
            return {"ok": True, "locale": resolve_locale(request)}
    return JSONResponse(status_code=404, content=error_payload("task_not_found", resolve_locale(request), detail="error_id not found"))





ERROR_ANALYSIS_MODEL = os.environ.get(
    "ERROR_ANALYSIS_MODEL",
    "publishers/google/models/gemini-3.1-flash-lite-preview",
)


def generate_fallback_analysis(error_message: str) -> str:
    msg = (error_message or "").lower()

    def fmt(title: str, cause: str, actions: List[str]) -> str:
        action_text = "\n".join([f"{i + 1}. {a}" for i, a in enumerate(actions)])
        links = "\n".join([f"- {u}" for u in AI_STUDIO_DOC_LINKS])
        return f"{title}\n\n可能原因:\n{cause}\n\n建议排查:\n{action_text}\n\n参考文档:\n{links}"

    if ("task polling failed" in msg) or (("/task/" in msg or "task" in msg) and ("404" in msg or "not found" in msg)):
        return fmt("⚠️ 任务轮询失败", "Cloud Run 多实例下任务状态未持久化，轮询命中其他实例导致 404。", [
            "将任务状态落库（Firestore/Redis/DB），不要只放内存。",
            "确认 /submit-task 与 /task/{id} 使用同一存储。",
            "检查实例冷启动与回收策略。",
        ])
    if ("resource_exhausted" in msg) or ("429" in msg) or ("quota" in msg) or ("rate" in msg):
        return fmt("⏳ 配额或速率限制", "请求超过配额或限流。", [
            "降低并发，增加退避重试。",
            "检查 Google AI Studio 配额和账单。",
            "必要时切换 key 或等待窗口重置。",
        ])
    if "permission_denied" in msg or "403" in msg:
        return fmt("🔒 权限问题", "API Key 无效或权限不足。", [
            "确认 API Key 是否属于当前项目。",
            "确认 Gemini API 是否已启用。",
            "检查配额和账单是否正常。",
        ])
    if ("finish_reason" in msg) or ("image_safety" in msg) or ("safety" in msg):
        return fmt("🛡️ 安全策略拦截", "输入或提示词触发安全策略。", [
            "更换图片，减少敏感内容。",
            "使用更中性的提示词。",
            "记录 finish_reason 与 safety_ratings。",
        ])
    if ("timeout" in msg) or ("deadline" in msg) or ("504" in msg):
        return fmt("⏱️ 请求超时", "生成耗时过长或网络波动。", [
            "增加超时和重试。",
            "降低并发。",
            "记录每次请求耗时。",
        ])

    links = "\n".join([f"- {u}" for u in AI_STUDIO_DOC_LINKS])
    return f"❓ 未知错误\n\n错误信息: {(error_message or '')[:300]}\n\n建议排查:\n1. 检查 API Key 是否有效、Gemini API 是否已启用。\n2. 记录完整堆栈和参数。\n3. 对 5xx/超时类错误增加重试。\n\n参考文档:\n{links}"


@app.post("/analyze-error")
async def analyze_error(
    error_message: str = Form(...),
    error_detail: Optional[str] = Form(None),
):
    merged = (error_message or "") + "\n" + (error_detail or "")
    quick = generate_fallback_analysis(merged)

    # Try to use runtime config for AI analysis
    try:
        config = resolve_tryon_runtime_config()
        api_key = config.get("api_key", "")
        if not api_key:
            return {"analysis": quick}
    except RuntimeError:
        return {"analysis": quick}

    try:
        analysis_client = genai.Client(api_key=api_key)

        prompt = (
            "你是资深 Google AI Studio / Gemini API 排障工程师。"
            "请根据错误信息输出：1) 根因 2) 证据 3) 3条可执行修复步骤。"
            "尽量简洁，中文输出。\n\n"
            f"错误信息:\n{merged}\n\n"
            f"可用参考:\n{quick}"
        )

        loop = asyncio.get_event_loop()
        try_models = [
            "google/gemini-3.1-flash-lite-preview",
            "gemini-3.1-flash-lite-preview",
            ERROR_ANALYSIS_MODEL,
        ]

        response_text = None
        for m in try_models:
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda model_id=m: analysis_client.models.generate_content(model=model_id, contents=prompt),
                )
                response_text = getattr(resp, "text", None)
                if response_text:
                    break
            except Exception:
                continue

        if response_text:
            return {"analysis": response_text.strip()}

        return {"analysis": quick}

    except Exception:
        return {"analysis": quick}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

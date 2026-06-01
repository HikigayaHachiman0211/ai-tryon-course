from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, unquote, quote
from typing import Optional, List, Dict, Any, Tuple

import PIL.Image
import httpx
from google import genai
from app.products import load_catalog, list_products, get_filter_options
from app import admin_report as _admin_report
try:
    from google.cloud import firestore
except Exception:
    firestore = None
try:
    from google.cloud import storage
except Exception:
    storage = None


# ===== Vertex / Project Config =====
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "asia-east1")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "global")
VERTEX_AI_API_KEY = os.environ.get("VERTEX_AI_API_KEY", "")
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "vertex-ai")
RECOMMEND_APP_URL = str(os.environ.get("VITE_RECOMMEND_APP_URL", "") or "").strip()
TRYON_EMBED_MODE = str(os.environ.get("VITE_TRYON_EMBED_MODE", "standalone") or "standalone").strip().lower()
if TRYON_EMBED_MODE not in ("standalone", "embed"):
    TRYON_EMBED_MODE = "standalone"
RESULTS_GCS_BUCKET = str(os.environ.get("RESULTS_GCS_BUCKET", "") or "").strip()
RESULTS_GCS_PREFIX = str(os.environ.get("RESULTS_GCS_PREFIX", "tryon-results") or "tryon-results").strip().strip("/")
UPLOADS_GCS_PREFIX = str(os.environ.get("UPLOADS_GCS_PREFIX", "tryon-uploads") or "tryon-uploads").strip().strip("/")
INTAKE_MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)

MODEL_MAP = {
    "flash": {
        "ids": ["gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"],
        "name": "Nano Banana 2",
    },
    "pro": {
        "ids": ["gemini-3-pro-image-preview", "gemini-3-pro-image"],
        "name": "Nano Banana Pro",
    },
}
DEFAULT_MODEL = "flash"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
CREDENTIALS_PATH = os.path.join(BASE_DIR, "gcp-credentials.json")
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.txt")
LOCAL_PROXY_CONFIG_PATH = os.path.join(BASE_DIR, "local_proxy_config.json")
AI_STUDIO_CONFIG_PATH = os.path.join(BASE_DIR, "ai_studio_config.json")
LOCAL_ANTIGRAVITY_DIRS = [
    os.path.join(os.path.expanduser("~"), ".antigravity_tools"),
    os.path.join(WORKSPACE_DIR, ".antigravity_tools"),
]

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ASSET_DIR = os.path.join(BASE_DIR, "assets")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
HISTORY_FILES_DIR = os.path.join(HISTORY_DIR, "files")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ASSET_DIR, exist_ok=True)
os.makedirs(HISTORY_FILES_DIR, exist_ok=True)

DEFAULT_LOCAL_PROXY_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "base_url": "http://127.0.0.1:8045",
    "api_key": "",
    "timeout_seconds": 180,
    "flash_model": "gemini-3.1-flash-image",
    "pro_model": "gemini-3-pro-image",
}

DEFAULT_AI_STUDIO_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "flash_model": "gemini-3.1-flash-image-preview",
    "pro_model": "gemini-3-pro-image-preview",
}


# ===== Clients =====
vertex_client = None


def init_vertex_client():
    global vertex_client
    if VERTEX_AI_API_KEY:
        vertex_client = genai.Client(api_key=VERTEX_AI_API_KEY)
        print(f"[VertexAI] Initialized by API key, project={GCP_PROJECT_ID}")
        return

    if os.path.exists(CREDENTIALS_PATH):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH

    vertex_client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=VERTEX_LOCATION,
    )
    print(f"[VertexAI] Initialized by ADC/Service Account, project={GCP_PROJECT_ID}, location={VERTEX_LOCATION}")


init_vertex_client()

if firestore is not None:
    try:
        db = firestore.Client()
        print("[DB] Firestore connected")
    except Exception as e:
        db = None
        print(f"[DB] Firestore unavailable, fallback to memory only: {e}")
else:
    db = None
    print("[DB] Firestore module unavailable, fallback to memory only")

if storage is not None and RESULTS_GCS_BUCKET:
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        print(f"[Storage] GCS connected, bucket={RESULTS_GCS_BUCKET}")
    except Exception as e:
        storage_client = None
        print(f"[Storage] GCS unavailable, fallback to local assets only: {e}")
else:
    storage_client = None


def _sanitize_local_proxy_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(DEFAULT_LOCAL_PROXY_CONFIG)
    if isinstance(raw, dict):
        payload.update(raw)
    base_url = str(payload.get("base_url", DEFAULT_LOCAL_PROXY_CONFIG["base_url"]) or "").strip()
    if not base_url:
        base_url = DEFAULT_LOCAL_PROXY_CONFIG["base_url"]
    flash_model = str(payload.get("flash_model", DEFAULT_LOCAL_PROXY_CONFIG["flash_model"]) or "").strip()
    pro_model = str(payload.get("pro_model", DEFAULT_LOCAL_PROXY_CONFIG["pro_model"]) or "").strip()
    timeout_raw = payload.get("timeout_seconds", DEFAULT_LOCAL_PROXY_CONFIG["timeout_seconds"])
    try:
        timeout_seconds = int(timeout_raw)
    except Exception:
        timeout_seconds = int(DEFAULT_LOCAL_PROXY_CONFIG["timeout_seconds"])
    return {
        "enabled": bool(payload.get("enabled", False)),
        "base_url": base_url.rstrip("/"),
        "api_key": str(payload.get("api_key", "") or "").strip(),
        "timeout_seconds": max(30, min(600, timeout_seconds)),
        "flash_model": flash_model or DEFAULT_LOCAL_PROXY_CONFIG["flash_model"],
        "pro_model": pro_model or DEFAULT_LOCAL_PROXY_CONFIG["pro_model"],
    }


def _load_local_proxy_config() -> Dict[str, Any]:
    try:
        if os.path.exists(LOCAL_PROXY_CONFIG_PATH):
            with open(LOCAL_PROXY_CONFIG_PATH, "r", encoding="utf-8") as f:
                return _sanitize_local_proxy_config(json.load(f))
    except Exception as e:
        print(f"[LocalProxy] load config failed: {e}")
    return dict(DEFAULT_LOCAL_PROXY_CONFIG)


def _save_local_proxy_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = _sanitize_local_proxy_config(raw)
    with open(LOCAL_PROXY_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def _sanitize_ai_studio_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(DEFAULT_AI_STUDIO_CONFIG)
    if isinstance(raw, dict):
        payload.update(raw)
    flash_model = str(payload.get("flash_model", DEFAULT_AI_STUDIO_CONFIG["flash_model"]) or "").strip()
    pro_model = str(payload.get("pro_model", DEFAULT_AI_STUDIO_CONFIG["pro_model"]) or "").strip()
    if flash_model == "gemini-2.5-flash-image":
        flash_model = DEFAULT_AI_STUDIO_CONFIG["flash_model"]
    return {
        "api_key": str(payload.get("api_key", "") or "").strip(),
        "flash_model": flash_model or DEFAULT_AI_STUDIO_CONFIG["flash_model"],
        "pro_model": pro_model or DEFAULT_AI_STUDIO_CONFIG["pro_model"],
    }


def _load_ai_studio_config() -> Dict[str, Any]:
    try:
        if os.path.exists(AI_STUDIO_CONFIG_PATH):
            with open(AI_STUDIO_CONFIG_PATH, "r", encoding="utf-8") as f:
                return _sanitize_ai_studio_config(json.load(f))
    except Exception as e:
        print(f"[AIStudio] load config failed: {e}")
    return dict(DEFAULT_AI_STUDIO_CONFIG)


def _save_ai_studio_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = _sanitize_ai_studio_config(raw)
    with open(AI_STUDIO_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def _mask_secret(secret: str) -> str:
    value = str(secret or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:4]}...{value[-4:]}"


def _proxy_api_base(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith("/v1beta"):
        return normalized
    return f"{normalized}/v1beta"


def _proxy_root_base(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.endswith("/v1beta"):
        return normalized[:-7].rstrip("/")
    return normalized


def _proxy_openai_base(base_url: str) -> str:
    root = _proxy_root_base(base_url)
    if not root:
        return ""
    if root.endswith("/v1"):
        return root
    return f"{root}/v1"


def _normalize_proxy_model_name(name: Optional[str]) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return text.rsplit("/", 1)[-1]


def _proxy_headers(request_key: Optional[str]) -> Dict[str, str]:
    token = str(request_key or "").strip()
    headers: Dict[str, str] = {}
    if token:
        headers["x-goog-api-key"] = token
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_proxy_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            status = str(error.get("status") or "").strip()
            if message:
                try:
                    nested = json.loads(message)
                except Exception:
                    nested = None
                if isinstance(nested, dict):
                    nested_error = nested.get("error")
                    if isinstance(nested_error, dict):
                        nested_message = str(nested_error.get("message") or "").strip()
                        nested_status = str(nested_error.get("status") or "").strip()
                        if nested_message:
                            return f"{nested_status}: {nested_message}" if nested_status else nested_message
                return f"{status}: {message}" if status else message
    if isinstance(payload, str):
        return payload.strip()
    return ""


def _summarize_proxy_response_error(status_code: int, body_text: str, payload: Any = None) -> str:
    message = _extract_proxy_error_message(payload)
    if not message:
        try:
            message = _extract_proxy_error_message(json.loads(body_text))
        except Exception:
            message = ""
    if not message:
        message = (body_text or "").strip()[:600]
    message = " ".join(message.split())
    return f"HTTP {status_code} - {message}" if message else f"HTTP {status_code}"


async def _fetch_proxy_model_names(
    client: httpx.AsyncClient,
    base_url: str,
    request_key: Optional[str],
) -> List[str]:
    response = await client.get(
        f"{_proxy_api_base(base_url)}/models",
        headers=_proxy_headers(request_key),
    )
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    names: List[str] = []
    for item in (payload.get("models") or []) if isinstance(payload, dict) else []:
        name = _normalize_proxy_model_name((item or {}).get("name"))
        if name and name not in names:
            names.append(name)
    return names


def _guess_proxy_image_model(
    model_names: List[str],
    preferred: Optional[str],
    family: str,
) -> str:
    preferred_name = _normalize_proxy_model_name(preferred)
    if preferred_name and preferred_name in model_names:
        return preferred_name

    if family == "flash":
        keywords = ("flash-image", "flash_image")
    else:
        keywords = ("pro-image", "pro_image")

    for name in model_names:
        lower = name.lower()
        if any(keyword in lower for keyword in keywords):
            return name
    return ""


def _select_proxy_model_candidates(
    model_key: str,
    proxy_config: Dict[str, Any],
    model_names: Optional[List[str]],
) -> List[str]:
    flash_model = _normalize_proxy_model_name(proxy_config.get("flash_model"))
    pro_model = _normalize_proxy_model_name(proxy_config.get("pro_model"))
    available = list(model_names or [])

    requested = flash_model if model_key == "flash" else pro_model
    fallback = pro_model if model_key == "flash" else flash_model
    candidates: List[str] = []

    def add(value: Optional[str]):
        name = _normalize_proxy_model_name(value)
        if name and name not in candidates:
            candidates.append(name)

    add(requested)

    if available:
        requested_guess = _guess_proxy_image_model(available, requested, model_key)
        fallback_guess = _guess_proxy_image_model(available, fallback, "pro" if model_key == "flash" else "flash")
        add(requested_guess)

        if model_key == "flash":
            add(fallback_guess)
            add(fallback)
        else:
            add(fallback_guess)
    else:
        if model_key == "flash":
            add(fallback)

    return candidates


def _collect_local_antigravity_proxy_diagnostics() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "found": False,
        "base_dir": None,
        "enabled_account_count": 0,
        "disabled_account_count": 0,
        "preferred_account_id": None,
        "enabled_accounts": [],
        "disabled_accounts": [],
        "enabled_image_models": [],
    }

    base_dir = ""
    for candidate in LOCAL_ANTIGRAVITY_DIRS:
        if os.path.isdir(os.path.join(candidate, "accounts")):
            base_dir = candidate
            break

    if not base_dir:
        return result

    result["found"] = True
    result["base_dir"] = base_dir
    accounts_dir = os.path.join(base_dir, "accounts")
    gui_config_path = os.path.join(base_dir, "gui_config.json")

    try:
        if os.path.exists(gui_config_path):
            with open(gui_config_path, "r", encoding="utf-8") as f:
                gui_config = json.load(f)
            result["preferred_account_id"] = gui_config.get("preferred_account_id")
    except Exception as e:
        result["gui_config_error"] = str(e)

    enabled_models: Dict[str, int] = {}

    for path in sorted(glob.glob(os.path.join(accounts_dir, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        quota_models = ((data.get("quota") or {}).get("models") or [])
        image_models: Dict[str, int] = {}
        for item in quota_models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if "image" not in name.lower():
                continue
            try:
                percentage = int(item.get("percentage") or 0)
            except Exception:
                percentage = 0
            image_models[name] = percentage

        account_summary = {
            "id": data.get("id"),
            "email": data.get("email"),
            "proxy_disabled": bool(data.get("proxy_disabled")),
            "image_models": image_models,
        }

        if account_summary["proxy_disabled"]:
            result["disabled_accounts"].append(account_summary)
            result["disabled_account_count"] += 1
            continue

        result["enabled_accounts"].append(account_summary)
        result["enabled_account_count"] += 1
        for name, percentage in image_models.items():
            if percentage > 0:
                enabled_models[name] = max(enabled_models.get(name, 0), percentage)

    result["enabled_image_models"] = sorted(enabled_models.keys())
    return result


def _resolve_provider_mode(provider_mode: Optional[str], nanobanana_api_key: Optional[str]) -> str:
    mode = str(provider_mode or "auto").strip().lower()
    if mode in ("vertex", "direct", "official"):
        return "direct"
    if mode in ("aistudio", "ai-studio", "google-ai-studio", "googleaistudio"):
        return "aistudio"
    if mode == "nanobanana":
        return "nanobanana"
    if mode == "proxy":
        return "proxy"

    proxy_config = _load_local_proxy_config()
    if proxy_config.get("enabled"):
        return "proxy"
    if str(nanobanana_api_key or "").strip():
        return "nanobanana"
    return "direct"


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    asyncio.create_task(_periodic_cleanup())
    load_catalog()

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/history-files", StaticFiles(directory=HISTORY_FILES_DIR), name="history-files")


# ===== Task Store =====
TASKS: Dict[str, Dict[str, Any]] = {}
TASKS_COLLECTION = "generation_tasks"

ERROR_LOGS: List[Dict[str, Any]] = []
KEY_USAGE: Dict[str, Dict[str, Any]] = {}

MODEL_PRICING = {
    "flash": 0.067,
    "pro": 0.134,
}

# Model limits aligned with Gemini image model quota panel (RPM / TPM / RPD).
MODEL_LIMITS = {
    "flash": {"rpm": 100, "tpm": 200000, "rpd": 1000},
    "pro": {"rpm": 20, "tpm": 100000, "rpd": 250},
}

PT_ZONE = ZoneInfo("America/Los_Angeles")
RATE_LIMIT_STATE: Dict[str, Dict[str, Dict[str, Any]]] = {}
RATE_LIMIT_LOCK = asyncio.Lock()


def _mask_key(api_key: str) -> str:
    k = (api_key or "").strip()
    if not k:
        return "N/A"
    if len(k) <= 8:
        return f"{k[:2]}***{k[-2:]}"
    return f"{k[:4]}...{k[-4:]}"


def _record_key_usage(api_key: Optional[str], model_key: str, success: bool):
    key = (api_key or "").strip()
    if not key or key.lower() in ("vertex-ai", "mock"):
        return
    row = KEY_USAGE.get(key) or {
        "key_masked": _mask_key(key),
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
    row["cost"] += float(MODEL_PRICING.get(model_key, MODEL_PRICING["flash"]))
    row["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    KEY_USAGE[key] = row


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


def _rate_identity(
    api_key: Optional[str],
    nanobanana_api_key: Optional[str],
    proxy_api_key: Optional[str] = None,
    provider_mode: Optional[str] = None,
) -> str:
    k = (api_key or "").strip()
    nk = (nanobanana_api_key or "").strip()
    pk = (proxy_api_key or "").strip()
    mode = str(provider_mode or "").strip().lower()
    if mode == "proxy" and pk:
        return f"proxy:{pk}"
    if k and k.lower() not in ("vertex-ai", "mock"):
        return f"api:{k}"
    if nk:
        return f"nano:{nk}"
    if pk:
        return f"proxy:{pk}"
    return "default"


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
    now_ts = time.time()
    minute_id = int(now_ts // 60)
    day_key = _pt_day_key(now_ts)

    model_state = RATE_LIMIT_STATE.get(identity, {}).get(model_key, {})
    rpm_used = int(model_state.get("rpm_used", 0) if model_state.get("minute_id") == minute_id else 0)
    tpm_used = int(model_state.get("tpm_used", 0) if model_state.get("minute_id") == minute_id else 0)
    rpd_used = int(model_state.get("rpd_used", 0) if model_state.get("day_key") == day_key else 0)

    return {
        "model": model_key,
        "model_name": MODEL_MAP.get(model_key, MODEL_MAP[DEFAULT_MODEL])["name"],
        "rpm_limit": int(limits["rpm"]),
        "tpm_limit": int(limits["tpm"]),
        "rpd_limit": int(limits["rpd"]),
        "rpm_used": rpm_used,
        "tpm_used": tpm_used,
        "rpd_used": rpd_used,
        "minute_reset_seconds": _seconds_until_next_minute(now_ts),
        "daily_reset_seconds": _seconds_until_next_pt_midnight(now_ts),
        "daily_reset_timezone": "PT",
    }


async def _check_and_consume_rate_limit(
    identity: str,
    model_key: str,
    token_cost: int,
) -> Dict[str, Any]:
    limits = MODEL_LIMITS.get(model_key, MODEL_LIMITS[DEFAULT_MODEL])
    now_ts = time.time()
    minute_id = int(now_ts // 60)
    day_key = _pt_day_key(now_ts)

    async with RATE_LIMIT_LOCK:
        identity_state = RATE_LIMIT_STATE.setdefault(identity, {})
        m = identity_state.setdefault(model_key, {
            "minute_id": minute_id,
            "day_key": day_key,
            "rpm_used": 0,
            "tpm_used": 0,
            "rpd_used": 0,
        })

        if m.get("minute_id") != minute_id:
            m["minute_id"] = minute_id
            m["rpm_used"] = 0
            m["tpm_used"] = 0

        if m.get("day_key") != day_key:
            m["day_key"] = day_key
            m["rpd_used"] = 0

        rpm_used = int(m.get("rpm_used", 0))
        tpm_used = int(m.get("tpm_used", 0))
        rpd_used = int(m.get("rpd_used", 0))

        if rpm_used + 1 > int(limits["rpm"]):
            raise RuntimeError(
                f"触发 RPM 限制: {rpm_used}/{limits['rpm']}，请等待 {_seconds_until_next_minute(now_ts)} 秒后重试"
            )
        if tpm_used + token_cost > int(limits["tpm"]):
            raise RuntimeError(
                f"触发 TPM 限制: {tpm_used}/{limits['tpm']}，当前请求估算 {token_cost} tokens，请等待 {_seconds_until_next_minute(now_ts)} 秒后重试"
            )
        if rpd_used + 1 > int(limits["rpd"]):
            raise RuntimeError(
                f"触发 RPD 限制: {rpd_used}/{limits['rpd']}，将在 PT 零点后重置（约 {_seconds_until_next_pt_midnight(now_ts)} 秒）"
            )

        m["rpm_used"] = rpm_used + 1
        m["tpm_used"] = tpm_used + token_cost
        m["rpd_used"] = rpd_used + 1

        return _rate_status_snapshot(identity, model_key)


def _task_public_payload(task: Optional[dict]) -> dict:
    if not isinstance(task, dict):
        return {}

    logs = task.get("logs", [])
    if not isinstance(logs, list):
        logs = [str(logs)]

    return {
        "status": task.get("status", "pending"),
        "progress": int(task.get("progress", 0) or 0),
        "message": str(task.get("message", "")),
        "result_url": task.get("result_url"),
        "result_cloud_url": task.get("result_cloud_url"),
        "result_display_url": task.get("result_display_url"),
        "result_data_url": task.get("result_data_url"),
        "freedom": int(task.get("freedom", 5) or 5),
        "logs": [str(x) for x in logs][-500:],
        "error": task.get("error"),
        "created_at": float(task.get("created_at", 0) or 0),
    }


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
    """Upload bytes to GCS under the given prefix. Returns public URL or None."""
    if not storage_client or not RESULTS_GCS_BUCKET:
        return None

    date_prefix = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y/%m/%d")
    blob_name = "/".join(part for part in [prefix, date_prefix, filename] if part)
    try:
        bucket = storage_client.bucket(RESULTS_GCS_BUCKET)
        blob = bucket.blob(blob_name)
        blob.cache_control = "public, max-age=31536000, immutable"
        blob.upload_from_string(img_bytes, content_type=content_type)
        return _public_gcs_url(RESULTS_GCS_BUCKET, blob_name)
    except Exception as e:
        print(f"[Storage] upload to GCS failed ({prefix}/{filename}): {e}")
        return None


def _upload_generated_bytes_to_gcs(img_bytes: bytes, filename: str) -> Optional[str]:
    return _upload_bytes_to_gcs(img_bytes, filename, RESULTS_GCS_PREFIX, "image/png")


def _content_type_from_ext(ext: str) -> str:
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
        ext.lstrip(".").lower(), "image/png"
    )


def _save_generated_bytes(img_bytes: bytes) -> Dict[str, str]:
    filename = f"generated_{uuid.uuid4().hex}.png"
    path = os.path.join(ASSET_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    cloud_url = _upload_generated_bytes_to_gcs(img_bytes, filename)
    local_url = f"/assets/{filename}"
    # Avoid keeping large base64 strings in memory; generate data_url only on demand
    return {
        "result_url": local_url,
        "result_cloud_url": cloud_url,
        "result_display_url": cloud_url or local_url,
        "result_data_url": None,
    }


def _build_direct_generate_config():
    from google.genai import types as genai_types

    return genai_types.GenerateContentConfig(
        safety_settings=[
            genai_types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            genai_types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            genai_types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            genai_types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        ],
        response_modalities=["TEXT", "IMAGE"],
    )


def _extract_error_status_text(error: Exception) -> str:
    raw = " ".join(str(error or "").split())
    match = re.search(r"'status':\s*'([^']+)'", raw)
    if match:
        return match.group(1).strip()
    match = re.search(r'"status":\s*"([^"]+)"', raw)
    if match:
        return match.group(1).strip()
    return ""


def _summarize_direct_generation_error(error: Exception, provider: str) -> str:
    raw = " ".join(str(error or "").split())
    lower = raw.lower()
    provider_label = "Google AI Studio" if provider == "aistudio" else "Vertex AI"

    if "consumer_invalid" in lower or ("permission_denied" in lower and "aiplatform.googleapis.com" in lower):
        return (
            "Vertex AI 返回了 403 / CONSUMER_INVALID。当前请求很可能走到了 Vertex 路径，"
            "但当前项目、账单、区域或服务账号并不满足 Vertex AI 的调用要求。"
            "如果你使用的是 Google AI Studio / Gemini API 密钥，请切换到 Google AI Studio 接口；"
            "如果你本来就要走 Vertex，请检查 Cloud Run 运行身份、Vertex AI API 启用状态和项目配置。"
        )
    if "permission_denied" in lower or "403" in lower:
        return f"{provider_label} 返回了 HTTP 403。请检查当前认证方式、IAM 权限以及相关 API 是否已启用。"
    if "resource_exhausted" in lower or "429" in lower or "quota" in lower or "rate" in lower:
        return f"{provider_label} 触发了配额或限流。请稍后重试，或切换到其他可用的 API 密钥或项目。"
    if "api key not valid" in lower or "invalid api key" in lower:
        return f"{provider_label} 拒绝了当前 API 密钥。请确认密钥有效，并且它属于当前所选通道。"
    if "returned empty parts" in lower or "does not contain image bytes" in lower:
        return f"{provider_label} 已返回响应，但没有生成可用的图片数据。"

    status_text = _extract_error_status_text(error)
    if status_text:
        return f"{provider_label} 请求失败，状态为 {status_text}：{raw[:420]}"
    return f"{provider_label} 请求失败：{raw[:420]}"

def _extract_image_bytes_from_vertex_response(response) -> bytes:
    parts = getattr(response, "parts", None)
    if not parts:
        reason = None
        if getattr(response, "candidates", None):
            cand = response.candidates[0]
            reason = _finish_reason_desc(getattr(cand, "finish_reason", None))
        raise RuntimeError(f"Vertex 返回了空的 parts，finish_reason={reason}")

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

    raise RuntimeError("Vertex response does not contain image bytes")


def _resolve_ai_studio_generation_config(model_key: str) -> Dict[str, Any]:
    config = _load_ai_studio_config()
    flash_model = str(config.get("flash_model") or "").strip()
    pro_model = str(config.get("pro_model") or "").strip()
    model_ids = [flash_model] if model_key == "flash" else [pro_model]

    for model_id in MODEL_MAP.get(model_key, {}).get("ids") or []:
        if model_id and model_id not in model_ids:
            model_ids.append(model_id)

    return {
        "api_key": str(config.get("api_key") or "").strip(),
        "model_ids": [item for item in model_ids if item],
    }


def _resolve_direct_api_key(api_key: Optional[str], provider_mode: Optional[str]) -> str:
    mode = str(provider_mode or "").strip().lower()
    supplied = str(api_key or "").strip()
    if supplied:
        return supplied
    if mode == "aistudio":
        return str(_load_ai_studio_config().get("api_key") or "").strip()
    return ""


def _usage_key_for_mode(
    api_key: Optional[str],
    nanobanana_api_key: Optional[str],
    proxy_api_key: Optional[str],
    provider_mode: Optional[str],
) -> str:
    mode = str(provider_mode or "").strip().lower()
    if mode == "proxy":
        return str(proxy_api_key or "").strip()
    if mode == "nanobanana":
        return str(nanobanana_api_key or "").strip()
    if mode == "aistudio":
        return _resolve_direct_api_key(api_key, mode)
    return ""


def _extract_image_bytes_from_gemini_payload(payload: Dict[str, Any]) -> bytes:
    root = payload.get("response") if isinstance(payload, dict) and isinstance(payload.get("response"), dict) else payload
    candidates = root.get("candidates") or []
    empty_parts = False
    finish_reasons: List[str] = []
    for candidate in candidates:
        finish_reason = str(candidate.get("finishReason") or "").strip()
        if finish_reason:
            finish_reasons.append(finish_reason)
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        if isinstance(parts, list) and len(parts) == 0:
            empty_parts = True
        for part in parts:
            inline = part.get("inline_data") or part.get("inlineData") or {}
            mime_type = str(inline.get("mime_type") or inline.get("mimeType") or "")
            data = inline.get("data")
            if mime_type.startswith("image/") and data:
                try:
                    return base64.b64decode(data)
                except Exception as e:
                    raise RuntimeError(f"Proxy image decode failed: {e}") from e

    prompt_feedback = root.get("promptFeedback") or {}
    block_reason = prompt_feedback.get("blockReason")
    if block_reason:
        raise RuntimeError(f"Proxy request blocked: {block_reason}")

    texts: List[str] = []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = str(part.get("text") or "").strip()
            if text:
                texts.append(text)
    if texts:
            raise RuntimeError(f"反代返回了文本而不是图片：{' | '.join(texts)[:400]}")

    if empty_parts:
        suffix = f" (finishReason={', '.join(finish_reasons)})" if finish_reasons else ""
        raise RuntimeError(f"反代返回了空的 Gemini candidates，且没有图片字节数据{suffix}")

    raise RuntimeError("Proxy response does not contain image bytes")


def _extract_image_bytes_from_openai_payload(payload: Dict[str, Any]) -> bytes:
    choices = payload.get("choices") or []
    pattern = re.compile(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)")
    texts: List[str] = []

    for choice in choices:
        message = (choice or {}).get("message") or {}
        content = message.get("content")
        chunks: List[str] = []
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    text = str(item.get("text") or item.get("content") or "").strip()
                    if text:
                        chunks.append(text)

        for chunk in chunks:
            match = pattern.search(chunk)
            if match:
                try:
                    return base64.b64decode(match.group(1))
                except Exception as e:
                    raise RuntimeError(f"Proxy image decode failed: {e}") from e
            stripped = chunk.strip()
            if stripped:
                texts.append(stripped)

    if texts:
            raise RuntimeError(f"反代返回了文本而不是图片：{' | '.join(texts)[:400]}")
    raise RuntimeError("Proxy response does not contain image bytes")


def _extract_image_bytes_from_openai_images_payload(payload: Dict[str, Any]) -> bytes:
    data_items = payload.get("data") or []
    urls: List[str] = []

    for item in data_items if isinstance(data_items, list) else []:
        if not isinstance(item, dict):
            continue

        b64_json = item.get("b64_json")
        if b64_json:
            try:
                return base64.b64decode(b64_json)
            except Exception as e:
                raise RuntimeError(f"Proxy image decode failed: {e}") from e

        url = str(item.get("url") or "").strip()
        if url:
            urls.append(url)

    if urls:
                raise RuntimeError(f"反代返回了图片 URL，而不是内联字节数据：{' | '.join(urls[:2])}")

    error_message = _extract_proxy_error_message(payload)
    if error_message:
        raise RuntimeError(error_message)

    raise RuntimeError("Proxy images response does not contain image bytes")


def _nearest_proxy_aspect_ratio(image_path: str) -> str:
    ratios = {
        "1:1": 1.0,
        "3:4": 3 / 4,
        "4:3": 4 / 3,
        "9:16": 9 / 16,
        "16:9": 16 / 9,
        "21:9": 21 / 9,
    }
    try:
        with PIL.Image.open(image_path) as img:
            width = max(1, int(getattr(img, "width", 1) or 1))
            height = max(1, int(getattr(img, "height", 1) or 1))
    except Exception:
        return "3:4"

    target = width / height
    return min(ratios.items(), key=lambda item: abs(item[1] - target))[0]


def _prepare_proxy_edit_upload(path: str, target_format: str) -> Dict[str, Any]:
    fmt = str(target_format or "").strip().upper()
    filename = "image.png" if fmt == "PNG" else "image.jpg"
    mime_type = "image/png" if fmt == "PNG" else "image/jpeg"

    with PIL.Image.open(path) as img:
        buffer = io.BytesIO()
        if fmt == "PNG":
            normalized = img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")
            normalized.save(buffer, format="PNG")
        else:
            normalized = img.convert("RGB")
            normalized.save(buffer, format="JPEG", quality=95)

    return {
        "filename": filename,
        "mime_type": mime_type,
        "data": buffer.getvalue(),
    }


def _build_local_proxy_tryon_error(errors: List[str], diagnostics: Optional[Dict[str, Any]] = None) -> RuntimeError:
    detail = " | ".join(str(err or "").strip() for err in errors if str(err or "").strip())
    detail = " ".join(detail.split())[:1200]
    message = (
        "当前本地反代已连通，但没有返回可用的试衣编辑结果。"
        "本项目已停止使用会忽略参考图的文生图回退，避免继续生成与模特图、服装图完全不符的图片。"
        "请在 Antigravity 中确认 `/v1/images/edits` 可用，且账号池对图片模型具备真实的多图编辑能力；"
        "否则请切换到官方直连或 Nano Banana。"
    )
    if isinstance(diagnostics, dict) and diagnostics.get("found"):
        enabled_accounts = diagnostics.get("enabled_accounts") or []
        enabled_models = diagnostics.get("enabled_image_models") or []
        enabled_emails = [str(item.get("email") or item.get("id") or "未知账号").strip() for item in enabled_accounts if isinstance(item, dict)]
        account_hint = (
            f" 当前本机 Antigravity 反代池已启用账号数: {len(enabled_accounts)}。"
            f" 已启用账号的图片模型: {', '.join(enabled_models) if enabled_models else '无'}。"
        )
        if enabled_emails:
            account_hint += f" 当前实际启用账号: {', '.join(enabled_emails)}。"
            if len(enabled_emails) == 1:
                account_hint += " 这说明当前请求已经进入该账号对应的 API 反代池。"
        message += account_hint
    if detail:
        message += f" 原始错误: {detail}"
    return RuntimeError(message)


async def _call_local_proxy_image(
    prompt: str,
    model_path: str,
    garment_path: str,
    model_key: str,
    proxy_config: Dict[str, Any],
    proxy_api_key_override: Optional[str],
) -> bytes:
    base_url = str(proxy_config.get("base_url") or "").strip()
    if not base_url:
        raise RuntimeError("本地反代的接口地址为空")

    timeout_seconds = int(proxy_config.get("timeout_seconds") or DEFAULT_LOCAL_PROXY_CONFIG["timeout_seconds"])
    request_key = str(proxy_api_key_override or proxy_config.get("api_key") or "").strip()

    aspect_ratio = _nearest_proxy_aspect_ratio(model_path)
    main_upload = _prepare_proxy_edit_upload(model_path, "PNG")
    garment_upload = _prepare_proxy_edit_upload(garment_path, "JPEG")

    edit_headers = _proxy_headers(request_key)
    errors: List[str] = []
    diagnostics = _collect_local_antigravity_proxy_diagnostics()

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        available_models: List[str] = []
        try:
            available_models = await _fetch_proxy_model_names(client, base_url, request_key)
        except Exception as e:
            print(f"[LocalProxy] model list probe failed: {e}")

        candidate_models = _select_proxy_model_candidates(model_key, proxy_config, available_models)
        enabled_models = set(diagnostics.get("enabled_image_models") or [])
        if enabled_models:
            filtered_models = [name for name in candidate_models if name in enabled_models]
            if filtered_models:
                candidate_models = filtered_models
        if not candidate_models:
            raise _build_local_proxy_tryon_error(
                [f"未在本机 Antigravity 已启用反代账号中发现可用图片模型，mode={model_key}"],
                diagnostics=diagnostics,
            )

        for idx, proxy_model in enumerate(candidate_models):
            protocol_errors: List[str] = []

            edit_endpoint = f"{_proxy_openai_base(base_url)}/images/edits"
            response = await client.post(
                edit_endpoint,
                headers=edit_headers,
                data={
                    "prompt": prompt,
                    "model": proxy_model,
                    "n": "1",
                    "response_format": "b64_json",
                    "aspect_ratio": aspect_ratio,
                },
                files=[
                    ("image", (main_upload["filename"], main_upload["data"], main_upload["mime_type"])),
                    ("image1", (garment_upload["filename"], garment_upload["data"], garment_upload["mime_type"])),
                ],
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as e:
                    raise RuntimeError(f"本地反代返回了无效的 JSON：{e}") from e
                try:
                    img_bytes = _extract_image_bytes_from_openai_images_payload(data)
                except Exception as e:
                    error_summary = str(e)
                    protocol_errors.append(f"images.edits: {error_summary}")
                else:
                    if idx > 0:
                        print(f"[LocalProxy] fallback succeeded: {candidate_models[0]} -> {proxy_model}")
                    return img_bytes
            else:
                body = response.text[:1200]
                parsed_payload = None
                try:
                    parsed_payload = response.json()
                except Exception:
                    parsed_payload = None
                error_summary = _summarize_proxy_response_error(response.status_code, body, parsed_payload)
                protocol_errors.append(f"images.edits: {error_summary}")

            error_summary = " ; ".join(protocol_errors)
            errors.append(f"{proxy_model}: {error_summary}")
            if idx + 1 < len(candidate_models):
                print(f"[LocalProxy] retrying with fallback model after {proxy_model} failed: {error_summary}")

    raise _build_local_proxy_tryon_error(errors, diagnostics=diagnostics)

async def _call_vertex_image(prompt: str, model_path: str, garment_path: str, model_key: str) -> bytes:
    model_info = MODEL_MAP.get(model_key, MODEL_MAP[DEFAULT_MODEL])
    model_ids = list(model_info.get("ids") or [])
    if not model_ids:
        raise RuntimeError(f"Vertex 模型配置缺少 model_key={model_key} 对应的模型 ID")

    img_model = PIL.Image.open(model_path)
    img_garment = PIL.Image.open(garment_path)
    request_contents = [prompt, img_model, img_garment]

    loop = asyncio.get_event_loop()
    last_error = None
    config = _build_direct_generate_config()

    for model_id in model_ids:
        for attempt in range(3):
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda current_model=model_id: vertex_client.models.generate_content(
                        model=current_model,
                        contents=request_contents,
                        config=config,
                    ),
                )
                return _extract_image_bytes_from_vertex_response(response)
            except Exception as e:
                last_error = e
                err = str(e).lower()
                is_retryable = ("429" in err) or ("resource_exhausted" in err) or ("rate" in err) or ("quota" in err)
                missing_or_denied = (
                    ("permission_denied" in err)
                    or ("aiplatform.endpoints.predict" in err)
                    or ("not found" in err)
                    or ("does not exist" in err)
                    or ("or it may not exist" in err)
                )
                if is_retryable and attempt < 2:
                    await asyncio.sleep(2 + attempt * 2)
                    continue
                if missing_or_denied:
                    break
                break

    raise RuntimeError(_summarize_direct_generation_error(last_error or RuntimeError("unknown vertex error"), "direct"))


async def _call_ai_studio_image(
    prompt: str,
    model_path: str,
    garment_path: str,
    model_key: str,
    api_key: str,
) -> bytes:
    request_key = str(api_key or "").strip()
    if not request_key:
        raise RuntimeError("Google AI Studio 接口缺少 Gemini API 密钥。请在左侧 AI Studio 侧边栏保存默认密钥，或在主面板中填写 AI Studio 密钥。")

    resolved = _resolve_ai_studio_generation_config(model_key)
    model_ids = list(resolved.get("model_ids") or [])
    if not model_ids:
        raise RuntimeError(f"AI Studio 模型配置缺少 model_key={model_key} 对应的模型 ID")

    client = genai.Client(api_key=request_key)
    img_model = PIL.Image.open(model_path)
    img_garment = PIL.Image.open(garment_path)
    request_contents = [prompt, img_model, img_garment]

    loop = asyncio.get_event_loop()
    last_error = None
    config = _build_direct_generate_config()

    for model_id in model_ids:
        for attempt in range(3):
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda current_model=model_id: client.models.generate_content(
                        model=current_model,
                        contents=request_contents,
                        config=config,
                    ),
                )
                return _extract_image_bytes_from_vertex_response(response)
            except Exception as e:
                last_error = e
                err = str(e).lower()
                is_retryable = ("429" in err) or ("resource_exhausted" in err) or ("rate" in err) or ("quota" in err)
                missing_or_denied = (
                    ("permission_denied" in err)
                    or ("api key not valid" in err)
                    or ("invalid api key" in err)
                    or ("not found" in err)
                    or ("does not exist" in err)
                    or ("or it may not exist" in err)
                )
                if is_retryable and attempt < 2:
                    await asyncio.sleep(2 + attempt * 2)
                    continue
                if missing_or_denied:
                    break
                break

    raise RuntimeError(_summarize_direct_generation_error(last_error or RuntimeError("unknown ai studio error"), "aistudio"))


async def _call_nanobanana_image(
    prompt: str,
    model_key: str,
    model_filename: str,
    garment_filename: str,
    base_url: str,
    nanobanana_api_key: str,
) -> bytes:
    endpoint = "generate-2" if model_key == "flash" else "generate-pro"
    image_urls = [
        f"{base_url}/uploads/{model_filename}",
        f"{base_url}/uploads/{garment_filename}",
    ]

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        submit_resp = await client.post(
            f"https://api.nanobananaapi.ai/api/v1/nanobanana/{endpoint}",
            headers={
                "Authorization": f"Bearer {nanobanana_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": prompt,
                "type": "TEXTTOIAMGE",
                "numImages": 1,
                "imageUrls": image_urls,
            },
        )

        if submit_resp.status_code != 200:
            raise RuntimeError(f"NanoBanana submit failed: HTTP {submit_resp.status_code} - {submit_resp.text}")

        submit_data = submit_resp.json()
        if submit_data.get("code") != 200:
            raise RuntimeError(f"NanoBanana submit error: {submit_data.get('msg')}")

        task_id = submit_data.get("data", {}).get("taskId")
        if not task_id:
            raise RuntimeError("NanoBanana submit response missing taskId")

        result_image_url = None
        for _ in range(100):
            poll_resp = await client.get(
                f"https://api.nanobananaapi.ai/api/v1/nanobanana/record-info?taskId={task_id}",
                headers={"Authorization": f"Bearer {nanobanana_api_key}"},
            )
            poll_data = poll_resp.json()

            if poll_data.get("code") != 200:
                raise RuntimeError(f"NanoBanana polling error: {poll_data.get('msg')}")

            flag = poll_data.get("successFlag", 0)
            if flag == 1:
                result_image_url = poll_data.get("response", {}).get("resultImageUrl")
                break
            if flag in (2, 3):
                raise RuntimeError(f"NanoBanana task failed: {poll_data.get('errorMessage', 'unknown')}" )

            await asyncio.sleep(3)

        if not result_image_url:
            raise RuntimeError("NanoBanana polling timeout")

        image_resp = await client.get(result_image_url)
        if image_resp.status_code != 200 or not image_resp.content:
            raise RuntimeError("NanoBanana image download failed")
        return image_resp.content


async def _ensure_local_file(filename: str, cloud_url: Optional[str]) -> str:
    """Ensure a file exists locally in UPLOAD_DIR; download from cloud_url if missing."""
    local_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(local_path):
        return local_path
    url = str(cloud_url or "").strip()
    if not url:
        return local_path  # caller will detect missing file
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code == 200 and resp.content:
            with open(local_path, "wb") as f:
                f.write(resp.content)
            print(f"[GCS-Restore] restored {filename} from cloud URL ({len(resp.content)} bytes)")
    except Exception as e:
        print(f"[GCS-Restore] failed to restore {filename}: {e}")
    return local_path


async def _generate_tryon_image_bytes(
    model_filename: str,
    garment_filename: str,
    custom_prompt: Optional[str],
    prompt_mode: str,
    freedom: int,
    garment_type: Optional[str],
    model_key: str,
    provider_mode: Optional[str],
    proxy_api_key: Optional[str],
    nanobanana_api_key: Optional[str],
    api_key: Optional[str],
    base_url: str,
    model_cloud_url: Optional[str] = None,
    garment_cloud_url: Optional[str] = None,
) -> bytes:
    model_path = await _ensure_local_file(model_filename, model_cloud_url)
    garment_path = await _ensure_local_file(garment_filename, garment_cloud_url)
    if not os.path.exists(model_path):
        raise RuntimeError(f"未找到模特图片：{model_filename}")
    if not os.path.exists(garment_path):
        raise RuntimeError(f"未找到服装图片：{garment_filename}")

    prompt = _build_prompt(custom_prompt, prompt_mode or "append", freedom, garment_type)
    mode = str(provider_mode or "").strip().lower()

    if mode == "proxy":
        proxy_config = _load_local_proxy_config()
        return await _call_local_proxy_image(
            prompt=prompt,
            model_path=model_path,
            garment_path=garment_path,
            model_key=model_key,
            proxy_config=proxy_config,
            proxy_api_key_override=proxy_api_key,
        )

    if mode == "nanobanana" and not (nanobanana_api_key and nanobanana_api_key.strip()):
        raise RuntimeError("Nano Banana mode is selected, but no Nano Banana API Key is configured")

    if mode == "nanobanana" and nanobanana_api_key and nanobanana_api_key.strip():
        return await _call_nanobanana_image(
            prompt=prompt,
            model_key=model_key,
            model_filename=model_filename,
            garment_filename=garment_filename,
            base_url=base_url,
            nanobanana_api_key=nanobanana_api_key.strip(),
        )

    if mode == "aistudio":
        return await _call_ai_studio_image(
            prompt=prompt,
            model_path=model_path,
            garment_path=garment_path,
            model_key=model_key,
            api_key=_resolve_direct_api_key(api_key, mode),
        )

    return await _call_vertex_image(prompt, model_path, garment_path, model_key)


def _validate_single_model(target_image: List[str]):
    if not target_image:
        raise ValueError("请上传 1 张模特图片")
    if len(target_image) != 1:
        raise ValueError(f"模特图片数量必须为 1 张，当前为 {len(target_image)} 张")


async def _process_task(
    task_id: str,
    base_url: str,
    target_image: List[str],
    reference_image: str,
    api_key: Optional[str],
    proxy_api_key: Optional[str],
    nanobanana_api_key: Optional[str],
    custom_prompt: Optional[str],
    prompt_mode: Optional[str],
    freedom: Optional[int],
    garment_type: Optional[str],
    model: Optional[str],
    provider_mode: Optional[str],
    target_image_cloud_url: Optional[str] = None,
    reference_image_cloud_url: Optional[str] = None,
):
    task = TASKS[task_id]
    model_key = model if model in MODEL_MAP else DEFAULT_MODEL
    effective_mode = _resolve_provider_mode(provider_mode, nanobanana_api_key)
    effective_direct_api_key = _resolve_direct_api_key(api_key, effective_mode)

    def update(progress: Optional[int] = None, message: Optional[str] = None, status: Optional[str] = None):
        if progress is not None:
            task["progress"] = int(progress)
        if message is not None:
            task["message"] = str(message)
            task["logs"].append(str(message))
        if status is not None:
            task["status"] = status
        _persist_task(task_id)

    try:
        update(5, "任务初始化完成", "processing")
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")

        current_api_key = effective_direct_api_key or DEFAULT_API_KEY

        if current_api_key.lower() == "mock":
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = "模拟生成完成"
            task["result_url"] = "/assets/demo_result.png"
            _persist_task(task_id)
            return

        freedom_level = max(0, min(10, int(freedom or 5)))
        prompt_text = _build_prompt(custom_prompt, prompt_mode or "append", freedom_level, garment_type)
        rate_key = effective_direct_api_key if effective_mode == "aistudio" else api_key
        rate_identity = _rate_identity(rate_key, nanobanana_api_key, proxy_api_key, effective_mode)
        token_cost = _estimate_token_cost(prompt_text)

        update(18, "检查额度限制...")
        await _check_and_consume_rate_limit(
            identity=rate_identity,
            model_key=model_key,
            token_cost=token_cost,
        )

        update(25, "正在生成图片...")
        img_bytes = await _generate_tryon_image_bytes(
            model_filename=target_image[0],
            garment_filename=reference_image,
            custom_prompt=custom_prompt,
            prompt_mode=prompt_mode or "append",
            freedom=freedom_level,
            garment_type=garment_type,
            model_key=model_key,
            provider_mode=effective_mode,
            proxy_api_key=proxy_api_key,
            nanobanana_api_key=nanobanana_api_key,
            api_key=effective_direct_api_key,
            base_url=base_url,
            model_cloud_url=target_image_cloud_url,
            garment_cloud_url=reference_image_cloud_url,
        )

        out = _save_generated_bytes(img_bytes)
        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "生成完成"
        task["result_url"] = out["result_url"]
        task["result_cloud_url"] = out.get("result_cloud_url")
        task["result_display_url"] = out.get("result_display_url")
        task["result_data_url"] = out["result_data_url"]
        task["freedom"] = freedom_level
        usage_key = _usage_key_for_mode(api_key, nanobanana_api_key, proxy_api_key, effective_mode)
        _record_key_usage(usage_key, model_key, True)
        _persist_task(task_id)
        _dur = (time.time() - float(task.get("created_at") or 0)) * 1000
        asyncio.create_task(_admin_report.report_tryon_task(
            task_id, "completed",
            result_image_url=out.get("result_cloud_url") or out.get("result_display_url") or "",
            duration_ms=_dur,
            model_used=model_key or "flash",
        ))

    except Exception as e:
        task["status"] = "failed"
        task["progress"] = 0
        task["message"] = str(e)
        task["error"] = str(e)
        task["logs"].append(f"Error: {e}")
        usage_key = _usage_key_for_mode(api_key, nanobanana_api_key, proxy_api_key, effective_mode)
        _record_key_usage(usage_key, model_key, False)
        _append_error_log(str(e), context="generation_task", detail=f"task_id={task_id}")
        _persist_task(task_id)
        _dur = (time.time() - float(task.get("created_at") or 0)) * 1000
        asyncio.create_task(_admin_report.report_tryon_task(
            task_id, "failed",
            error_type=type(e).__name__,
            error_detail=str(e)[:500],
            duration_ms=_dur,
            model_used=model_key or "flash",
        ))


@app.get("/")
async def read_root(request: Request):
    import asyncio
    asyncio.create_task(_admin_report.report_page_view(
        source="tryon_workbench",
        page="/",
        user_agent=request.headers.get("user-agent", ""),
        ip=request.client.host if request.client else "",
    ))
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "model-tryon-generator",
        "version": "3.1.0",
    }


@app.get("/api/products")
async def api_products(
    query: Optional[str] = None,
    gender: Optional[str] = None,
    platform: Optional[str] = None,
    style_type: Optional[str] = None,
    color: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    offset: int = 0,
    limit: int = 60,
):
    return list_products(
        query=query, gender=gender, platform=platform,
        style_type=style_type, color=color,
        price_min=price_min, price_max=price_max,
        offset=offset, limit=limit,
    )


@app.get("/api/products/filters")
async def api_product_filters():
    return get_filter_options()


@app.get("/api/result-data-url/{filename}")
async def get_result_data_url(filename: str):
    """Generate base64 data URL on demand instead of keeping it in memory."""
    safe_name = os.path.basename(filename)
    path = os.path.join(ASSET_DIR, safe_name)
    if not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    with open(path, "rb") as f:
        img_bytes = f.read()
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


@app.get("/api/local-proxy-config")
async def get_local_proxy_config():
    config = _load_local_proxy_config()
    return {
        "ok": True,
        "config": config,
        "has_api_key": bool(config.get("api_key")),
        "api_key_masked": _mask_secret(config.get("api_key", "")),
    }


@app.put("/api/local-proxy-config")
async def update_local_proxy_config(payload: Dict[str, Any]):
    try:
        config = _save_local_proxy_config(payload)
        return {
            "ok": True,
            "message": "本地反代配置已保存",
            "config": config,
            "has_api_key": bool(config.get("api_key")),
            "api_key_masked": _mask_secret(config.get("api_key", "")),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/api/local-proxy-config/test")
async def test_local_proxy_config(payload: Optional[Dict[str, Any]] = None):
    config = _sanitize_local_proxy_config(payload or _load_local_proxy_config())
    base_url = str(config.get("base_url") or "").strip()
    if not base_url:
        return JSONResponse(status_code=400, content={"ok": False, "error": "base_url is required"})

    request_key = str(config.get("api_key") or "").strip()
    headers = _proxy_headers(request_key)

    result: Dict[str, Any] = {
        "ok": False,
        "health": {"ok": False},
        "models": {"ok": False, "items": []},
        "tryon": {
            "ok": False,
            "strategy": "openai.images.edits",
            "warning": "模特试衣现在只会使用真正接收两张图片的编辑接口，不再回退到 /v1/chat/completions 文生图路径。",
            "note": "连接成功只代表反代服务在线；若图片编辑接口不可用，任务会明确失败，而不会生成与输入无关的图。",
        },
        "local_antigravity": _collect_local_antigravity_proxy_diagnostics(),
    }

    timeout_seconds = int(config.get("timeout_seconds") or DEFAULT_LOCAL_PROXY_CONFIG["timeout_seconds"])
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        try:
            health_resp = await client.get(f"{_proxy_root_base(base_url)}/health")
            if health_resp.status_code == 404:
                health_resp = await client.get(f"{_proxy_root_base(base_url)}/healthz")
            health_ok = health_resp.status_code == 200
            health_data = None
            try:
                health_data = health_resp.json()
            except Exception:
                health_data = health_resp.text[:400]
            result["health"] = {
                "ok": health_ok,
                "status_code": health_resp.status_code,
                "data": health_data,
            }
        except Exception as e:
            result["health"] = {"ok": False, "error": str(e)}

        try:
            models_resp = await client.get(f"{_proxy_api_base(base_url)}/models", headers=headers)
            models_data = models_resp.json() if models_resp.headers.get("content-type", "").startswith("application/json") else {}
            model_items = models_data.get("models") if isinstance(models_data, dict) else []
            model_names = []
            for item in model_items or []:
                name = _normalize_proxy_model_name((item or {}).get("name"))
                if not name:
                    continue
                if name not in model_names:
                    model_names.append(name)
            flash_model = str(config.get("flash_model") or "").strip()
            pro_model = str(config.get("pro_model") or "").strip()
            effective_flash = _select_proxy_model_candidates("flash", config, model_names)
            effective_pro = _select_proxy_model_candidates("pro", config, model_names)
            result["models"] = {
                "ok": models_resp.status_code == 200,
                "status_code": models_resp.status_code,
                "items": model_names[:80],
                "count": len(model_names),
                "contains_flash_model": flash_model in model_names if flash_model else False,
                "contains_pro_model": pro_model in model_names if pro_model else False,
                "effective_flash_model": effective_flash[0] if effective_flash else "",
                "effective_pro_model": effective_pro[0] if effective_pro else "",
                "flash_fallback_to_pro": bool(
                    effective_flash
                    and effective_flash[0] != _normalize_proxy_model_name(flash_model)
                    and effective_flash[0] == _normalize_proxy_model_name(pro_model)
                ),
                "candidate_flash_models": effective_flash,
                "candidate_pro_models": effective_pro,
            }
            result["tryon"]["ok"] = bool(models_resp.status_code == 200 and (effective_flash or effective_pro))
        except Exception as e:
            result["models"] = {"ok": False, "error": str(e), "items": []}

    result["ok"] = bool(result["health"].get("ok") or result["models"].get("ok"))
    if not result["ok"]:
        return JSONResponse(status_code=502, content=result)
    return result


async def _save_upload_file(file: UploadFile) -> Tuple[str, Optional[str]]:
    ext = pathlib.Path(file.filename or "").suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    data = await file.read()
    with open(path, "wb") as f:
        f.write(data)
    cloud_url = _upload_bytes_to_gcs(data, filename, UPLOADS_GCS_PREFIX, _content_type_from_ext(ext))
    return filename, cloud_url


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


async def _fetch_remote_image_bytes(raw_url: str) -> Tuple[bytes, str]:
    url = str(raw_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("自动导入只支持 http / https 图片地址")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)

    if response.status_code != 200:
        raise ValueError(f"远程图片下载失败 (HTTP {response.status_code})")

    content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise ValueError("远程地址返回的不是图片资源")

    image_bytes = response.content
    return image_bytes, content_type


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
async def intake_image(payload: Dict[str, Any]):
    try:
        image_url = str(payload.get("image_url") or "").strip()
        image_data_url = str(payload.get("image_data_url") or payload.get("image_base64") or "").strip()
        role = str(payload.get("role") or "image").strip() or "image"

        if image_url:
            image_bytes, content_type = await _fetch_remote_image_bytes(image_url)
            source_type = "url"
        elif image_data_url:
            image_bytes, content_type = _decode_recommended_image_data(image_data_url)
            source_type = "data_url"
        else:
            raise ValueError("缺少 image_url 或 image_data_url，无法自动预填图片")

        suffix = _validate_and_resolve_image_suffix(image_bytes, _guess_image_suffix(content_type))
        filename, cloud_url = _save_upload_bytes(image_bytes, suffix)
        return {
            "ok": True,
            "role": role,
            "source_type": source_type,
            "filename": filename,
            "url": f"/uploads/{quote(filename)}",
            "cloud_url": cloud_url,
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

@app.get("/api/ai-studio-config")
async def get_ai_studio_config():
    config = _load_ai_studio_config()
    return {
        "ok": True,
        "config": config,
        "has_api_key": bool(config.get("api_key")),
        "api_key_masked": _mask_secret(config.get("api_key", "")),
    }


@app.put("/api/ai-studio-config")
async def update_ai_studio_config(payload: Dict[str, Any]):
    try:
        config = _save_ai_studio_config(payload)
        return {
            "ok": True,
            "message": "Google AI Studio 配置已保存",
            "config": config,
            "has_api_key": bool(config.get("api_key")),
            "api_key_masked": _mask_secret(config.get("api_key", "")),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})



@app.post("/upload/model")
async def upload_model(file: UploadFile = File(...)):
    filename, cloud_url = await _save_upload_file(file)
    return {"filename": filename, "cloud_url": cloud_url}


@app.post("/upload/garment")
async def upload_garment(file: UploadFile = File(...)):
    filename, cloud_url = await _save_upload_file(file)
    return {"filename": filename, "cloud_url": cloud_url}


@app.post("/upload/target")
async def upload_target_alias(file: UploadFile = File(...)):
    filename, cloud_url = await _save_upload_file(file)
    return {"filename": filename, "cloud_url": cloud_url}


@app.post("/upload/reference")
async def upload_reference_alias(file: UploadFile = File(...)):
    filename, cloud_url = await _save_upload_file(file)
    return {"filename": filename, "cloud_url": cloud_url}


@app.post("/submit-task")
async def submit_task(
    request: Request,
    target_image: List[str] = Form(...),
    reference_image: str = Form(...),
    api_key: Optional[str] = Form(None),
    proxy_api_key: Optional[str] = Form(None),
    nanobanana_api_key: Optional[str] = Form(None),
    custom_prompt: Optional[str] = Form(None),
    prompt_mode: Optional[str] = Form("append"),
    freedom: Optional[int] = Form(5),
    garment_type: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    provider_mode: Optional[str] = Form("auto"),
    target_image_cloud_url: Optional[str] = Form(None),
    reference_image_cloud_url: Optional[str] = Form(None),
):
    try:
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    # Dedup guard: prevent identical submissions within 10 seconds
    import hashlib
    dedup_hash = hashlib.md5(f"{target_image}:{reference_image}:{model}:{provider_mode}:{freedom}".encode()).hexdigest()
    now = time.time()
    if dedup_hash in _PENDING_DEDUP and now - _PENDING_DEDUP[dedup_hash] < 10:
        return JSONResponse(status_code=429, content={"error": "请勿重复提交，请稍后再试"})
    _PENDING_DEDUP[dedup_hash] = now

    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "status": "pending",
        "progress": 0,
        "message": "Task submitted",
        "result_url": None,
        "result_cloud_url": None,
        "result_display_url": None,
        "result_data_url": None,
        "freedom": int(freedom or 5),
        "garment_type": str(garment_type or "").strip(),
        "logs": [],
        "error": None,
        "created_at": time.time(),
    }
    _prune_old_tasks()
    _persist_task(task_id)
    asyncio.create_task(_admin_report.report_tryon_task(
        task_id, "pending", model_used=model or "flash",
    ))

    base_url = str(request.base_url).rstrip("/")
    asyncio.create_task(
        _process_task(
            task_id=task_id,
            base_url=base_url,
            target_image=target_image,
            reference_image=reference_image,
            api_key=api_key,
            proxy_api_key=proxy_api_key,
            nanobanana_api_key=nanobanana_api_key,
            custom_prompt=custom_prompt,
            prompt_mode=prompt_mode,
            freedom=freedom,
            garment_type=garment_type,
            model=model,
            provider_mode=provider_mode,
            target_image_cloud_url=target_image_cloud_url,
            reference_image_cloud_url=reference_image_cloud_url,
        )
    )

    return {"task_id": task_id}


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    task = TASKS.get(task_id)
    if task:
        return _task_public_payload(task)
    stored = _load_task_from_store(task_id)
    if stored:
        return stored
    return JSONResponse(status_code=404, content={"error": "task not found"})

@app.post("/generate")
async def generate_once(
    request: Request,
    target_image: List[str] = Form(...),
    reference_image: str = Form(...),
    api_key: Optional[str] = Form(None),
    proxy_api_key: Optional[str] = Form(None),
    nanobanana_api_key: Optional[str] = Form(None),
    custom_prompt: Optional[str] = Form(None),
    prompt_mode: Optional[str] = Form("append"),
    freedom: Optional[int] = Form(5),
    garment_type: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    provider_mode: Optional[str] = Form("auto"),
    target_image_cloud_url: Optional[str] = Form(None),
    reference_image_cloud_url: Optional[str] = Form(None),
):
    try:
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")

        model_key = model if model in MODEL_MAP else DEFAULT_MODEL
        freedom_level = max(0, min(10, int(freedom or 5)))
        prompt_text = _build_prompt(custom_prompt, prompt_mode or "append", freedom_level, garment_type)
        effective_mode = _resolve_provider_mode(provider_mode, nanobanana_api_key)
        effective_direct_api_key = _resolve_direct_api_key(api_key, effective_mode)
        rate_key = effective_direct_api_key if effective_mode == "aistudio" else api_key
        rate_identity = _rate_identity(rate_key, nanobanana_api_key, proxy_api_key, effective_mode)
        token_cost = _estimate_token_cost(prompt_text)
        await _check_and_consume_rate_limit(
            identity=rate_identity,
            model_key=model_key,
            token_cost=token_cost,
        )

        base_url = str(request.base_url).rstrip("/")
        img_bytes = await _generate_tryon_image_bytes(
            model_filename=target_image[0],
            garment_filename=reference_image,
            custom_prompt=custom_prompt,
            prompt_mode=prompt_mode or "append",
            freedom=freedom_level,
            garment_type=garment_type,
            model_key=model_key,
            provider_mode=effective_mode,
            proxy_api_key=proxy_api_key,
            nanobanana_api_key=nanobanana_api_key,
            api_key=effective_direct_api_key,
            base_url=base_url,
            model_cloud_url=target_image_cloud_url,
            garment_cloud_url=reference_image_cloud_url,
        )

        out = _save_generated_bytes(img_bytes)
        return {
            "status": "success",
            "generated_image_url": out["result_url"],
            "result_url": out["result_url"],
            "result_cloud_url": out.get("result_cloud_url"),
            "result_display_url": out.get("result_display_url"),
            "result_data_url": out["result_data_url"],
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


def _extract_local_candidates(raw_url: str) -> List[str]:
    if not isinstance(raw_url, str):
        return []

    url = raw_url.strip()
    if not url or url.startswith("data:image/"):
        return []

    parsed = urlparse(url)
    path = parsed.path if parsed.scheme in ("http", "https") else url
    path = unquote(path).split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return []

    normalized = path.replace("\\", "/")
    if normalized.startswith("/"):
        normalized = normalized[1:]

    parts = pathlib.Path(normalized).parts
    if any(part == ".." for part in parts):
        return []

    candidates = [normalized]
    if normalized.startswith("history-files/"):
        candidates.append(os.path.join(HISTORY_FILES_DIR, os.path.basename(normalized)))

    base = os.path.basename(normalized)
    if base:
        candidates.extend([
            os.path.join(ASSET_DIR, base),
            os.path.join(UPLOAD_DIR, base),
            os.path.join(HISTORY_FILES_DIR, base),
        ])

    dedup = []
    seen = set()
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            dedup.append(c)
    return dedup


def _build_download_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


@app.get("/download-single")
async def download_single(url: str):
    """代理下载单张图片，避免浏览器端 CORS 限制。"""
    if not url or not url.strip():
        return JSONResponse(status_code=400, content={"error": "missing url"})
    raw = url.strip()
    img_bytes = None
    # 优先查找本地文件
    for local_path in _extract_local_candidates(raw):
        if os.path.isfile(local_path):
            with open(local_path, "rb") as f:
                img_bytes = f.read()
            break
    # 本地不存在则远程获取
    if img_bytes is None:
        parsed = urlparse(raw)
        if parsed.scheme in ("http", "https"):
            fetch_url = raw
        else:
            route = parsed.path if parsed.path else raw
            if not route.startswith("/"):
                route = f"/{route}"
            port = int(os.environ.get("PORT", "8080"))
            fetch_url = f"http://127.0.0.1:{port}{route}"
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(fetch_url)
            if resp.status_code != 200:
                return JSONResponse(status_code=502, content={"error": f"upstream {resp.status_code}"})
            img_bytes = resp.content
    if not img_bytes or len(img_bytes) < 80:
        return JSONResponse(status_code=404, content={"error": "image not found or empty"})
    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=tryon_result.png"},
    )


@app.post("/download-batch")
async def download_batch(filenames: str = Form(...)):
    try:
        urls = json.loads(filenames)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "invalid filenames JSON"})

    if not isinstance(urls, list) or len(urls) == 0:
        return JSONResponse(status_code=400, content={"error": "no files to download"})

    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    added_count = 0
    failed_count = 0
    batch_stamp = _build_download_stamp()

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
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
                                parsed = urlparse(raw)
                                if parsed.scheme in ("http", "https"):
                                    fetch_url = raw
                                else:
                                    route = parsed.path if parsed.path else raw
                                    if not route.startswith("/"):
                                        route = f"/{route}"
                                    port = int(os.environ.get("PORT", "8080"))
                                    fetch_url = f"http://127.0.0.1:{port}{route}"
                                resp = await client.get(fetch_url)
                                if resp.status_code == 200:
                                    img_bytes = resp.content

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
                content={"error": f"unable to fetch images (total={len(urls)}, failed={failed_count})"},
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
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/rate-status")
async def get_rate_status(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    nanobanana_api_key: Optional[str] = None,
    proxy_api_key: Optional[str] = None,
    provider_mode: Optional[str] = None,
):
    model_key = model if model in MODEL_MAP else DEFAULT_MODEL
    effective_mode = _resolve_provider_mode(provider_mode, nanobanana_api_key)
    proxy_key = (proxy_api_key or "").strip()
    if effective_mode == "proxy" and not proxy_key:
        proxy_key = str(_load_local_proxy_config().get("api_key") or "").strip()
    rate_key = _resolve_direct_api_key(api_key, effective_mode) if effective_mode == "aistudio" else api_key
    identity = _rate_identity(rate_key, nanobanana_api_key, proxy_key, effective_mode)
    return {"ok": True, **_rate_status_snapshot(identity, model_key)}


@app.get("/api/key-usage")
async def get_key_usage(api_key: str):
    key = (api_key or "").strip()
    if not key:
        return {"found": False, "error": "api_key required"}
    row = KEY_USAGE.get(key)
    if not row:
        return {
            "found": False,
            "key_masked": _mask_key(key),
            "calls": 0,
            "success": 0,
            "failed": 0,
            "cost": 0.0,
            "last_used": "",
        }
    return {"found": True, **row}


@app.get("/api/errors")
async def get_errors():
    return {"total": len(ERROR_LOGS), "errors": ERROR_LOGS[:200]}


@app.delete("/api/errors")
async def clear_errors():
    ERROR_LOGS.clear()
    return {"ok": True}


@app.post("/api/errors/report")
async def report_error(message: str = Form(...), context: Optional[str] = Form(None), detail: Optional[str] = Form(None)):
    item = _append_error_log(message, context=context or "frontend", detail=detail or "")
    return {"ok": True, "error": item}


@app.put("/api/errors/{error_id}/analysis")
async def update_error_analysis(error_id: str, analysis: str = Form(...)):
    for row in ERROR_LOGS:
        if row.get("id") == error_id:
            row["analysis"] = str(analysis or "")[:6000]
            return {"ok": True}
    return JSONResponse(status_code=404, content={"error": "error_id not found"})


@app.post("/api/vertex-credentials")
async def upload_vertex_credentials(file: UploadFile = File(...)):
    try:
        if not (file.filename or "").lower().endswith(".json"):
            return JSONResponse(status_code=400, content={"error": "仅允许上传 .json 文件"})

        raw = await file.read()
        if not raw:
            return JSONResponse(status_code=400, content={"error": "上传文件为空"})

        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            return JSONResponse(status_code=400, content={"error": "无效的 JSON 数据"})
        if parsed.get("type") and parsed.get("type") != "service_account":
            return JSONResponse(status_code=400, content={"error": "请上传 service_account 类型的 JSON"})

        with open(CREDENTIALS_PATH, "wb") as f:
            f.write(raw)
        init_vertex_client()
        return {"ok": True, "message": "Vertex 凭证已上传并生效（重启前有效）"}
    except Exception as e:
        _append_error_log(str(e), context="vertex_credentials_upload")
        return JSONResponse(status_code=500, content={"error": str(e)})


VERTEX_DOC_LINKS = [
    "https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/api-errors",
    "https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstarts/quickstart-multimodal",
    "https://ai.google.dev/gemini-api/docs/quickstart?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/pricing?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/safety-settings",
]

ERROR_ANALYSIS_MODEL = os.environ.get(
    "ERROR_ANALYSIS_MODEL",
    "publishers/google/models/gemini-3.1-flash-lite-preview",
)


def generate_fallback_analysis(error_message: str) -> str:
    msg = (error_message or "").lower()

    def fmt(title: str, cause: str, actions: List[str]) -> str:
        action_text = "\n".join([f"{i + 1}. {a}" for i, a in enumerate(actions)])
        links = "\n".join([f"- {u}" for u in VERTEX_DOC_LINKS])
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
            "检查项目配额和账单。",
            "必要时切换 key 或等待窗口重置。",
        ])
    if ("consumer_invalid" in msg) or (("aiplatform.googleapis.com" in msg) and ("permission_denied" in msg)):
        return fmt("通道与认证不匹配", "当前请求很可能走到了 Vertex AI，但项目、区域、账单或服务账号并不满足 Vertex 调用要求；也可能是把 Google AI Studio / Gemini API 密钥误用在了 Vertex 路径上。", [
            "如果你的密钥来自 Google AI Studio，请切换到 Google AI Studio 接口。",
            "如果你要继续使用 Vertex AI，请检查 Cloud Run 服务账号、上传的凭据 JSON 以及 Vertex IAM 权限。",
            "确认当前 GCP 项目与区域已启用 Vertex AI API。",
        ])
    if ("permission_denied" in msg) or ("403" in msg) or ("iam" in msg) or ("serviceusage" in msg):
        return fmt("🔒 IAM/权限问题", "服务账号权限不足或 API 未启用。", [
            "确认服务账号有 Vertex AI User 角色。",
            "确认 Vertex AI API 已启用。",
            "检查 Cloud Run 运行身份。",
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

    links = "\n".join([f"- {u}" for u in VERTEX_DOC_LINKS])
    return f"❓ 未知错误\n\n错误信息: {(error_message or '')[:300]}\n\n建议排查:\n1. 先检查 IAM、配额、区域和 API 启用状态。\n2. 记录完整堆栈和参数。\n3. 对 5xx/超时类错误增加重试。\n\n参考文档:\n{links}"


@app.post("/analyze-error")
async def analyze_error(
    error_message: str = Form(...),
    error_detail: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None),
):
    merged = (error_message or "") + "\n" + (error_detail or "")
    quick = generate_fallback_analysis(merged)

    current_api_key = (api_key or "").strip()
    if not current_api_key:
        return {"analysis": quick}

    try:
        # User provided key first; fallback model naming for Vertex/Express compatibility.
        analysis_client = genai.Client(api_key=current_api_key)

        prompt = (
            "你是资深 Vertex AI/Gemini 排障工程师。"
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

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
import ipaddress
import socket
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urljoin, unquote, quote
from typing import Optional, List, Dict, Any, Tuple

import PIL.Image
import httpx
from google import genai
from app.products import load_catalog, list_products, get_filter_options
from app.admin_runtime_config import resolve_tryon_runtime_config, get_tryon_runtime_status
from app import admin_report as _admin_report
try:
    from google.cloud import firestore
except Exception:
    firestore = None
try:
    from google.cloud import storage
except Exception:
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
}
DEFAULT_MODEL = "flash"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.txt")

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ASSET_DIR = os.path.join(BASE_DIR, "assets")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
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


def _resolve_tryon_generation_config(model_key: str) -> Dict[str, Any]:
    """Resolve generation config from admin DB via runtime config module."""
    try:
        config = resolve_tryon_runtime_config()
    except RuntimeError as exc:
        raise RuntimeError(str(exc))

    if not config.get("enabled"):
        raise RuntimeError("试衣服务当前已由管理员停用")

    api_key = config.get("api_key", "")
    if not api_key:
        raise RuntimeError("试衣服务 API Key 未配置，请联系管理员")

    flash_model = config.get("flash_model", "")
    pro_model = config.get("pro_model", "")

    if model_key == "flash":
        model_ids = [flash_model] if flash_model else []
    else:
        model_ids = [pro_model] if pro_model else []

    # Append fallback model IDs from MODEL_MAP
    for model_id in MODEL_MAP.get(model_key, {}).get("ids") or []:
        if model_id and model_id not in model_ids:
            model_ids.append(model_id)

    return {
        "api_key": api_key,
        "model_ids": [item for item in model_ids if item],
    }


def _validate_model_key(model: Optional[str]) -> str:
    value = str(model or DEFAULT_MODEL).strip().lower()
    if value not in MODEL_MAP:
        raise ValueError("不支持的模型类型，仅允许 flash 或 pro")
    return value


def _require_tryon_runtime_config() -> Dict[str, Any]:
    try:
        config = resolve_tryon_runtime_config()
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc
    if not config.get("enabled"):
        raise RuntimeError("试衣服务当前已由管理员停用")
    if not config.get("api_key"):
        raise RuntimeError("试衣服务 API Key 未配置或无法解密，请联系管理员")
    return config




async def _call_ai_studio_image(
    prompt: str,
    model_path: str,
    garment_path: str,
    model_key: str,
) -> bytes:
    resolved = _resolve_tryon_generation_config(model_key)
    request_key = resolved["api_key"]
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
                return _extract_image_bytes_from_genai_response(response)
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

    raise RuntimeError(_summarize_direct_generation_error(last_error or RuntimeError("unknown ai studio error")))


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

    return await _call_ai_studio_image(
        prompt=prompt,
        model_path=model_path,
        garment_path=garment_path,
        model_key=model_key,
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
):
    task = TASKS[task_id]
    model_key = _validate_model_key(model)

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
            task["message"] = "模拟生成完成"
            task["result_url"] = "/assets/demo_result.png"
            _persist_task(task_id)
            return

        freedom_level = max(0, min(10, int(freedom or 5)))
        prompt_text = _build_prompt(custom_prompt, prompt_mode or "append", freedom_level, garment_type)
        rate_identity = _rate_identity()
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
        _record_key_usage(model_key, True)
        _persist_task(task_id)
        _dur = (time.time() - float(task.get("created_at") or 0)) * 1000
        # Await (not fire-and-forget): a bare create_task here is dropped under
        # Cloud Run CPU throttling after the response returns, so the admin
        # dashboard never received completed try-on tasks. report_tryon_task is
        # self-contained (own timeout + try/except) so awaiting cannot raise.
        await _admin_report.report_tryon_task(
            task_id, "completed",
            result_image_url=out.get("result_cloud_url") or out.get("result_display_url") or "",
            duration_ms=_dur,
            model_used=model_key or "flash",
        )

    except Exception as e:
        task["status"] = "failed"
        task["progress"] = 0
        task["message"] = str(e)
        task["error"] = str(e)
        task["logs"].append(f"Error: {e}")
        _record_key_usage(model_key, False)
        _append_error_log(str(e), context="generation_task", detail=f"task_id={task_id}")
        _persist_task(task_id)
        _dur = (time.time() - float(task.get("created_at") or 0)) * 1000
        # Await for the same reason as the completed branch above.
        await _admin_report.report_tryon_task(
            task_id, "failed",
            error_type=type(e).__name__,
            error_detail=str(e)[:500],
            duration_ms=_dur,
            model_used=model_key or "flash",
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

    _check_url_safe_for_ssrf(url)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        current_url = url
        for _hop in range(5):
            response = await client.get(current_url)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if not location:
                    raise ValueError("重定向响应缺少 Location 头")
                next_url = urljoin(current_url, location)
                _check_url_safe_for_ssrf(next_url)
                current_url = next_url
                continue
            if response.status_code != 200:
                raise ValueError(f"远程图片下载失败 (HTTP {response.status_code})")
            break
        else:
            raise ValueError("远程图片重定向次数超过限制")

    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > INTAKE_MAX_IMAGE_BYTES:
                raise ValueError("远程图片文件过大")
        except (ValueError, TypeError):
            pass

    content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise ValueError("远程地址返回的不是图片资源")

    image_bytes = response.content
    if len(image_bytes) > INTAKE_MAX_IMAGE_BYTES:
        raise ValueError("远程图片文件过大")

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

@app.get("/api/runtime-status")
async def get_runtime_status():
    """Non-sensitive runtime status. No auth required. No secrets returned."""
    return get_tryon_runtime_status()



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
    custom_prompt: Optional[str] = Form(None),
    prompt_mode: Optional[str] = Form("append"),
    freedom: Optional[int] = Form(5),
    garment_type: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    target_image_cloud_url: Optional[str] = Form(None),
    reference_image_cloud_url: Optional[str] = Form(None),
):
    try:
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")
        model_key = _validate_model_key(model)
        _require_tryon_runtime_config()
    except Exception as e:
        status_code = 503 if isinstance(e, RuntimeError) else 400
        return JSONResponse(status_code=status_code, content={"error": str(e)})

    # Dedup guard: prevent identical submissions within 10 seconds
    import hashlib
    dedup_hash = hashlib.md5(f"{target_image}:{reference_image}:{model}:{freedom}".encode()).hexdigest()
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
        task_id, "pending", model_used=model_key,
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
    custom_prompt: Optional[str] = Form(None),
    prompt_mode: Optional[str] = Form("append"),
    freedom: Optional[int] = Form(5),
    garment_type: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    target_image_cloud_url: Optional[str] = Form(None),
    reference_image_cloud_url: Optional[str] = Form(None),
):
    try:
        _validate_single_model(target_image)
        if not reference_image:
            raise ValueError("请上传 1 张服装图片")

        model_key = _validate_model_key(model)
        _require_tryon_runtime_config()
        freedom_level = max(0, min(10, int(freedom or 5)))
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
        if isinstance(e, ValueError):
            status_code = 400
        elif isinstance(e, RuntimeError):
            status_code = 503
        else:
            status_code = 500
        return JSONResponse(status_code=status_code, content={"error": str(e)})


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
):
    model_key = model if model in MODEL_MAP else DEFAULT_MODEL
    identity = _rate_identity()
    return {"ok": True, **_rate_status_snapshot(identity, model_key)}


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

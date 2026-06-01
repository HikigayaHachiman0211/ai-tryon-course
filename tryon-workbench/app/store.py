"""Task store: in-memory + optional Firestore persistence."""

import time
import uuid
import asyncio
from typing import Dict, Any, Optional, List

from app.config import TASK_STORE_MAX_ENTRIES, ERROR_LOG_MAX_ENTRIES, MODEL_PRICING

try:
    from google.cloud import firestore
except Exception:
    firestore = None

# ===== In-memory stores =====
TASKS: Dict[str, Dict[str, Any]] = {}
TASKS_COLLECTION = "generation_tasks"

ERROR_LOGS: List[Dict[str, Any]] = []
KEY_USAGE: Dict[str, Dict[str, Any]] = {}

# ===== Firestore client =====
db = None


def init_firestore():
    global db
    if firestore is None:
        print("[DB] Firestore module unavailable, fallback to memory only")
        return
    try:
        db = firestore.Client()
        print("[DB] Firestore connected")
    except Exception as e:
        db = None
        print(f"[DB] Firestore unavailable, fallback to memory only: {e}")


def _mask_key(api_key: str) -> str:
    k = (api_key or "").strip()
    if not k:
        return "N/A"
    if len(k) <= 8:
        return f"{k[:2]}***{k[-2:]}"
    return f"{k[:4]}...{k[-4:]}"


def record_key_usage(api_key: Optional[str], model_key: str, success: bool):
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


def append_error_log(message: str, context: str = "", detail: str = "", analysis: str = "") -> Dict[str, Any]:
    item = {
        "id": f"err_{uuid.uuid4().hex[:12]}",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "message": str(message or "")[:2000],
        "context": str(context or "")[:200],
        "detail": str(detail or "")[:3000],
        "analysis": str(analysis or "")[:6000],
    }
    ERROR_LOGS.insert(0, item)
    if len(ERROR_LOGS) > ERROR_LOG_MAX_ENTRIES:
        del ERROR_LOGS[ERROR_LOG_MAX_ENTRIES:]
    return item


def task_public_payload(task: Optional[dict]) -> dict:
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


def persist_task(task_id: str):
    if db is None:
        return
    task = TASKS.get(task_id)
    if not task:
        return
    try:
        payload = task_public_payload(task)
        payload["updated_at"] = firestore.SERVER_TIMESTAMP
        db.collection(TASKS_COLLECTION).document(task_id).set(payload, merge=True)
    except Exception as e:
        print(f"[TaskStore] persist failed: {task_id} -> {e}")


def load_task_from_store(task_id: str) -> Optional[dict]:
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
        return task_public_payload(data)
    except Exception as e:
        print(f"[TaskStore] load failed: {task_id} -> {e}")
        return None


def prune_old_tasks():
    """Remove oldest completed/failed tasks when store exceeds limit."""
    if len(TASKS) <= TASK_STORE_MAX_ENTRIES:
        return
    completed = [(tid, t) for tid, t in TASKS.items() if t.get("status") in ("completed", "failed")]
    completed.sort(key=lambda x: x[1].get("created_at", 0))
    to_remove = len(TASKS) - TASK_STORE_MAX_ENTRIES
    for tid, _ in completed[:to_remove]:
        del TASKS[tid]

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_admin
from app.services import gcs

router = APIRouter(prefix="/api/admin/history", tags=["history"])

# Must match the GCS prefix used by the main site (gcs_storage.GCS_RESULT_PREFIX)
GCS_RESULT_PREFIX = "ai-tryon-results"
HISTORY_INDEX_KEY = f"{GCS_RESULT_PREFIX}/history_index.json"


def _load_index() -> list[dict]:
    data = gcs.download_blob(HISTORY_INDEX_KEY)
    if not data:
        return []
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return []


def _format_timestamp(ts: str | None) -> str | None:
    """Format the Shanghai-ISO index timestamp to 'YYYY-MM-DD HH:MM:SS'."""
    if not ts:
        return ts
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def _to_list_item(entry: dict) -> dict:
    """Map a raw GCS index entry to the structure expected by the admin frontend.

    The main site writes 'timestamp' / 'item_count' (and never a session id),
    while the table reads 'created_at' / 'result_count' / 'summary'.
    """
    return {
        "id": entry.get("id"),
        "created_at": _format_timestamp(entry.get("timestamp")),
        "result_count": entry.get("item_count"),
        "summary": entry.get("summary"),
        "thumbnail_url": entry.get("thumbnail_url"),
        "type": entry.get("type"),
    }


@router.get("")
def list_history(page: int = 1, size: int = 20, admin=Depends(get_current_admin)):
    index = _load_index()
    index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    total = len(index)
    start = (page - 1) * size
    return {"total": total, "items": [_to_list_item(e) for e in index[start: start + size]]}


@router.get("/{result_id}")
def get_history(result_id: str, admin=Depends(get_current_admin)):
    data = gcs.download_blob(f"{GCS_RESULT_PREFIX}/results/{result_id}.json")
    if not data:
        raise HTTPException(404, "历史记录不存在")
    result = json.loads(data)
    # Trim items to first 5 to avoid frontend lag/crash from rendering too many items
    if isinstance(result.get("items"), list) and len(result["items"]) > 5:
        result["_total_items"] = len(result["items"])
        result["items"] = result["items"][:5]
    return result


@router.delete("/{result_id}")
def delete_history(result_id: str, admin=Depends(get_current_admin)):
    # Delete result json
    gcs.delete_blob(f"{GCS_RESULT_PREFIX}/results/{result_id}.json")
    # Delete thumbnail
    gcs.delete_blob(f"{GCS_RESULT_PREFIX}/thumbnails/{result_id}.png")

    # Update index
    index = _load_index()
    index = [item for item in index if item.get("id") != result_id]
    gcs.upload_blob(HISTORY_INDEX_KEY, json.dumps(index).encode(), content_type="application/json")

    return {"detail": "已删除"}

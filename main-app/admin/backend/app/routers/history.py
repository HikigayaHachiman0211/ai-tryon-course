from __future__ import annotations

import json

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


@router.get("")
def list_history(page: int = 1, size: int = 20, admin=Depends(get_current_admin)):
    index = _load_index()
    index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    total = len(index)
    start = (page - 1) * size
    return {"total": total, "items": index[start: start + size]}


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

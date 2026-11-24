from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func

from app.auth import get_current_admin
from app.database import RecommendationHistory, get_db
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
    """Map a raw index entry to the structure expected by the admin frontend."""
    return {
        "id": entry.get("id"),
        "created_at": _format_timestamp(entry.get("timestamp")),
        "result_count": entry.get("item_count"),
        "summary": entry.get("summary"),
        "thumbnail_url": entry.get("thumbnail_url"),
        "type": entry.get("type"),
    }


def _db_row_to_list_item(row: RecommendationHistory) -> dict:
    return {
        "id": row.id,
        "created_at": _format_timestamp(row.created_at),
        "result_count": row.item_count,
        "summary": row.summary,
        "thumbnail_url": f"/api/history/{row.id}/thumbnail" if row.thumbnail_blob_path else None,
        "type": row.result_type,
    }


@router.get("")
def list_history(page: int = 1, size: int = 20, admin=Depends(get_current_admin), db=Depends(get_db)):
    del admin
    page = max(1, page)
    size = max(1, min(size, 100))
    total = db.query(func.count(RecommendationHistory.id)).scalar() or 0
    if total > 0:
        rows = (
            db.query(RecommendationHistory)
            .order_by(desc(RecommendationHistory.created_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return {"total": total, "items": [_db_row_to_list_item(r) for r in rows]}

    index = _load_index()
    index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    total = len(index)
    start = (page - 1) * size
    return {"total": total, "items": [_to_list_item(e) for e in index[start: start + size]]}


@router.get("/{result_id}")
def get_history(result_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    del admin
    row = db.get(RecommendationHistory, result_id)
    result = None
    if row is not None and row.payload_json:
        try:
            result = json.loads(row.payload_json)
        except json.JSONDecodeError:
            result = None
    if result is None:
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
def delete_history(result_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    del admin
    row = db.get(RecommendationHistory, result_id)
    if row is not None:
        for path in (row.result_blob_path, row.thumbnail_blob_path, row.user_photo_blob_path):
            if path:
                try:
                    gcs.delete_blob(path)
                except Exception:
                    pass
        db.delete(row)
        db.commit()

    for blob_path in (
        f"{GCS_RESULT_PREFIX}/results/{result_id}.json",
        f"{GCS_RESULT_PREFIX}/thumbnails/{result_id}.png",
        f"{GCS_RESULT_PREFIX}/user_photos/{result_id}.jpg",
        f"{GCS_RESULT_PREFIX}/user_photos/{result_id}.png",
    ):
        try:
            gcs.delete_blob(blob_path)
        except Exception:
            pass

    # Update legacy index if present
    index = _load_index()
    if index:
        updated = [item for item in index if item.get("id") != result_id]
        if len(updated) != len(index):
            gcs.upload_blob(HISTORY_INDEX_KEY, json.dumps(updated).encode(), content_type="application/json")

    return {"detail": "已删除"}

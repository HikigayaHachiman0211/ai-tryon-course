from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import cast, Date, func

from app.auth import get_current_admin
from app.database import UserProfile, TryonTask, get_db
from app.routers import to_beijing_str

router = APIRouter(prefix="/api/admin/profiles", tags=["profiles"])


@router.get("")
def list_profiles(
    page: int = 1,
    size: int = 20,
    gender: str = "",
    body_shape: str = "",
    fallback: str = "",
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    q = db.query(UserProfile)
    if gender:
        q = q.filter(UserProfile.gender == gender)
    if body_shape:
        q = q.filter(UserProfile.ai_body_shape.ilike(f"%{body_shape}%"))
    if fallback == "true":
        q = q.filter(UserProfile.used_fallback == True)
    elif fallback == "false":
        q = q.filter(UserProfile.used_fallback == False)

    total = q.count()
    items = q.order_by(UserProfile.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "total": total,
        "page": page,
        "items": [_serialize(p) for p in items],
    }


@router.get("/stats")
def profile_stats(admin=Depends(get_current_admin), db=Depends(get_db)):
    total = db.query(func.count(UserProfile.id)).scalar() or 0
    fallback_count = db.query(func.count(UserProfile.id)).filter(UserProfile.used_fallback == True).scalar() or 0

    # Body shape distribution
    body_dist = (
        db.query(UserProfile.ai_body_shape, func.count(UserProfile.id))
        .filter(UserProfile.ai_body_shape.isnot(None))
        .group_by(UserProfile.ai_body_shape)
        .order_by(func.count(UserProfile.id).desc())
        .all()
    )

    # Size distribution
    size_dist = (
        db.query(UserProfile.ai_recommended_size, func.count(UserProfile.id))
        .filter(UserProfile.ai_recommended_size.isnot(None))
        .group_by(UserProfile.ai_recommended_size)
        .order_by(func.count(UserProfile.id).desc())
        .all()
    )

    # Gender distribution
    gender_dist = (
        db.query(UserProfile.gender, func.count(UserProfile.id))
        .filter(UserProfile.gender.isnot(None))
        .group_by(UserProfile.gender)
        .all()
    )

    return {
        "total": total,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / total * 100, 1) if total > 0 else 0,
        "body_shape_distribution": [{"shape": b[0], "count": b[1]} for b in body_dist],
        "size_distribution": [{"size": s[0], "count": s[1]} for s in size_dist],
        "gender_distribution": [{"gender": g[0], "count": g[1]} for g in gender_dist],
    }


@router.get("/{profile_id}")
def get_profile(profile_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(UserProfile, profile_id)
    if not p:
        raise HTTPException(404, "画像不存在")
    return _serialize(p)


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(UserProfile, profile_id)
    if not p:
        raise HTTPException(404, "画像不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/{profile_id}/tryon-results")
def tryon_results(profile_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(UserProfile, profile_id)
    if not p:
        raise HTTPException(404, "画像不存在")
    # Try to find tryon tasks matching the user photo
    tasks = []
    if p.photo_url:
        tasks = db.query(TryonTask).filter(TryonTask.user_photo_url == p.photo_url).all()
    return [
        {
            "id": t.id,
            "status": t.status,
            "product_id": t.product_id,
            "result_image_url": t.result_image_url,
            "created_at": to_beijing_str(t.created_at),
        }
        for t in tasks
    ]


def _serialize(p: UserProfile) -> dict:
    return {
        "id": p.id,
        "session_id": p.session_id[:8] + "..." if p.session_id and len(p.session_id) > 8 else p.session_id,
        "created_at": to_beijing_str(p.created_at),
        "photo_url": p.photo_url,
        "gender": p.gender,
        "mbti": p.mbti,
        "color_preference": p.color_preference,
        "size_input": p.size_input,
        "style_input": p.style_input,
        "ai_recommended_size": p.ai_recommended_size,
        "ai_body_shape": p.ai_body_shape,
        "ai_suggested_style": p.ai_suggested_style,
        "ai_reasoning": p.ai_reasoning,
        "used_fallback": p.used_fallback,
        "recommendation_count": p.recommendation_count,
    }

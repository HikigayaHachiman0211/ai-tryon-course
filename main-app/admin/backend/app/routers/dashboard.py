from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import get_current_admin
from app.database import get_db
from app.services import stats as stats_svc

router = APIRouter(prefix="/api/admin/dashboard", tags=["dashboard"])


@router.get("/overview")
def get_overview(admin=Depends(get_current_admin), db=Depends(get_db)):
    return stats_svc.overview(db)


@router.get("/trends")
def get_trends(days: int = 7, admin=Depends(get_current_admin), db=Depends(get_db)):
    return {"trends": stats_svc.trends(db, days=days)}


@router.get("/top-preferences")
def get_top_preferences(admin=Depends(get_current_admin), db=Depends(get_db)):
    return stats_svc.top_preferences(db)

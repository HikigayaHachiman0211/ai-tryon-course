"""Statistics query helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, case, cast, Date
from sqlalchemy.orm import Session

from app.database import PageView, Product, RequestLog

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _shanghai_today_start_utc() -> datetime:
    """Return the UTC datetime corresponding to midnight Shanghai time today."""
    now_sh = datetime.now(SHANGHAI)
    midnight_sh = now_sh.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_sh.astimezone(timezone.utc).replace(tzinfo=None)


def overview(db: Session) -> dict:
    total = db.query(func.count(Product.id)).scalar() or 0

    # Platform split by title keyword
    jd_count = db.query(func.count(Product.id)).filter(
        Product.image_path.like("%downloaded_jd_images%")
    ).scalar() or 0
    taobao_count = total - jd_count

    now = datetime.now(timezone.utc)
    today_start = _shanghai_today_start_utc()

    today_recommend = db.query(func.count(RequestLog.id)).filter(
        RequestLog.timestamp >= today_start,
        RequestLog.endpoint == "recommend",
    ).scalar() or 0

    today_style_lab = db.query(func.count(RequestLog.id)).filter(
        RequestLog.timestamp >= today_start,
        RequestLog.endpoint == "style-lab",
    ).scalar() or 0

    total_logs = db.query(func.count(RequestLog.id)).scalar() or 0

    # --- Page view counts ---
    today_visits_main = db.query(func.count(PageView.id)).filter(
        PageView.timestamp >= today_start,
        PageView.source == "main_site",
    ).scalar() or 0

    today_visits_tryon = db.query(func.count(PageView.id)).filter(
        PageView.timestamp >= today_start,
        PageView.source == "tryon_workbench",
    ).scalar() or 0

    return {
        "total_products": total,
        "jd_products": jd_count,
        "taobao_products": taobao_count,
        "today_requests": today_recommend + today_style_lab,
        "today_recommend": today_recommend,
        "today_style_lab": today_style_lab,
        "total_requests": total_logs,
        "today_visits": today_visits_main + today_visits_tryon,
        "today_visits_main": today_visits_main,
        "today_visits_tryon": today_visits_tryon,
    }


def trends(db: Session, days: int = 7) -> list[dict]:
    now = datetime.now(SHANGHAI)
    request_data = []
    visit_data = []

    for i in range(days, -1, -1):
        sh_day = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        sh_next = sh_day + timedelta(days=1)
        utc_start = sh_day.astimezone(timezone.utc).replace(tzinfo=None)
        utc_end = sh_next.astimezone(timezone.utc).replace(tzinfo=None)
        day_str = str(sh_day.date())

        # Request log counts per endpoint
        req_rows = (
            db.query(RequestLog.endpoint, func.count(RequestLog.id).label("count"))
            .filter(RequestLog.timestamp >= utc_start, RequestLog.timestamp < utc_end)
            .group_by(RequestLog.endpoint)
            .all()
        )
        for r in req_rows:
            request_data.append({"date": day_str, "category": "request", "type": r.endpoint, "count": r.count})

        # Page view counts per source
        pv_rows = (
            db.query(PageView.source, func.count(PageView.id).label("count"))
            .filter(PageView.timestamp >= utc_start, PageView.timestamp < utc_end)
            .group_by(PageView.source)
            .all()
        )
        for r in pv_rows:
            visit_data.append({"date": day_str, "category": "visit", "type": r.source, "count": r.count})

    return request_data + visit_data


def top_preferences(db: Session) -> dict:
    # Color distribution
    colors = (
        db.query(Product.color_family, func.count(Product.id).label("count"))
        .group_by(Product.color_family)
        .order_by(func.count(Product.id).desc())
        .limit(10)
        .all()
    )

    # Style type distribution
    styles = (
        db.query(Product.style_type, func.count(Product.id).label("count"))
        .group_by(Product.style_type)
        .order_by(func.count(Product.id).desc())
        .limit(10)
        .all()
    )

    # Price ranges
    price_ranges = []
    boundaries = [0, 100, 200, 300, 500, 800, 1000, 1500, 2000, 99999]
    for i in range(len(boundaries) - 1):
        lo, hi = boundaries[i], boundaries[i + 1]
        label = f"{lo}-{hi}" if hi < 99999 else f"{lo}+"
        cnt = db.query(func.count(Product.id)).filter(
            Product.price >= lo, Product.price < hi
        ).scalar() or 0
        price_ranges.append({"range": label, "count": cnt})

    return {
        "top_colors": [{"color": c[0], "count": c[1]} for c in colors],
        "top_styles": [{"name": s[0], "count": s[1]} for s in styles],
        "price_distribution": price_ranges,
    }

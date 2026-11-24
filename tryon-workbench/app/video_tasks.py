"""Durable, visitor-owned video task receipts and idempotent submission claims."""
import hashlib
import json
import time
import uuid
from urllib.parse import quote

from sqlalchemy import Column, Float, String, Text, update, text
from sqlalchemy.exc import IntegrityError

from app.task_db import TaskBase, get_session_factory, issue_short_lived_media_token, verify_short_lived_media_token
from app.video_gateway import VideoError, public_media_url


class VideoTask(TaskBase):
    __tablename__ = "workbench_video_tasks"
    id = Column(String(64), primary_key=True)
    owner = Column(String(128), index=True, nullable=False)
    request_hash = Column(String(64), nullable=False)
    connection_hash = Column(String(64), nullable=False)
    upstream_id = Column(String(160), nullable=True)
    model = Column(String(160), nullable=False)
    provider = Column(String(80), nullable=False, default="")
    status = Column(String(32), nullable=False, default="submitting")
    result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(Float, nullable=False)
    polled_at = Column(Float, nullable=False, default=0)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def connection_hash(cfg):
    return digest([cfg["base_url"], cfg.get("project_id", ""), cfg.get("api_key", "")])


def _factory():
    factory, engine = get_session_factory()
    if not getattr(engine, "_video_task_table_ready", False):
        VideoTask.__table__.create(engine, checkfirst=True)
        setattr(engine, "_video_task_table_ready", True)
    return factory


def public_task(row):
    result = json.loads(row.result_json)
    status = "unknown" if row.status == "submitting" and time.time() - row.created_at > 150 else row.status
    downloads = [f"/api/video/tasks/{row.id}/download?index={i}&st={quote(issue_short_lived_media_token(f'video:{row.id}:{i}', row.owner))}"
                 for i in range(len(result.get("outputs") or []))]
    return {**result, "download_urls": downloads, "id": row.id, "upstream_id": row.upstream_id, "model": row.model,
            "provider": row.provider, "status": status, "created_at": row.created_at}


def existing_task(owner, key, request_hash):
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"video:{owner}:{key}"))
    with _factory()() as session:
        row = session.get(VideoTask, task_id)
        if row is None:
            return None
        if request_hash is not None and row.request_hash != request_hash:
            raise VideoError(409, "idempotency_conflict", "This submission key belongs to different parameters")
        return public_task(row)


def reserve_task(owner, key, request_hash, cfg, model, provider):
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"video:{owner}:{key}"))
    factory = _factory()
    with factory() as session:
        row = VideoTask(id=task_id, owner=owner, request_hash=request_hash, connection_hash=connection_hash(cfg),
                        model=model, provider=provider, created_at=time.time(), status="submitting", result_json="{}")
        session.add(row)
        try:
            session.commit()
            return public_task(row), True
        except IntegrityError:
            session.rollback()
    return existing_task(owner, key, request_hash), False


def get_task(task_id, owner, cfg=None):
    with _factory()() as session:
        row = session.get(VideoTask, task_id)
        if row is None or row.owner != owner:
            raise VideoError(404, "task_not_found", "Video task not found")
        if cfg is not None and row.connection_hash != connection_hash(cfg):
            raise VideoError(409, "connection_changed", "Restore the original 01Router connection to query this task")
        return public_task(row)


def list_tasks(owner):
    with _factory()() as session:
        rows = session.query(VideoTask).filter_by(owner=owner).order_by(VideoTask.created_at.desc()).limit(20).all()
        return [public_task(row) for row in rows]


def get_download_task(task_id, owner, index, token):
    with _factory()() as session:
        row = session.get(VideoTask, task_id)
        if row is None or (row.owner != owner and not verify_short_lived_media_token(f"video:{task_id}:{index}", token, expected_access_token_hash=row.owner)):
            raise VideoError(404, "task_not_found", "Video task not found")
        return public_task(row)


def save_result(task_id, data):
    with _factory()() as session:
        if session.bind.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        row = session.query(VideoTask).filter_by(id=task_id).with_for_update().one()
        if row.status in {"failed", "succeeded"}:
            return public_task(row)
        upstream_id = data.get("id")
        if upstream_id:
            row.upstream_id = str(upstream_id)[:160]
        status = data.get("status", "unknown")
        row.status = status if status in {"queued", "processing", "succeeded", "failed", "unknown"} else "unknown"
        if data.get("provider"):
            row.provider = str(data["provider"])[:80]
        outputs = data.get("outputs") or []
        result = {"outputs": [v for v in outputs if isinstance(v, str) and public_media_url(v)][:8],
                  "error": str(data["error"])[:500] if data.get("error") else None,
                  "error_code": data.get("error_code"), "price_usd": data.get("price_usd"),
                  "credits": data.get("credits"), "completed_at": data.get("completed_at")}
        row.result_json = json.dumps(result, ensure_ascii=False)
        session.commit()
        return public_task(row)


def claim_poll(task_id):
    with _factory()() as session:
        result = session.execute(update(VideoTask).where(VideoTask.id == task_id, VideoTask.polled_at <= time.time() - 3).values(polled_at=time.time()))
        session.commit()
        return bool(result.rowcount)

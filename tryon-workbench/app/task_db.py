"""Shared PostgreSQL/SQLite task store, lease management, rate limits, and private media metadata."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.tryon_options import parse_detail_options, serialize_detail_options

PT_ZONE = ZoneInfo("America/Los_Angeles")
SHANGHAI_ZONE = ZoneInfo("Asia/Shanghai")

TERMINAL_TASK_STATUSES = {"completed", "failed", "unknown"}


class TaskBase(DeclarativeBase):
    pass


class WorkbenchTaskRecord(TaskBase):
    __tablename__ = "workbench_generation_tasks"

    task_id = Column(String(64), primary_key=True)
    idempotency_key = Column(String(192), unique=True, index=True, nullable=False)
    access_token_hash = Column(String(128), index=True, nullable=False)

    status = Column(String(32), index=True, nullable=False, default="pending")
    message_code = Column(String(64), nullable=False, default="pending")
    message = Column(Text, nullable=False, default="Task submitted")
    progress = Column(Integer, nullable=False, default=0)
    locale = Column(String(16), nullable=False, default="zh-CN")

    model_key = Column(String(32), nullable=False, default="flash")
    provider_key = Column(String(32), nullable=True)
    model_id = Column(String(128), nullable=True)
    detail_options_json = Column(Text, nullable=True, default="{}")
    freedom = Column(Integer, nullable=False, default=5)
    garment_type = Column(String(64), nullable=False, default="")
    custom_prompt = Column(Text, nullable=True)
    prompt_mode = Column(String(32), nullable=False, default="append")

    target_filename = Column(String(255), nullable=False)
    reference_filename = Column(String(255), nullable=False)
    input_target_blob = Column(String(500), nullable=True)
    input_reference_blob = Column(String(500), nullable=True)
    output_result_blob = Column(String(500), nullable=True)
    result_filename = Column(String(255), nullable=True)

    error_code = Column(String(128), nullable=True)
    error_detail = Column(Text, nullable=True)
    logs_json = Column(Text, nullable=False, default="[]")

    attempt_count = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(128), nullable=True)
    lease_expires_at = Column(Float, nullable=True)

    upstream_status = Column(String(32), nullable=False, default="not_started")
    upstream_started_at = Column(Float, nullable=True)
    upstream_completed_at = Column(Float, nullable=True)

    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)


class WorkbenchRateLimitRecord(TaskBase):
    __tablename__ = "workbench_rate_limits"

    identity = Column(String(128), primary_key=True)
    model_key = Column(String(32), primary_key=True)
    minute_id = Column(Integer, nullable=False, default=0)
    day_key = Column(String(16), nullable=False, default="")
    month_key = Column(String(16), nullable=False, default="")
    rpm_used = Column(Integer, nullable=False, default=0)
    tpm_used = Column(Integer, nullable=False, default=0)
    rpd_used = Column(Integer, nullable=False, default=0)
    monthly_used = Column(Integer, nullable=False, default=0)
    updated_at = Column(Float, nullable=False, default=0.0)


class WorkbenchMediaRecord(TaskBase):
    __tablename__ = "workbench_media_files"

    filename = Column(String(255), primary_key=True)
    blob_name = Column(String(500), nullable=False)
    media_kind = Column(String(32), nullable=False, default="upload")
    content_type = Column(String(64), nullable=False, default="image/png")
    access_token_hash = Column(String(128), index=True, nullable=False)
    task_id = Column(String(64), index=True, nullable=True)
    created_at = Column(Float, nullable=False)


class WorkbenchRealtimeSession(TaskBase):
    __tablename__ = "workbench_realtime_sessions"

    id = Column(String(32), primary_key=True)
    provider_key = Column(String(32), nullable=False, default="decart", index=True)
    model_id = Column(String(64), nullable=True)
    visitor_hash = Column(String(64), nullable=False, index=True)
    budget_day = Column(String(10), nullable=False, index=True)
    created_at = Column(Float, nullable=False, index=True)
    claim_before = Column(Float, nullable=False)
    hold_until = Column(Float, nullable=False, index=True)
    state = Column(String(16), nullable=False)
    stop_requested = Column(Boolean, nullable=False, default=False)
    limit_seconds = Column(Integer, nullable=False)
    cents_per_second = Column(Integer, nullable=False)
    cents_per_minute = Column(Integer, nullable=True)
    credits_per_second = Column(Float, nullable=True)
    max_credits = Column(Integer, nullable=True)
    accounted_cents = Column(Integer, nullable=False)
    provider_session_id = Column(String(128))
    provider_seconds = Column(Float)
    provider_credits = Column(Float, nullable=True)
    provider_temp_key_uid = Column(String(128), nullable=True)
    provider_temp_key_encrypted = Column(Text, nullable=True)
    reason = Column(String(32))
    ended_at = Column(Float)


_ENGINE_LOCK = threading.Lock()
_ENGINES: Dict[str, Any] = {}
_SESSIONS: Dict[str, Any] = {}
_INITIALIZED_URLS: set[str] = set()
_SQLITE_WRITE_LOCK = threading.Lock()
_DEV_EPHEMERAL_SECRET = secrets.token_hex(32)


def is_production_env() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() in {"production", "prod"}


def _default_sqlite_path() -> str:
    history_dir = os.path.abspath(
        os.environ.get(
            "HISTORY_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history"),
        )
    )
    os.makedirs(history_dir, exist_ok=True)
    return os.path.join(history_dir, "workbench_state.db")


def resolve_task_database_url(db_url: Optional[str] = None) -> str:
    raw = str(
        db_url
        or os.environ.get("TASK_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("AI_CONFIG_DATABASE_URL")
        or ""
    ).strip()
    if raw:
        if raw.startswith("postgres://"):
            return "postgresql+psycopg://" + raw[len("postgres://"):]
        if raw.startswith("postgresql://") and "+psycopg" not in raw:
            return "postgresql+psycopg://" + raw[len("postgresql://"):]
        return raw
    if is_production_env():
        raise RuntimeError("TASK_DATABASE_URL or DATABASE_URL must be configured in production")
    sqlite_path = _default_sqlite_path().replace("\\", "/")
    return f"sqlite:///{sqlite_path}"


def _ensure_optional_task_columns(engine) -> None:
    try:
        cols = {col["name"] for col in sa_inspect(engine).get_columns("workbench_generation_tasks")}
    except Exception:
        return
    optional_cols = (
        ("provider_key", "VARCHAR(32)"),
        ("model_id", "VARCHAR(128)"),
        ("detail_options_json", "TEXT"),
    )
    missing = [(name, ddl) for name, ddl in optional_cols if name not in cols]
    if not missing:
        return
    is_pg = engine.dialect.name == "postgresql"
    for name, ddl in missing:
        stmt = (
            f"ALTER TABLE workbench_generation_tasks ADD COLUMN IF NOT EXISTS {name} {ddl}"
            if is_pg
            else f"ALTER TABLE workbench_generation_tasks ADD COLUMN {name} {ddl}"
        )
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            refreshed = {col["name"] for col in sa_inspect(engine).get_columns("workbench_generation_tasks")}
            if name not in refreshed:
                raise


def _ensure_realtime_session_columns(engine) -> None:
    try:
        cols = {col["name"] for col in sa_inspect(engine).get_columns("workbench_realtime_sessions")}
    except Exception:
        return
    optional_cols = (
        ("provider_key", "VARCHAR(32) NOT NULL DEFAULT 'decart'"),
        ("model_id", "VARCHAR(64)"),
        ("cents_per_minute", "INTEGER"),
        ("credits_per_second", "FLOAT"),
        ("max_credits", "INTEGER"),
        ("provider_credits", "FLOAT"),
        ("provider_temp_key_uid", "VARCHAR(128)"),
        ("provider_temp_key_encrypted", "TEXT"),
    )
    missing = [(name, ddl) for name, ddl in optional_cols if name not in cols]
    is_pg = engine.dialect.name == "postgresql"
    for name, ddl in missing:
        stmt = (
            f"ALTER TABLE workbench_realtime_sessions ADD COLUMN IF NOT EXISTS {name} {ddl}"
            if is_pg
            else f"ALTER TABLE workbench_realtime_sessions ADD COLUMN {name} {ddl}"
        )
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            refreshed = {col["name"] for col in sa_inspect(engine).get_columns("workbench_realtime_sessions")}
            if name not in refreshed:
                raise
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_workbench_realtime_sessions_provider_key "
                "ON workbench_realtime_sessions (provider_key)"
            ))
    except Exception:
        pass


def get_session_factory(db_url: Optional[str] = None):
    url = resolve_task_database_url(db_url)
    with _ENGINE_LOCK:
        if url not in _ENGINES:
            kwargs: Dict[str, Any] = {"pool_pre_ping": True}
            if url.startswith("sqlite"):
                kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            engine = create_engine(url, **kwargs)
            _ENGINES[url] = engine
            _SESSIONS[url] = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        if url not in _INITIALIZED_URLS:
            TaskBase.metadata.create_all(bind=_ENGINES[url], checkfirst=True)
            _ensure_optional_task_columns(_ENGINES[url])
            _ensure_realtime_session_columns(_ENGINES[url])
            _INITIALIZED_URLS.add(url)
        return _SESSIONS[url], _ENGINES[url]


def ensure_task_tables(db_url: Optional[str] = None) -> None:
    get_session_factory(db_url)


def reset_engine_cache() -> None:
    with _ENGINE_LOCK:
        for eng in _ENGINES.values():
            try:
                eng.dispose()
            except Exception:
                pass
        _ENGINES.clear()
        _SESSIONS.clear()
        _INITIALIZED_URLS.clear()


def _signing_secret() -> bytes:
    secret = (
        os.environ.get("TASK_TOKEN_SECRET")
        or os.environ.get("INGEST_SECRET_KEY")
        or os.environ.get("FERNET_SECRET_KEY")
        or os.environ.get("JWT_SECRET_KEY")
        or _DEV_EPHEMERAL_SECRET
    )
    return secret.encode("utf-8")


def generate_access_token() -> str:
    return secrets.token_urlsafe(24)


def hash_access_token(raw_token: str) -> str:
    value = str(raw_token or "").strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_short_lived_media_token(
    filename: str,
    access_token_hash: str,
    *,
    ttl_seconds: int = 3600,
    now_ts: Optional[float] = None,
) -> str:
    exp = int((now_ts if now_ts is not None else time.time()) + max(60, ttl_seconds))
    payload = f"{filename}:{access_token_hash}:{exp}".encode("utf-8")
    sig = hmac.new(_signing_secret(), payload, hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_short_lived_media_token(
    filename: str,
    token: str,
    *,
    expected_access_token_hash: Optional[str] = None,
    now_ts: Optional[float] = None,
) -> bool:
    raw = str(token or "").strip()
    if "." not in raw or not expected_access_token_hash:
        return False
    exp_str, sig = raw.split(".", 1)
    try:
        exp = int(exp_str)
    except ValueError:
        return False
    current = now_ts if now_ts is not None else time.time()
    if exp < int(current):
        return False
    payload = f"{filename}:{expected_access_token_hash}:{exp}".encode("utf-8")
    expected_sig = hmac.new(_signing_secret(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def derive_idempotent_task_id(access_token_hash: str, idempotency_key: str) -> str:
    seed = f"tryon:{access_token_hash}:{idempotency_key}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _record_to_dict(row: WorkbenchTaskRecord) -> Dict[str, Any]:
    try:
        logs = json.loads(row.logs_json or "[]")
        if not isinstance(logs, list):
            logs = [str(logs)]
    except Exception:
        logs = []
    return {
        "task_id": row.task_id,
        "idempotency_key": row.idempotency_key,
        "access_token_hash": row.access_token_hash,
        "status": row.status,
        "message_code": row.message_code,
        "message": row.message,
        "progress": int(row.progress or 0),
        "locale": row.locale or "zh-CN",
        "model_key": row.model_key or "flash",
        "provider_key": row.provider_key or None,
        "model_id": row.model_id or None,
        "detail_options": parse_detail_options(row.detail_options_json),
        "freedom": int(5 if row.freedom is None else row.freedom),
        "garment_type": row.garment_type or "",
        "custom_prompt": row.custom_prompt,
        "prompt_mode": row.prompt_mode or "append",
        "target_filename": row.target_filename,
        "reference_filename": row.reference_filename,
        "input_target_blob": row.input_target_blob,
        "input_reference_blob": row.input_reference_blob,
        "output_result_blob": row.output_result_blob,
        "result_filename": row.result_filename,
        "error_code": row.error_code,
        "error_detail": row.error_detail,
        "logs": [str(x) for x in logs][-500:],
        "attempt_count": int(row.attempt_count or 0),
        "lease_owner": row.lease_owner,
        "lease_expires_at": row.lease_expires_at,
        "upstream_status": row.upstream_status or "not_started",
        "upstream_started_at": row.upstream_started_at,
        "upstream_completed_at": row.upstream_completed_at,
        "created_at": float(row.created_at or 0.0),
        "updated_at": float(row.updated_at or 0.0),
    }


def create_or_get_task(
    *,
    task_id: str,
    idempotency_key: str,
    access_token_hash: str,
    locale: str,
    model_key: str,
    freedom: int,
    garment_type: str,
    custom_prompt: Optional[str],
    prompt_mode: str,
    target_filename: str,
    reference_filename: str,
    provider_key: Optional[str] = None,
    model_id: Optional[str] = None,
    detail_options: Optional[Dict[str, Any]] = None,
    input_target_blob: Optional[str] = None,
    input_reference_blob: Optional[str] = None,
    status: str = "queued",
    message_code: str = "pending",
    message: str = "Task submitted",
    db_url: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    SessionFactory, _ = get_session_factory(db_url)
    now = time.time()
    scoped_key = f"{access_token_hash}:{idempotency_key}"
    with SessionFactory() as session:
        existing = (
            session.query(WorkbenchTaskRecord)
            .filter(
                (WorkbenchTaskRecord.idempotency_key == scoped_key)
                | (WorkbenchTaskRecord.task_id == task_id)
            )
            .first()
        )
        if existing is not None:
            return _record_to_dict(existing), False

        record = WorkbenchTaskRecord(
            task_id=task_id,
            idempotency_key=scoped_key,
            access_token_hash=access_token_hash,
            status=status,
            message_code=message_code,
            message=message,
            progress=0,
            locale=locale,
            model_key=model_key,
            provider_key=provider_key or None,
            model_id=model_id or None,
            detail_options_json=serialize_detail_options(detail_options),
            freedom=int(freedom),
            garment_type=garment_type or "",
            custom_prompt=custom_prompt,
            prompt_mode=prompt_mode or "append",
            target_filename=target_filename,
            reference_filename=reference_filename,
            input_target_blob=input_target_blob,
            input_reference_blob=input_reference_blob,
            logs_json="[]",
            attempt_count=0,
            upstream_status="not_started",
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        try:
            session.commit()
            return _record_to_dict(record), True
        except IntegrityError:
            session.rollback()
            existing = (
                session.query(WorkbenchTaskRecord)
                .filter(
                    (WorkbenchTaskRecord.idempotency_key == scoped_key)
                    | (WorkbenchTaskRecord.task_id == task_id)
                )
                .first()
            )
            if existing is not None:
                return _record_to_dict(existing), False
            raise


def upsert_task_from_manifest(manifest: Dict[str, Any], db_url: Optional[str] = None) -> Dict[str, Any]:
    task_id = str(manifest["task_id"])
    raw_idem = str(manifest.get("idempotency_key") or task_id)
    token_hash = str(manifest.get("access_token_hash") or "")
    # If raw_idem already includes token_hash prefix, don't double-prefix.
    if raw_idem.startswith(f"{token_hash}:"):
        raw_idem = raw_idem[len(token_hash) + 1 :]
    record, _ = create_or_get_task(
        task_id=task_id,
        idempotency_key=raw_idem,
        access_token_hash=token_hash,
        locale=str(manifest.get("locale") or "zh-CN"),
        model_key=str(manifest.get("model_key") or "flash"),
        provider_key=manifest.get("provider_key"),
        model_id=manifest.get("model_id"),
        detail_options=parse_detail_options(manifest.get("detail_options")),
        freedom=int(5 if manifest.get("freedom") is None else manifest["freedom"]),
        garment_type=str(manifest.get("garment_type") or ""),
        custom_prompt=manifest.get("custom_prompt"),
        prompt_mode=str(manifest.get("prompt_mode") or "append"),
        target_filename=str(manifest.get("target_filename") or ""),
        reference_filename=str(manifest.get("reference_filename") or ""),
        input_target_blob=manifest.get("input_target_blob"),
        input_reference_blob=manifest.get("input_reference_blob"),
        status=str(manifest.get("status") or "queued"),
        message_code=str(manifest.get("message_code") or "pending"),
        message=str(manifest.get("message") or "Task submitted"),
        db_url=db_url,
    )
    return record


def get_task_record(task_id: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    SessionFactory, _ = get_session_factory(db_url)
    with SessionFactory() as session:
        row = session.get(WorkbenchTaskRecord, task_id)
        return _record_to_dict(row) if row is not None else None


def claim_task_for_worker(
    task_id: str,
    worker_id: str,
    *,
    lease_seconds: int = 90,
    now_ts: Optional[float] = None,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Transactionally claim a queued/pending or lease-expired task for a worker."""
    SessionFactory, engine = get_session_factory(db_url)
    now = float(now_ts if now_ts is not None else time.time())
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run_claim() -> Dict[str, Any]:
        with SessionFactory() as session:
            if is_sqlite:
                session.execute(text("BEGIN IMMEDIATE"))
                row = session.get(WorkbenchTaskRecord, task_id)
            else:
                row = (
                    session.query(WorkbenchTaskRecord)
                    .filter(WorkbenchTaskRecord.task_id == task_id)
                    .with_for_update()
                    .first()
                )
            if row is None:
                session.rollback()
                return {"action": "not_found", "task": None}

            if row.status in TERMINAL_TASK_STATUSES:
                session.commit()
                return {"action": "ack_already_terminal", "task": _record_to_dict(row)}

            active_lease = (
                row.status in {"processing", "checking_quota"}
                and row.lease_expires_at is not None
                and float(row.lease_expires_at) > now
                and row.lease_owner
                and row.lease_owner != worker_id
            )
            if active_lease:
                session.commit()
                return {"action": "skip_active_lease", "task": _record_to_dict(row)}

            if row.status in {"processing", "checking_quota"} and row.upstream_status == "in_flight":
                row.status = "unknown"
                row.message_code = "unknown"
                row.message = "Upstream status unknown after worker lease expired"
                row.upstream_status = "unknown_timeout"
                row.error_code = "WorkerLeaseExpiredDuringUpstream"
                row.error_detail = (
                    "Worker lease expired while upstream AI request was in flight; "
                    "marked unknown to prevent duplicate billing."
                )
                row.lease_owner = None
                row.lease_expires_at = None
                row.updated_at = now
                logs = json.loads(row.logs_json or "[]")
                logs.append("Lease expired during upstream AI call; marked unknown.")
                row.logs_json = json.dumps(logs[-500:], ensure_ascii=False)
                session.commit()
                return {"action": "marked_unknown", "task": _record_to_dict(row)}

            row.status = "processing"
            row.message_code = "initializing"
            row.progress = max(int(row.progress or 0), 5)
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.lease_owner = worker_id
            row.lease_expires_at = now + max(10, int(lease_seconds))
            row.updated_at = now
            session.commit()
            return {"action": "claimed", "task": _record_to_dict(row)}

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run_claim()
    return _run_claim()


def renew_task_lease(
    task_id: str,
    worker_id: str,
    *,
    lease_seconds: int = 90,
    now_ts: Optional[float] = None,
    db_url: Optional[str] = None,
) -> bool:
    SessionFactory, engine = get_session_factory(db_url)
    now = float(now_ts if now_ts is not None else time.time())
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run() -> bool:
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None or row.status in TERMINAL_TASK_STATUSES:
                return False
            if row.lease_owner != worker_id:
                return False
            row.lease_expires_at = now + max(10, int(lease_seconds))
            row.updated_at = now
            session.commit()
            return True

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def update_task_progress(
    task_id: str,
    worker_id: str,
    *,
    progress: Optional[int] = None,
    status: Optional[str] = None,
    message_code: Optional[str] = None,
    message: Optional[str] = None,
    log_line: Optional[str] = None,
    db_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    SessionFactory, engine = get_session_factory(db_url)
    now = time.time()
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run():
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None or (row.lease_owner and row.lease_owner != worker_id):
                return None
            if progress is not None:
                row.progress = int(progress)
            if status is not None:
                row.status = status
            if message_code is not None:
                row.message_code = message_code
            if message is not None:
                row.message = str(message)
            if log_line is not None:
                logs = json.loads(row.logs_json or "[]")
                logs.append(str(log_line))
                row.logs_json = json.dumps(logs[-500:], ensure_ascii=False)
            row.updated_at = now
            session.commit()
            return _record_to_dict(row)

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def mark_upstream_in_flight(
    task_id: str,
    worker_id: str,
    *,
    now_ts: Optional[float] = None,
    db_url: Optional[str] = None,
) -> bool:
    SessionFactory, engine = get_session_factory(db_url)
    now = float(now_ts if now_ts is not None else time.time())
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run() -> bool:
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None or row.lease_owner != worker_id:
                return False
            row.upstream_status = "in_flight"
            row.upstream_started_at = now
            row.updated_at = now
            session.commit()
            return True

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def complete_task(
    task_id: str,
    worker_id: str,
    *,
    result_filename: str,
    output_result_blob: Optional[str],
    freedom: int,
    db_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    SessionFactory, engine = get_session_factory(db_url)
    now = time.time()
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run():
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None:
                return None
            if row.lease_owner and row.lease_owner != worker_id:
                return None
            row.status = "completed"
            row.progress = 100
            row.message_code = "completed"
            row.message = "Generation complete"
            row.result_filename = result_filename
            row.output_result_blob = output_result_blob
            row.freedom = int(freedom)
            row.upstream_status = "succeeded"
            row.upstream_completed_at = now
            row.lease_owner = None
            row.lease_expires_at = None
            row.error_code = None
            row.error_detail = None
            row.updated_at = now
            session.commit()
            return _record_to_dict(row)

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def fail_task(
    task_id: str,
    worker_id: str,
    *,
    error_code: str,
    error_detail: str,
    upstream_status: str = "failed_known",
    db_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    SessionFactory, engine = get_session_factory(db_url)
    now = time.time()
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run():
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None:
                return None
            if row.lease_owner and row.lease_owner != worker_id:
                return None
            row.status = "failed"
            row.progress = 0
            row.message_code = "failed"
            row.message = "Task failed"
            row.error_code = str(error_code)[:128]
            row.error_detail = str(error_detail)[:500]
            row.upstream_status = upstream_status
            row.upstream_completed_at = now
            row.lease_owner = None
            row.lease_expires_at = None
            logs = json.loads(row.logs_json or "[]")
            logs.append(f"Error: {error_detail[:500]}")
            row.logs_json = json.dumps(logs[-500:], ensure_ascii=False)
            row.updated_at = now
            session.commit()
            return _record_to_dict(row)

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def mark_task_unknown(
    task_id: str,
    worker_id: str,
    *,
    error_code: str = "UpstreamResultUnknown",
    error_detail: str = "Upstream AI request timed out; outcome unknown and not auto-retried.",
    db_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    SessionFactory, engine = get_session_factory(db_url)
    now = time.time()
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run():
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None:
                return None
            if row.lease_owner and row.lease_owner != worker_id:
                return None
            row.status = "unknown"
            row.progress = 0
            row.message_code = "unknown"
            row.message = "Task status unknown"
            row.error_code = str(error_code)[:128]
            row.error_detail = str(error_detail)[:500]
            row.upstream_status = "unknown_timeout"
            row.upstream_completed_at = now
            row.lease_owner = None
            row.lease_expires_at = None
            logs = json.loads(row.logs_json or "[]")
            logs.append(f"Unknown: {error_detail[:500]}")
            row.logs_json = json.dumps(logs[-500:], ensure_ascii=False)
            row.updated_at = now
            session.commit()
            return _record_to_dict(row)

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def reset_task_for_retry(
    task_id: str,
    *,
    allow_unknown_retry: bool = False,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    SessionFactory, engine = get_session_factory(db_url)
    now = time.time()
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run() -> Dict[str, Any]:
        with SessionFactory() as session:
            row = session.get(WorkbenchTaskRecord, task_id)
            if row is None:
                raise LookupError("Task not found")
            allowed = {"failed"}
            if allow_unknown_retry:
                allowed.add("unknown")
            if row.status not in allowed:
                raise ValueError(f"Task status '{row.status}' cannot be retried")
            row.status = "queued"
            row.progress = 0
            row.message_code = "pending"
            row.message = "Task re-queued"
            row.error_code = None
            row.error_detail = None
            row.upstream_status = "not_started"
            row.upstream_started_at = None
            row.upstream_completed_at = None
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now
            session.commit()
            return _record_to_dict(row)

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def register_media_file(
    *,
    filename: str,
    blob_name: str,
    media_kind: str,
    access_token_hash: str,
    content_type: str = "image/png",
    task_id: Optional[str] = None,
    db_url: Optional[str] = None,
) -> None:
    SessionFactory, engine = get_session_factory(db_url)
    now = time.time()
    is_sqlite = str(engine.url).startswith("sqlite")

    def _run():
        with SessionFactory() as session:
            row = session.get(WorkbenchMediaRecord, filename)
            if row is None:
                row = WorkbenchMediaRecord(
                    filename=filename,
                    blob_name=blob_name,
                    media_kind=media_kind,
                    content_type=content_type,
                    access_token_hash=access_token_hash,
                    task_id=task_id,
                    created_at=now,
                )
                session.add(row)
            else:
                row.blob_name = blob_name
                row.media_kind = media_kind
                row.content_type = content_type
                row.access_token_hash = access_token_hash
                if task_id:
                    row.task_id = task_id
            session.commit()

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            _run()
    else:
        _run()


def get_media_file(filename: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    SessionFactory, _ = get_session_factory(db_url)
    with SessionFactory() as session:
        row = session.get(WorkbenchMediaRecord, filename)
        if row is None:
            return None
        return {
            "filename": row.filename,
            "blob_name": row.blob_name,
            "media_kind": row.media_kind,
            "content_type": row.content_type,
            "access_token_hash": row.access_token_hash,
            "task_id": row.task_id,
            "created_at": float(row.created_at or 0.0),
        }


def _pt_day_key(now_ts: float) -> str:
    return datetime.fromtimestamp(now_ts, tz=PT_ZONE).strftime("%Y-%m-%d")


def _shanghai_month_key(now_ts: float) -> str:
    return datetime.fromtimestamp(now_ts, tz=SHANGHAI_ZONE).strftime("%Y-%m")


def _seconds_until_next_minute(now_ts: float) -> int:
    now = datetime.utcfromtimestamp(now_ts)
    next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return max(0, int((next_minute - now).total_seconds()))


def _seconds_until_next_pt_midnight(now_ts: float) -> int:
    now = datetime.fromtimestamp(now_ts, tz=PT_ZONE)
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0, int((next_day - now).total_seconds()))


def check_and_consume_shared_rate_limit(
    *,
    identity: str,
    model_key: str,
    token_cost: int,
    limits: Dict[str, int],
    monthly_limit: Optional[int] = None,
    now_ts: Optional[float] = None,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    SessionFactory, engine = get_session_factory(db_url)
    now = float(now_ts if now_ts is not None else time.time())
    minute_id = int(now // 60)
    day_key = _pt_day_key(now)
    month_key = _shanghai_month_key(now)
    is_sqlite = str(engine.url).startswith("sqlite")

    if monthly_limit is None:
        env_monthly = str(os.environ.get("TRYON_MONTHLY_LIMIT", "") or "").strip()
        if env_monthly.isdigit() and int(env_monthly) > 0:
            monthly_limit = int(env_monthly)

    def _run() -> Dict[str, Any]:
        with SessionFactory() as session:
            if is_sqlite:
                session.execute(text("BEGIN IMMEDIATE"))
                row = session.get(WorkbenchRateLimitRecord, (identity, model_key))
            else:
                row = (
                    session.query(WorkbenchRateLimitRecord)
                    .filter(
                        WorkbenchRateLimitRecord.identity == identity,
                        WorkbenchRateLimitRecord.model_key == model_key,
                    )
                    .with_for_update()
                    .first()
                )
            if row is None:
                row = WorkbenchRateLimitRecord(
                    identity=identity,
                    model_key=model_key,
                    minute_id=minute_id,
                    day_key=day_key,
                    month_key=month_key,
                    rpm_used=0,
                    tpm_used=0,
                    rpd_used=0,
                    monthly_used=0,
                    updated_at=now,
                )
                session.add(row)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    row = session.get(WorkbenchRateLimitRecord, (identity, model_key))

            if row.minute_id != minute_id:
                row.minute_id = minute_id
                row.rpm_used = 0
                row.tpm_used = 0
            if row.day_key != day_key:
                row.day_key = day_key
                row.rpd_used = 0
            if row.month_key != month_key:
                row.month_key = month_key
                row.monthly_used = 0

            rpm_used = int(row.rpm_used or 0)
            tpm_used = int(row.tpm_used or 0)
            rpd_used = int(row.rpd_used or 0)
            monthly_used = int(row.monthly_used or 0)

            if rpm_used + 1 > int(limits["rpm"]):
                session.rollback()
                raise RuntimeError(
                    f"触发 RPM 限制: {rpm_used}/{limits['rpm']}，请等待 {_seconds_until_next_minute(now)} 秒后重试"
                )
            if tpm_used + token_cost > int(limits["tpm"]):
                session.rollback()
                raise RuntimeError(
                    f"触发 TPM 限制: {tpm_used}/{limits['tpm']}，当前请求估算 {token_cost} tokens，请等待 {_seconds_until_next_minute(now)} 秒后重试"
                )
            if rpd_used + 1 > int(limits["rpd"]):
                session.rollback()
                raise RuntimeError(
                    f"触发 RPD 限制: {rpd_used}/{limits['rpd']}，将在 PT 零点后重置（约 {_seconds_until_next_pt_midnight(now)} 秒）"
                )
            if monthly_limit is not None and monthly_used + 1 > int(monthly_limit):
                session.rollback()
                raise RuntimeError(f"触发月度全站试衣限额: {monthly_used}/{monthly_limit}，请联系管理员调整配额")

            row.rpm_used = rpm_used + 1
            row.tpm_used = tpm_used + token_cost
            row.rpd_used = rpd_used + 1
            row.monthly_used = monthly_used + 1
            row.updated_at = now
            session.commit()
            return {
                "rpm_used": row.rpm_used,
                "tpm_used": row.tpm_used,
                "rpd_used": row.rpd_used,
                "monthly_used": row.monthly_used,
            }

    if is_sqlite:
        with _SQLITE_WRITE_LOCK:
            return _run()
    return _run()


def get_shared_rate_status_snapshot(
    *,
    identity: str,
    model_key: str,
    limits: Dict[str, int],
    now_ts: Optional[float] = None,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    SessionFactory, _ = get_session_factory(db_url)
    now = float(now_ts if now_ts is not None else time.time())
    minute_id = int(now // 60)
    day_key = _pt_day_key(now)
    month_key = _shanghai_month_key(now)
    with SessionFactory() as session:
        row = session.get(WorkbenchRateLimitRecord, (identity, model_key))
        rpm_used = int(row.rpm_used) if row and row.minute_id == minute_id else 0
        tpm_used = int(row.tpm_used) if row and row.minute_id == minute_id else 0
        rpd_used = int(row.rpd_used) if row and row.day_key == day_key else 0
        monthly_used = int(row.monthly_used) if row and row.month_key == month_key else 0
    return {
        "rpm_limit": int(limits["rpm"]),
        "tpm_limit": int(limits["tpm"]),
        "rpd_limit": int(limits["rpd"]),
        "rpm_used": rpm_used,
        "tpm_used": tpm_used,
        "rpd_used": rpd_used,
        "monthly_used": monthly_used,
        "minute_reset_seconds": _seconds_until_next_minute(now),
        "daily_reset_seconds": _seconds_until_next_pt_midnight(now),
        "daily_reset_timezone": "PT",
    }

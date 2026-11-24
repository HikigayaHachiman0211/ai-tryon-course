from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hmac
import time
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import (
    create_access_token,
    get_current_admin,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.database import AdminUser, get_db
from app.routers import to_beijing_str

router = APIRouter(prefix="/api/auth", tags=["auth"])

_RECOVERY_WINDOW_SEC = 300.0
_RECOVERY_MAX_FAILURES = 5
_RECOVERY_MAX_IPS = 1024
_recovery_failures: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _prune_attempts(ip: str, now: float) -> list[float]:
    recent = [ts for ts in _recovery_failures.get(ip, []) if now - ts < _RECOVERY_WINDOW_SEC]
    if recent:
        _recovery_failures[ip] = recent
    else:
        _recovery_failures.pop(ip, None)
    return recent


def _enforce_recovery_rate_limit(ip: str) -> None:
    recent = _prune_attempts(ip, time.monotonic())
    if len(recent) >= _RECOVERY_MAX_FAILURES:
        raise HTTPException(status_code=429, detail={"code": "AUTH_TOO_MANY_ATTEMPTS"})


def _record_recovery_failure(ip: str) -> None:
    now = time.monotonic()
    if len(_recovery_failures) >= _RECOVERY_MAX_IPS and ip not in _recovery_failures:
        _recovery_failures.clear()
    recent = _prune_attempts(ip, now)
    recent.append(now)
    _recovery_failures[ip] = recent


def _clear_recovery_failures(ip: str) -> None:
    _recovery_failures.pop(ip, None)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str | None = None
    old_password: str | None = None
    new_password: str


class RecoveryQuestionRequest(BaseModel):
    current_password: str
    security_question: str
    security_answer: str


class ResetPasswordRequest(BaseModel):
    username: str
    method: Literal["security_question", "recovery_key"]
    proof: str
    new_password: str


@router.post("/login")
def login(body: LoginRequest, db=Depends(get_db)):
    user = db.query(AdminUser).filter_by(username=body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_CREDENTIALS"})
    user.last_login = datetime.now(ZoneInfo("Asia/Shanghai"))
    db.commit()
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    current = body.current_password if body.current_password is not None else (body.old_password or "")
    if not verify_password(current, admin.password_hash):
        raise HTTPException(status_code=400, detail={"code": "AUTH_INVALID_CREDENTIALS"})
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail={"code": "AUTH_PASSWORD_TOO_SHORT"})
    admin.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


@router.get("/recovery-options")
def recovery_options(
    username: str = Query(default="admin"),
    db=Depends(get_db),
):
    settings = get_settings()
    user = db.query(AdminUser).filter_by(username=username.strip()).first()
    has_question = bool(user and user.recovery_question and user.recovery_answer_hash)
    return {
        "has_security_question": has_question,
        "security_question": user.recovery_question if has_question else None,
        "has_recovery_key": bool(settings.ADMIN_RECOVERY_KEY.strip()),
    }


@router.post("/recovery-question")
def update_recovery_question(
    body: RecoveryQuestionRequest,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    if not verify_password(body.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail={"code": "AUTH_INVALID_CREDENTIALS"})
    question = body.security_question.strip()
    answer = body.security_answer.strip()
    if not question or not answer:
        raise HTTPException(status_code=400, detail={"code": "AUTH_SECURITY_QUESTION_REQUIRED"})
    admin.recovery_question = question[:255]
    admin.recovery_answer_hash = hash_password(answer)
    db.commit()
    return {"security_question": admin.recovery_question}


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db=Depends(get_db),
):
    ip = _client_ip(request)
    _enforce_recovery_rate_limit(ip)
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail={"code": "AUTH_PASSWORD_TOO_SHORT"})

    proof = body.proof.strip()
    user = db.query(AdminUser).filter_by(username=body.username.strip()).first()

    if body.method == "recovery_key":
        expected_key = get_settings().ADMIN_RECOVERY_KEY.strip()
        if not expected_key:
            raise HTTPException(status_code=400, detail={"code": "AUTH_RECOVERY_NOT_CONFIGURED"})
        if not user or not proof or not hmac.compare_digest(proof.encode("utf-8"), expected_key.encode("utf-8")):
            _record_recovery_failure(ip)
            raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_RECOVERY_PROOF"})
    else:
        if user and (not user.recovery_question or not user.recovery_answer_hash):
            raise HTTPException(status_code=400, detail={"code": "AUTH_RECOVERY_NOT_CONFIGURED"})
        if not user or not proof or not user.recovery_answer_hash or not verify_password(proof, user.recovery_answer_hash):
            _record_recovery_failure(ip)
            raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_RECOVERY_PROOF"})

    _clear_recovery_failures(ip)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


@router.get("/me")
def me(admin: AdminUser = Depends(get_current_admin)):
    return {
        "id": admin.id,
        "username": admin.username,
        "role": admin.role,
        "recovery_question": admin.recovery_question,
        "created_at": to_beijing_str(admin.created_at),
        "last_login": to_beijing_str(admin.last_login),
    }

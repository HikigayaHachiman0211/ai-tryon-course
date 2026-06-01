from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import (
    create_access_token,
    get_current_admin,
    hash_password,
    verify_password,
)
from app.database import AdminUser, get_db
from app.routers import to_beijing_str

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
def login(body: LoginRequest, db=Depends(get_db)):
    user = db.query(AdminUser).filter_by(username=body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
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
    if not verify_password(body.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    admin.password_hash = hash_password(body.new_password)
    db.commit()
    return {"detail": "密码已更新"}


@router.get("/me")
def me(admin: AdminUser = Depends(get_current_admin)):
    return {
        "id": admin.id,
        "username": admin.username,
        "role": admin.role,
        "created_at": to_beijing_str(admin.created_at),
        "last_login": to_beijing_str(admin.last_login),
    }

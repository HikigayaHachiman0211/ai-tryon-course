"""Budgeted realtime try-on endpoints for Decart Lucy VTON and Xmax X2.1."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import secrets
import time
from contextlib import suppress
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.concurrency import run_in_threadpool
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app import reactor_client
from app import realtime_budget as budget
from app import xmax_client
from app.task_db import generate_access_token, hash_access_token

router = APIRouter(prefix="/api/realtime-tryon", tags=["tryon-realtime"])
logger = logging.getLogger(__name__)
VISITOR_COOKIE = "lucy_visitor"
MAX_SIGNAL_BYTES = 384 * 1024
MAX_IMAGE_BYTES = 256 * 1024
PROVIDER_USER_AGENT = "decart-js-sdk/0.2.14 lang/js runtime/browser"
PROVIDER_REASONS = {"disconnect", "timeout", "error", "insufficient_credits", "moderation_violation", "session_limit"}

_ACTIVE_WATCHDOGS: dict[str, asyncio.Task] = {}
_SETTLE_LOCKS: dict[str, asyncio.Lock] = {}


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_code: str = Field(default="", max_length=256)
    seconds: StrictInt
    max_cents: StrictInt


class XmaxStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_code: str = Field(default="", max_length=256)
    seconds: StrictInt
    max_cents: StrictInt
    model: str = Field(default="", max_length=64)


class XmaxAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_session_id: str = Field(min_length=1, max_length=128)


class ReactorStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_code: str = Field(default="", max_length=256)
    seconds: StrictInt
    max_cents: StrictInt
    model: str = Field(default="", max_length=64)


class ReactorAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_session_id: str = Field(min_length=1, max_length=128)


def response(data, status=200):
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "private, no-store"})


def error(code, status):
    return response({"error": {"code": code}}, status)


def settings():
    try:
        return budget.load_settings()
    except ValueError:
        return None


def xmax_settings():
    try:
        return budget.load_xmax_settings()
    except ValueError:
        return None


def reactor_settings():
    try:
        return budget.load_reactor_settings()
    except ValueError:
        return None


def same_origin(connection, cfg):
    scheme = {"ws": "http", "wss": "https"}.get(connection.url.scheme, connection.url.scheme)
    expected = (cfg.origin if cfg else "") or f"{scheme}://{connection.url.netloc}"
    return connection.headers.get("origin") == expected


def visitor_cookie(connection):
    token = connection.cookies.get(VISITOR_COOKIE, "")
    return token if re.fullmatch(r"[A-Za-z0-9_-]{32}", token) else ""


def owner(connection):
    return hash_access_token(visitor_cookie(connection))


def _apply_visitor_cookie(result, request, cfg, token: str):
    origin = cfg.origin if cfg else ""
    result.set_cookie(
        VISITOR_COOKIE,
        token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=bool(origin.startswith("https://") or request.url.scheme == "https"),
    )


def _disabled_reason(cfg) -> str:
    if not cfg:
        return "invalid_config"
    if not cfg.enabled:
        return "disabled"
    if not cfg.api_key:
        return "missing_api_key"
    return "missing_access_code"


async def _serialize_decart_status(cfg, effective_owner: str) -> dict:
    if not cfg or not cfg.available:
        return {"available": False, "reason": _disabled_reason(cfg)}
    quota = None
    try:
        quota = await run_in_threadpool(budget.status_snapshot, cfg, effective_owner)
    except Exception as exc:
        logger.warning("Decart status snapshot failed (%s)", type(exc).__name__)
    return {
        "available": True,
        "provider": "decart",
        "model": budget.MODEL,
        "min_seconds": budget.MIN_SECONDS,
        "max_seconds": cfg.max_seconds,
        "default_seconds": cfg.default_seconds,
        "cents_per_second": cfg.cents_per_second,
        "require_access_code": cfg.require_access_code,
        "default_prompt": cfg.default_prompt,
        "quota": quota,
    }


async def _serialize_xmax_status(cfg: budget.XmaxSettings | None, effective_owner: str) -> dict:
    if not cfg or not cfg.available:
        return {"available": False, "reason": _disabled_reason(cfg)}
    quota = None
    try:
        quota = await run_in_threadpool(budget.status_snapshot_xmax, cfg, effective_owner)
    except Exception as exc:
        logger.warning("Xmax status snapshot failed (%s)", type(exc).__name__)
    return {
        "available": True,
        "provider": "xmax",
        "environment": cfg.environment,
        "model": cfg.default_model,
        "allowed_models": list(cfg.allowed_models),
        "camera_preset": cfg.camera_preset,
        "face_restoration": cfg.face_restoration,
        "min_seconds": cfg.min_seconds,
        "max_seconds": cfg.max_seconds,
        "default_seconds": cfg.default_seconds,
        "credits_per_second": cfg.credits_per_second,
        "cents_per_minute": cfg.cents_per_minute,
        "min_account_credits": cfg.min_account_credits,
        "require_access_code": cfg.require_access_code,
        "default_prompt": cfg.default_prompt,
        "quota": quota,
    }


async def _serialize_reactor_status(cfg: budget.ReactorSettings | None, effective_owner: str) -> dict:
    if not cfg or not cfg.available:
        return {"available": False, "reason": _disabled_reason(cfg)}
    quota = None
    try:
        quota = await run_in_threadpool(budget.status_snapshot_reactor, cfg, effective_owner)
    except Exception as exc:
        logger.warning("Reactor status snapshot failed (%s)", type(exc).__name__)
    return {
        "available": True,
        "provider": "reactor",
        "model": cfg.default_model,
        "allowed_models": list(cfg.allowed_models),
        "min_seconds": cfg.min_seconds,
        "max_seconds": cfg.max_seconds,
        "default_seconds": cfg.default_seconds,
        "credits_per_second": cfg.credits_per_second,
        "cents_per_minute": cfg.cents_per_minute,
        "min_account_credits": cfg.min_account_credits,
        "require_access_code": cfg.require_access_code,
        "default_prompt": cfg.default_prompt,
        "quota": quota,
    }


@router.get("/config")
async def config(request: Request):
    cfg = settings()
    if not cfg or not cfg.available:
        return response({"available": False})
    result = response({
        "available": True, "model": budget.MODEL, "min_seconds": budget.MIN_SECONDS,
        "max_seconds": cfg.max_seconds, "cents_per_second": cfg.cents_per_second,
    })
    if not visitor_cookie(request):
        _apply_visitor_cookie(result, request, cfg, generate_access_token())
    return result


@router.get("/status")
async def status(request: Request):
    cfg = settings()
    if not cfg:
        return response({"available": False, "reason": "invalid_config"})
    if not cfg.available:
        return response({"available": False, "reason": _disabled_reason(cfg)})

    raw_cookie = visitor_cookie(request)
    new_token = "" if raw_cookie else generate_access_token()
    effective_owner = hash_access_token(raw_cookie or new_token)
    quota = None
    try:
        quota = await run_in_threadpool(budget.status_snapshot, cfg, effective_owner)
    except Exception as exc:
        logger.warning("Decart status snapshot failed (%s)", type(exc).__name__)
    result = response({
        "available": True,
        "model": budget.MODEL,
        "min_seconds": budget.MIN_SECONDS,
        "max_seconds": cfg.max_seconds,
        "default_seconds": cfg.default_seconds,
        "cents_per_second": cfg.cents_per_second,
        "require_access_code": cfg.require_access_code,
        "default_prompt": cfg.default_prompt,
        "quota": quota,
    })
    if new_token:
        _apply_visitor_cookie(result, request, cfg, new_token)
    return result


@router.get("/providers")
async def providers_status(request: Request):
    decart_cfg = settings()
    xmax_cfg = xmax_settings()
    reactor_cfg = reactor_settings()
    any_available = bool(
        (decart_cfg and decart_cfg.available)
        or (xmax_cfg and xmax_cfg.available)
        or (reactor_cfg and reactor_cfg.available)
    )

    raw_cookie = visitor_cookie(request)
    new_token = "" if (raw_cookie or not any_available) else generate_access_token()
    effective_owner = hash_access_token(raw_cookie or new_token) if (raw_cookie or new_token) else ""

    decart_payload = await _serialize_decart_status(decart_cfg, effective_owner)
    xmax_payload = await _serialize_xmax_status(xmax_cfg, effective_owner)
    reactor_payload = await _serialize_reactor_status(reactor_cfg, effective_owner)

    if decart_payload["available"]:
        default_provider = "decart"
    elif reactor_payload["available"]:
        default_provider = "reactor"
    elif xmax_payload["available"]:
        default_provider = "xmax"
    elif reactor_cfg and reactor_cfg.enabled:
        default_provider = "reactor"
    elif xmax_cfg and xmax_cfg.enabled:
        default_provider = "xmax"
    else:
        default_provider = "decart"

    result = response({
        "any_available": any_available,
        "default_provider": default_provider,
        "providers": {
            "decart": decart_payload,
            "xmax": xmax_payload,
            "reactor": reactor_payload,
        },
    })
    if new_token:
        cookie_cfg = next(
            (c for c in (decart_cfg, reactor_cfg, xmax_cfg) if c and c.available),
            decart_cfg or reactor_cfg or xmax_cfg,
        )
        _apply_visitor_cookie(result, request, cookie_cfg, new_token)
    return result


@router.post("/sessions")
async def start(payload: StartRequest, request: Request):
    cfg = settings()
    if not cfg or not cfg.available:
        return error("unavailable", 503)
    visitor = owner(request)
    if not visitor or not same_origin(request, cfg):
        return error("access_denied", 403)
    if cfg.require_access_code and not secrets.compare_digest(cfg.access_code.encode(), payload.access_code.encode()):
        return error("invalid_access_code", 403)
    if payload.max_cents != payload.seconds * cfg.cents_per_second:
        return error("quote_changed", 409)
    try:
        row = await run_in_threadpool(budget.reserve, cfg, visitor, payload.seconds)
    except budget.BudgetDenied as exc:
        code = str(exc)
        return error(code, 400 if code == "invalid_duration" else 429)
    except Exception as exc:
        logger.warning("Decart admission failed (%s)", type(exc).__name__)
        return error("ledger_unavailable", 503)
    return response(budget.receipt(row), 201)


@router.post("/xmax/sessions")
async def start_xmax(payload: XmaxStartRequest, request: Request):
    cfg = xmax_settings()
    if not cfg or not cfg.available:
        return error("unavailable", 503)
    visitor = owner(request)
    if not visitor or not same_origin(request, cfg):
        return error("access_denied", 403)
    if cfg.require_access_code and not secrets.compare_digest(cfg.access_code.encode(), payload.access_code.encode()):
        return error("invalid_access_code", 403)

    requested_model = payload.model.strip().lower() if payload.model else cfg.default_model
    if requested_model not in cfg.allowed_models:
        return error("invalid_model", 400)

    expected_cents = budget.xmax_session_cents(payload.seconds, cfg.cents_per_minute)
    if payload.max_cents != expected_cents:
        return error("quote_changed", 409)

    try:
        row = await run_in_threadpool(budget.reserve_xmax, cfg, visitor, payload.seconds, model_id=requested_model)
    except budget.BudgetDenied as exc:
        code = str(exc)
        status_code = 400 if code in {"invalid_duration", "invalid_model"} else 429
        return error(code, status_code)
    except Exception as exc:
        logger.warning("Xmax admission failed (%s)", type(exc).__name__)
        return error("ledger_unavailable", 503)
    return response(budget.receipt(row), 201)


def _get_settle_lock(session_id: str) -> asyncio.Lock:
    lock = _SETTLE_LOCKS.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _SETTLE_LOCKS[session_id] = lock
    return lock


async def _settle_and_close_xmax_session(
    session_id: str,
    cfg: budget.XmaxSettings,
    temp_key: str,
    *,
    reason: str,
) -> None:
    lock = _get_settle_lock(session_id)
    async with lock:
        row = await run_in_threadpool(budget.get_session_row, session_id)
        if not row or row.provider_key != "xmax":
            return
        if row.state == "ended" and row.provider_temp_key_encrypted is None:
            return

        effective_temp_key = temp_key or await run_in_threadpool(budget.decrypt_xmax_temp_key, row)
        provider_session_id = row.provider_session_id

        if provider_session_id:
            with suppress(Exception):
                await xmax_client.close_session(
                    effective_temp_key or cfg.api_key,
                    provider_session_id,
                    base_url=cfg.base_url,
                    timeout=5.0,
                )

        if effective_temp_key:
            with suppress(Exception):
                await xmax_client.deactivate_temporary_api_key(
                    cfg.api_key,
                    effective_temp_key,
                    base_url=cfg.base_url,
                    timeout=5.0,
                )

        consumed_credits: float | None = None
        if effective_temp_key:
            with suppress(Exception):
                tk_status = await xmax_client.get_temporary_api_key_status(
                    cfg.api_key,
                    effective_temp_key,
                    base_url=cfg.base_url,
                    timeout=5.0,
                )
                raw_credit = tk_status.get("consumedCredit")
                if isinstance(raw_credit, (int, float)) and not isinstance(raw_credit, bool) and raw_credit >= 0:
                    consumed_credits = float(raw_credit)

        if consumed_credits is None and provider_session_id:
            with suppress(Exception):
                sess_status = await xmax_client.get_session_status(
                    cfg.api_key,
                    provider_session_id,
                    base_url=cfg.base_url,
                    timeout=5.0,
                )
                raw_credit = sess_status.get("consumedCredit")
                if isinstance(raw_credit, (int, float)) and not isinstance(raw_credit, bool) and raw_credit >= 0:
                    consumed_credits = float(raw_credit)

        await run_in_threadpool(
            budget.finalize_xmax,
            session_id,
            reason=reason,
            provider_session_id=provider_session_id,
            provider_credits=consumed_credits,
            clear_temp_key=True,
        )


def _start_xmax_watchdog(session_id: str, cfg: budget.XmaxSettings, temp_key: str, deadline_epoch: float) -> None:
    existing = _ACTIVE_WATCHDOGS.pop(session_id, None)
    if existing and not existing.done():
        existing.cancel()

    async def _watch():
        stop_reason = "timeout"
        try:
            while time.time() < deadline_epoch:
                row = await run_in_threadpool(budget.get_session_row, session_id)
                if not row or row.state == "ended":
                    return
                if row.stop_requested:
                    stop_reason = "stopped"
                    break
                await asyncio.sleep(1.0)
            await _settle_and_close_xmax_session(session_id, cfg, temp_key, reason=stop_reason)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Xmax watchdog failed for %s (%s)", session_id, type(exc).__name__)
        finally:
            _ACTIVE_WATCHDOGS.pop(session_id, None)

    task = asyncio.create_task(_watch())
    _ACTIVE_WATCHDOGS[session_id] = task


@router.post("/xmax/sessions/{session_id}/token")
async def claim_xmax_token(session_id: str, request: Request):
    cfg = xmax_settings()
    if not cfg or not cfg.available:
        return error("unavailable", 503)
    visitor = owner(request)
    if not visitor or not same_origin(request, cfg):
        return error("access_denied", 403)
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        return error("session_missing", 404)

    try:
        row = await run_in_threadpool(budget.claim_xmax, session_id, visitor)
    except Exception as exc:
        logger.warning("Xmax claim failed (%s)", type(exc).__name__)
        return error("ledger_unavailable", 503)
    if not row:
        return error("session_unavailable", 409)

    required_credits = max(cfg.min_account_credits, int(row.max_credits or 0))
    if cfg.min_account_credits > 0:
        try:
            balance = await xmax_client.get_balance(cfg.api_key, base_url=cfg.base_url, timeout=8.0)
        except xmax_client.XmaxApiError as exc:
            await run_in_threadpool(
                budget.finalize_xmax, row.id, reason="provider_error", zero_charge=True, clear_temp_key=True,
            )
            logger.warning("Xmax balance check rejected (%s)", type(exc).__name__)
            return error("provider_error", 502)
        except Exception as exc:
            await run_in_threadpool(
                budget.finalize_xmax, row.id, reason="provider_error", zero_charge=True, clear_temp_key=True,
            )
            logger.warning("Xmax balance check failed (%s)", type(exc).__name__)
            return error("provider_error", 502)
        if balance < required_credits:
            await run_in_threadpool(
                budget.finalize_xmax, row.id, reason="insufficient_credits", zero_charge=True, clear_temp_key=True,
            )
            return error("insufficient_credits", 429)

    points_limit = max(1, int(row.max_credits or (row.limit_seconds * cfg.credits_per_second)))
    expire_seconds = max(60, int(row.limit_seconds) + budget.XMAX_SETUP_SECONDS)
    try:
        token_data = await xmax_client.create_temporary_api_key(
            cfg.api_key,
            base_url=cfg.base_url,
            expire_seconds=expire_seconds,
            points_limit=points_limit,
            session_limit=1,
            timeout=10.0,
        )
    except xmax_client.XmaxApiError as exc:
        err_code = "insufficient_credits" if exc.api_code == 46019 else "provider_error"
        await run_in_threadpool(
            budget.finalize_xmax, row.id, reason=err_code, zero_charge=True, clear_temp_key=True,
        )
        return error(err_code, 429 if err_code == "insufficient_credits" else 502)
    except Exception as exc:
        await run_in_threadpool(
            budget.finalize_xmax, row.id, reason="provider_error", zero_charge=True, clear_temp_key=True,
        )
        logger.warning("Xmax temporary key creation failed (%s)", type(exc).__name__)
        return error("provider_error", 502)

    temp_key = str(token_data.get("temporaryApiKey") or "").strip()
    temp_uid = str(token_data.get("uid") or "").strip()
    await run_in_threadpool(
        budget.save_xmax_temp_key,
        row.id,
        temp_key_uid=temp_uid,
        temp_key_raw=temp_key,
    )

    _start_xmax_watchdog(row.id, cfg, temp_key, row.hold_until)

    model_id = row.model_id or cfg.default_model
    return response({
        "session_id": row.id,
        "temporary_api_key": temp_key,
        "environment": cfg.environment,
        "model": model_id,
        "camera_preset": xmax_client.normalize_camera_preset(model_id, cfg.camera_preset),
        "face_restoration": cfg.face_restoration,
        "max_seconds": row.limit_seconds,
        "max_credits": points_limit,
        "max_cents": budget.xmax_session_cents(row.limit_seconds, int(row.cents_per_minute or cfg.cents_per_minute)),
        "expires_at": token_data.get("expireTimestamp"),
    })


@router.post("/xmax/sessions/{session_id}/attach")
async def attach_xmax_session(session_id: str, payload: XmaxAttachRequest, request: Request):
    cfg = xmax_settings()
    visitor = owner(request)
    if not visitor or not cfg or not same_origin(request, cfg):
        return error("access_denied", 403)
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        return error("session_missing", 404)
    attached = await run_in_threadpool(
        budget.attach_xmax_provider_session,
        session_id,
        visitor,
        payload.provider_session_id,
    )
    if not attached:
        return error("session_missing", 404)
    return response({"ok": True})


@router.post("/reactor/sessions")
async def start_reactor(payload: ReactorStartRequest, request: Request):
    cfg = reactor_settings()
    if not cfg or not cfg.available:
        return error("unavailable", 503)
    visitor = owner(request)
    if not visitor or not same_origin(request, cfg):
        return error("access_denied", 403)
    if cfg.require_access_code and not secrets.compare_digest(cfg.access_code.encode(), payload.access_code.encode()):
        return error("invalid_access_code", 403)

    raw_model = payload.model.strip().lower()
    requested_model = reactor_client.REACTOR_MODEL_ALIASES.get(raw_model, raw_model) if raw_model else cfg.default_model
    if requested_model not in cfg.allowed_models:
        return error("invalid_model", 400)

    expected_cents = budget.reactor_session_cents(payload.seconds, cfg.cents_per_minute)
    if payload.max_cents != expected_cents:
        return error("quote_changed", 409)

    try:
        row = await run_in_threadpool(budget.reserve_reactor, cfg, visitor, payload.seconds, model_id=requested_model)
    except budget.BudgetDenied as exc:
        code = str(exc)
        status_code = 400 if code in {"invalid_duration", "invalid_model"} else 429
        return error(code, status_code)
    except Exception as exc:
        logger.warning("Reactor admission failed (%s)", type(exc).__name__)
        return error("ledger_unavailable", 503)
    return response(budget.receipt(row), 201)


async def _settle_and_close_reactor_session(
    session_id: str,
    cfg: budget.ReactorSettings,
    *,
    reason: str,
) -> None:
    lock = _get_settle_lock(session_id)
    async with lock:
        row = await run_in_threadpool(budget.get_session_row, session_id)
        if not row or row.provider_key != "reactor" or row.state == "ended":
            return

        provider_session_id = row.provider_session_id
        billed_seconds: float | None = None
        if provider_session_id:
            with suppress(Exception):
                await reactor_client.close_session(
                    cfg.api_key,
                    provider_session_id,
                    base_url=cfg.base_url,
                    reason=reason,
                    timeout=5.0,
                )
            with suppress(Exception):
                usage_payload = await reactor_client.get_session_usage(
                    cfg.api_key,
                    provider_session_id,
                    base_url=cfg.base_url,
                    timeout=5.0,
                )
                if usage_payload:
                    extracted_sec, _ = reactor_client.extract_session_billed_seconds(usage_payload)
                    billed_seconds = extracted_sec

        await run_in_threadpool(
            budget.finalize_reactor,
            session_id,
            reason=reason,
            provider_session_id=provider_session_id,
            provider_seconds=billed_seconds,
        )


def _start_reactor_watchdog(session_id: str, cfg: budget.ReactorSettings, deadline_epoch: float) -> None:
    existing = _ACTIVE_WATCHDOGS.pop(session_id, None)
    if existing and not existing.done():
        existing.cancel()

    async def _watch():
        stop_reason = "timeout"
        try:
            while time.time() < deadline_epoch:
                row = await run_in_threadpool(budget.get_session_row, session_id)
                if not row or row.state == "ended":
                    return
                if row.stop_requested:
                    stop_reason = "stopped"
                    break
                await asyncio.sleep(1.0)
            await _settle_and_close_reactor_session(session_id, cfg, reason=stop_reason)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Reactor watchdog failed for %s (%s)", session_id, type(exc).__name__)
        finally:
            _ACTIVE_WATCHDOGS.pop(session_id, None)

    task = asyncio.create_task(_watch())
    _ACTIVE_WATCHDOGS[session_id] = task


@router.post("/reactor/sessions/{session_id}/token")
async def claim_reactor_token(session_id: str, request: Request):
    cfg = reactor_settings()
    if not cfg or not cfg.available:
        return error("unavailable", 503)
    visitor = owner(request)
    if not visitor or not same_origin(request, cfg):
        return error("access_denied", 403)
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        return error("session_missing", 404)

    try:
        row = await run_in_threadpool(budget.claim_reactor, session_id, visitor)
    except Exception as exc:
        logger.warning("Reactor claim failed (%s)", type(exc).__name__)
        return error("ledger_unavailable", 503)
    if not row:
        return error("session_unavailable", 409)

    required_credits = max(cfg.min_account_credits, int(row.max_credits or 0))
    if cfg.min_account_credits > 0:
        try:
            bal_info = await reactor_client.get_balance(cfg.api_key, base_url=cfg.base_url, timeout=8.0)
            balance = float(bal_info.get("balance") or 0.0)
        except reactor_client.ReactorApiError as exc:
            await run_in_threadpool(
                budget.finalize_reactor, row.id, reason="provider_error", zero_charge=True,
            )
            logger.warning("Reactor balance check rejected (%s)", type(exc).__name__)
            return error("provider_error", 502)
        except Exception as exc:
            await run_in_threadpool(
                budget.finalize_reactor, row.id, reason="provider_error", zero_charge=True,
            )
            logger.warning("Reactor balance check failed (%s)", type(exc).__name__)
            return error("provider_error", 502)
        if balance < required_credits:
            await run_in_threadpool(
                budget.finalize_reactor, row.id, reason="insufficient_credits", zero_charge=True,
            )
            return error("insufficient_credits", 429)

    model_id = row.model_id or cfg.default_model
    expire_seconds = max(60, int(row.limit_seconds) + budget.REACTOR_SETUP_SECONDS)
    try:
        token_data = await reactor_client.create_scoped_jwt(
            cfg.api_key,
            base_url=cfg.base_url,
            model_name=model_id,
            max_session_duration_seconds=row.limit_seconds,
            expire_seconds=expire_seconds,
            max_sessions=1,
            timeout=10.0,
        )
    except reactor_client.ReactorApiError as exc:
        err_code = "insufficient_credits" if exc.http_status in (402, 429) else "provider_error"
        await run_in_threadpool(
            budget.finalize_reactor, row.id, reason=err_code, zero_charge=True,
        )
        return error(err_code, 429 if err_code == "insufficient_credits" else 502)
    except Exception as exc:
        await run_in_threadpool(
            budget.finalize_reactor, row.id, reason="provider_error", zero_charge=True,
        )
        logger.warning("Reactor scoped JWT creation failed (%s)", type(exc).__name__)
        return error("provider_error", 502)

    _start_reactor_watchdog(row.id, cfg, row.hold_until)

    return response({
        "session_id": row.id,
        "jwt": str(token_data.get("jwt") or ""),
        "api_url": cfg.base_url,
        "model": model_id,
        "max_seconds": row.limit_seconds,
        "max_credits": int(row.max_credits or (row.limit_seconds * cfg.credits_per_second)),
        "max_cents": budget.reactor_session_cents(row.limit_seconds, int(row.cents_per_minute or cfg.cents_per_minute)),
        "expires_at": token_data.get("expires_at"),
    })


@router.post("/reactor/sessions/{session_id}/attach")
async def attach_reactor_session(session_id: str, payload: ReactorAttachRequest, request: Request):
    cfg = reactor_settings()
    visitor = owner(request)
    if not visitor or not cfg or not same_origin(request, cfg):
        return error("access_denied", 403)
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        return error("session_missing", 404)
    attached = await run_in_threadpool(
        budget.attach_reactor_provider_session,
        session_id,
        visitor,
        payload.provider_session_id,
    )
    if not attached:
        return error("session_missing", 404)
    return response({"ok": True})


@router.get("/sessions/{session_id}")
async def session_receipt(session_id: str, request: Request):
    visitor = owner(request)
    if not visitor or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        return error("session_missing", 404)
    data = await run_in_threadpool(budget.get_receipt, session_id, visitor)
    return response(data) if data else error("session_missing", 404)


def _matching_origin_cfg(connection, *, provider_hint: str | None = None):
    candidates = []
    if provider_hint == "reactor":
        candidates = [reactor_settings(), xmax_settings(), settings()]
    elif provider_hint == "xmax":
        candidates = [xmax_settings(), reactor_settings(), settings()]
    elif provider_hint == "decart":
        candidates = [settings(), reactor_settings(), xmax_settings()]
    else:
        candidates = [settings(), reactor_settings(), xmax_settings()]
    for cfg in candidates:
        if cfg and same_origin(connection, cfg):
            return cfg
    return None


_STOP_REASON_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_STOP_SECRET_RE = re.compile(
    r"(?:\b(?:uk|tk|rk)-[A-Za-z0-9_-]+|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)?|\bBearer\s+[A-Za-z0-9._~+/-]+=*)",
    re.IGNORECASE,
)


def _sanitize_client_stop_meta(raw) -> tuple[str, str, str]:
    if not isinstance(raw, dict):
        return "stopped", "", ""
    raw_reason = str(raw.get("reason") or "").strip().lower()
    stop_reason = raw_reason if _STOP_REASON_RE.fullmatch(raw_reason) else "stopped"
    raw_stage = str(raw.get("stage") or "").strip().lower()
    stage = re.sub(r"[^a-z0-9_-]", "", raw_stage)[:24]
    raw_detail = str(raw.get("detail") or "").strip()
    detail = _STOP_SECRET_RE.sub("[redacted]", raw_detail)
    detail = re.sub(r"\s+", " ", detail).strip()[:180]
    return stop_reason, stage, detail


@router.post("/sessions/{session_id}/stop")
async def stop(session_id: str, request: Request):
    visitor = owner(request)
    cfg = _matching_origin_cfg(request)
    if not visitor or not cfg:
        return error("access_denied", 403)
    try:
        raw_body = await request.json()
    except Exception:
        raw_body = {}
    stop_reason, stop_stage, stop_detail = _sanitize_client_stop_meta(raw_body)
    if re.fullmatch(r"[0-9a-f]{32}", session_id):
        row = await run_in_threadpool(budget.request_stop, session_id, visitor, reason=stop_reason)
        if row and (stop_reason != "stopped" or stop_detail):
            logger.warning(
                "Realtime stop session=%s provider=%s model=%s reason=%s stage=%s detail=%s",
                row.id,
                row.provider_key,
                row.model_id or "",
                stop_reason,
                stop_stage or "-",
                stop_detail or "-",
            )
        if row and row.state == "claimed":
            if row.provider_key == "xmax":
                x_cfg = xmax_settings()
                if x_cfg and x_cfg.api_key:
                    task = _ACTIVE_WATCHDOGS.pop(row.id, None)
                    if task and not task.done():
                        task.cancel()
                    with suppress(asyncio.TimeoutError, Exception):
                        await asyncio.wait_for(
                            _settle_and_close_xmax_session(row.id, x_cfg, "", reason=stop_reason),
                            timeout=4.0,
                        )
            elif row.provider_key == "reactor":
                r_cfg = reactor_settings()
                if r_cfg and r_cfg.api_key:
                    task = _ACTIVE_WATCHDOGS.pop(row.id, None)
                    if task and not task.done():
                        task.cancel()
                    with suppress(asyncio.TimeoutError, Exception):
                        await asyncio.wait_for(
                            _settle_and_close_reactor_session(row.id, r_cfg, reason=stop_reason),
                            timeout=4.0,
                        )
    return response({"ok": True})


async def open_provider(api_key, seconds, safari_codec):
    constraints = {"realtime": {"maxSessionDuration": seconds}}
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        result = await client.post(
            "https://api.decart.ai/v1/client/tokens", headers={"X-API-KEY": api_key},
            json={"expiresIn": 15, "allowedModels": [budget.MODEL], "constraints": constraints},
        )
        result.raise_for_status()
        token = result.json()
    returned_limit = ((token.get("constraints") or {}).get("realtime") or {}).get("maxSessionDuration")
    if not isinstance(token.get("apiKey"), str) or not token["apiKey"] or returned_limit != seconds:
        raise ValueError("Decart did not confirm the session limit")
    params = {
        "model": budget.MODEL, "resolution": "720p",
        "api_key": token["apiKey"], "user_agent": PROVIDER_USER_AGENT,
    }
    if safari_codec == "vp8":
        params["livekit_server_codec"] = safari_codec
    return await connect(
        "wss://api.decart.ai/v1/stream?" + urlencode(params), open_timeout=budget.SETUP_SECONDS,
        close_timeout=2, max_size=MAX_SIGNAL_BYTES, max_queue=4, compression=None,
    )


def browser_signal(raw, joined):
    if not raw or len(raw.encode("utf-8")) > MAX_SIGNAL_BYTES:
        raise ValueError("Invalid signaling size")
    message = json.loads(raw)
    if not isinstance(message, dict):
        raise ValueError("Invalid signal")
    kind = message.get("type")
    if kind == "livekit_join" and not joined:
        signal = {"type": kind, "passthrough": False}
        caps = message.get("client_capabilities")
        if isinstance(caps, dict) and caps.get("frame_timing") is True:
            signal["client_capabilities"] = {"frame_timing": True}
        return signal
    if kind == "set_image" and joined:
        image, prompt = message.get("image_data"), message.get("prompt")
        if isinstance(image, str) and isinstance(prompt, str) and 0 < len(prompt) <= 350:
            data = base64.b64decode(image, validate=True)
            if 0 < len(data) <= MAX_IMAGE_BYTES and data.startswith(b"\xff\xd8\xff"):
                return {"type": kind, "image_data": image, "prompt": prompt, "enhance_prompt": False}
    raise ValueError("Unsupported browser signal")


@router.websocket("/v1/stream")
async def stream(websocket: WebSocket):
    cfg = settings()
    visitor = owner(websocket)
    ticket = websocket.query_params.get("ticket", "")
    reject_reason = ""
    if not cfg or not cfg.available:
        reject_reason = "unavailable"
    elif not visitor:
        reject_reason = "missing_visitor"
    elif not same_origin(websocket, cfg):
        reject_reason = "origin_mismatch"
    elif not re.fullmatch(r"[0-9a-f]{32}", ticket):
        reject_reason = "invalid_ticket"
    elif websocket.query_params.get("model") != budget.MODEL:
        reject_reason = "invalid_model"
    elif "speed" in websocket.query_params:
        reject_reason = "speed_not_allowed"
    elif websocket.query_params.get("resolution", "720p") != "720p":
        reject_reason = "invalid_resolution"
    if reject_reason:
        logger.warning("Decart websocket handshake rejected (%s)", reject_reason)
        await websocket.close(code=1008)
        return
    try:
        row = await run_in_threadpool(budget.claim, ticket, visitor)
    except Exception as exc:
        logger.warning("Decart claim failed (%s)", type(exc).__name__)
        await websocket.close(code=1011)
        return
    if not row:
        await websocket.close(code=1008)
        return

    upstream = None
    joined = False
    reason = "connection_error"
    provider_id = None
    provider_seconds = None
    last_tick = 0
    relay_tasks = []

    async def send_to_provider():
        nonlocal joined
        edits = 0
        while True:
            incoming = await websocket.receive()
            if incoming["type"] == "websocket.disconnect":
                return "disconnect"
            try:
                signal = browser_signal(incoming.get("text"), joined)
            except (ValueError, RecursionError):
                return "invalid_signal"
            if signal["type"] == "livekit_join":
                joined = True
            else:
                edits += 1
                if edits > 20:
                    return "invalid_signal"
            await upstream.send(json.dumps(signal))

    async def receive_from_provider():
        nonlocal provider_id, provider_seconds, last_tick
        async for raw in upstream:
            if not isinstance(raw, str):
                continue
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if not isinstance(kind, str):
                continue
            if kind in {"session_id", "livekit_room_info"}:
                value = event.get("session_id")
                if isinstance(value, str) and 0 < len(value) <= 128:
                    provider_id = value
            if kind in {"generation_tick", "generation_ended"}:
                value = event.get("seconds")
                valid = type(value) in {int, float} and last_tick <= value <= 86400
                if valid:
                    last_tick = value
                if kind == "generation_ended":
                    provider_seconds = value if valid else None
                    end_reason = event.get("reason")
                    if not isinstance(end_reason, str) or end_reason not in PROVIDER_REASONS:
                        end_reason = "provider_ended"
                    await websocket.send_json({"type": kind, "seconds": provider_seconds, "reason": end_reason})
                    return end_reason
                if not valid:
                    continue
            if kind in {"livekit_room_info", "queue_position", "set_image_ack", "generation_started", "generation_tick", "error"}:
                await websocket.send_text(raw)
        return "disconnect"

    async def wait_for_stop():
        while not await run_in_threadpool(budget.stop_requested, row.id):
            await asyncio.sleep(0.75)
        return "stopped"

    try:
        await websocket.accept()
        remaining = row.hold_until - row.limit_seconds - budget.CLOSE_SECONDS - time.time()
        if remaining <= 0 or await run_in_threadpool(budget.stop_requested, row.id):
            reason = "stopped"
            return
        upstream = await asyncio.wait_for(open_provider(
            cfg.api_key, row.limit_seconds, websocket.query_params.get("livekit_server_codec"),
        ), timeout=remaining)
        if await run_in_threadpool(budget.stop_requested, row.id):
            reason = "stopped"
            return
        provider_task = asyncio.create_task(receive_from_provider())
        relay_tasks = [provider_task, asyncio.create_task(send_to_provider()), asyncio.create_task(wait_for_stop())]
        timeout = min(row.limit_seconds + 1, row.hold_until - time.time() - 2)
        done, _ = await asyncio.wait(relay_tasks, timeout=max(0, timeout), return_when=asyncio.FIRST_COMPLETED)
        reason = next((task.result() for task in relay_tasks if task in done), "timeout")
    except (ConnectionClosed, WebSocketDisconnect):
        reason = "disconnect"
    except asyncio.TimeoutError:
        reason = "connection_timeout"
    except Exception as exc:
        logger.warning("Decart signaling failed (%s)", type(exc).__name__)
    finally:
        for task in relay_tasks:
            task.cancel()
        if relay_tasks:
            await asyncio.gather(*relay_tasks, return_exceptions=True)
        if upstream is not None:
            with suppress(ConnectionClosed, OSError):
                await upstream.close()
        try:
            await run_in_threadpool(budget.finalize, row, reason=reason, provider_session_id=provider_id,
                                    provider_seconds=provider_seconds, join_sent=joined)
        except Exception as exc:
            logger.warning("Decart settlement failed for %s (%s)", row.id, type(exc).__name__)
        with suppress(RuntimeError, OSError, WebSocketDisconnect):
            await websocket.close(code=1000 if reason in {"stopped", "disconnect", "timeout"} else 1008)

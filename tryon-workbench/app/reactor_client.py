"""Official Reactor (reactor.inc) relay API helpers for Xmax X2.1 & Xmax X2.0."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote, urlsplit

import httpx

REACTOR_DEFAULT_BASE_URL = "https://api.reactor.inc"
REACTOR_DEFAULT_MODEL = "reactor/xmax-x2-1"
REACTOR_MODELS: tuple[str, ...] = ("reactor/xmax-x2-1", "xmax/x2")
REACTOR_MODEL_ALIASES: dict[str, str] = {
    "reactor/xmax-x2-1": "reactor/xmax-x2-1",
    "xmax-x2-1": "reactor/xmax-x2-1",
    "x2.1": "reactor/xmax-x2-1",
    "x21": "reactor/xmax-x2-1",
    "xmax/x2": "xmax/x2",
    "x2": "xmax/x2",
    "x2.0": "xmax/x2",
    "x20": "xmax/x2",
}
REACTOR_DEFAULT_CREDITS_PER_SECOND = 17
REACTOR_DEFAULT_CENTS_PER_MINUTE = 11  # Conservative ceiling for $0.102/min ($0.0017/sec).


class ReactorApiError(RuntimeError):
    """Normalized Reactor REST API failure without leaking credentials."""

    def __init__(self, message: str, *, http_status: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.error_code = error_code


def normalize_model(model: str | None, *, default: str = REACTOR_DEFAULT_MODEL) -> str:
    candidate = str(model or "").strip().lower()
    if candidate in REACTOR_MODEL_ALIASES:
        return REACTOR_MODEL_ALIASES[candidate]
    fallback = str(default or REACTOR_DEFAULT_MODEL).strip().lower()
    return REACTOR_MODEL_ALIASES.get(fallback, REACTOR_DEFAULT_MODEL)


def resolve_base_url(custom_base_url: str = "") -> str:
    raw = str(custom_base_url or "").strip().rstrip("/")
    if not raw:
        return REACTOR_DEFAULT_BASE_URL
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid Reactor API base URL")
    return raw


def _headers(api_key: str) -> dict[str, str]:
    clean_key = str(api_key or "").strip()
    if not clean_key:
        raise ReactorApiError("Missing Reactor API key")
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {clean_key}",
        "Reactor-API-Version": "1",
        "Reactor-API-Accept-Version": "1",
    }


def _parse_response_json(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except Exception as exc:
        if 200 <= resp.status_code < 300:
            return {}
        raise ReactorApiError(
            f"Reactor returned non-JSON error response (HTTP {resp.status_code})",
            http_status=resp.status_code,
        ) from exc

    if not isinstance(payload, dict):
        if 200 <= resp.status_code < 300:
            return {"items": payload}
        raise ReactorApiError(
            f"Reactor returned invalid payload (HTTP {resp.status_code})",
            http_status=resp.status_code,
        )

    if not (200 <= resp.status_code < 300):
        err_obj = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        err_code = str(
            err_obj.get("code")
            or payload.get("code")
            or (payload.get("error") if isinstance(payload.get("error"), str) else "")
            or ""
        ).strip() or None
        msg = str(
            err_obj.get("message")
            or payload.get("message")
            or payload.get("detail")
            or ""
        ).strip() or f"Reactor API error (HTTP {resp.status_code})"
        raise ReactorApiError(msg, http_status=resp.status_code, error_code=err_code)

    return payload


async def _request(
    method: str,
    path: str,
    api_key: str,
    *,
    base_url: str,
    json_body: dict | None = None,
    params: dict | None = None,
    timeout: float = 10.0,
) -> dict:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        resp = await client.request(
            method,
            url,
            headers=_headers(api_key),
            json=json_body,
            params=params,
        )
    return _parse_response_json(resp)


def extract_account_id(me_payload: dict) -> str:
    if not isinstance(me_payload, dict):
        return ""
    for key in ("account_id", "default_account_id", "active_account_id"):
        val = me_payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    account_obj = me_payload.get("account")
    if isinstance(account_obj, dict):
        aid = account_obj.get("id") or account_obj.get("account_id")
        if isinstance(aid, str) and aid.strip():
            return aid.strip()
    accounts = me_payload.get("accounts")
    if isinstance(accounts, list) and accounts:
        first = accounts[0]
        if isinstance(first, dict):
            aid = first.get("id") or first.get("account_id")
            if isinstance(aid, str) and aid.strip():
                return aid.strip()
        elif isinstance(first, str) and first.strip():
            return first.strip()
    return ""


def _parse_timestamp_value(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        num = float(value)
        return num / 1000.0 if num > 10_000_000_000 else num
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw).timestamp()
        except Exception:
            return None
    return None


def extract_session_billed_seconds(session_payload: dict) -> tuple[float | None, bool]:
    if not isinstance(session_payload, dict):
        return None, False

    raw_state = str(session_payload.get("state") or session_payload.get("status") or "").strip().upper()
    is_terminal = raw_state in {"CLOSED", "ENDED", "TERMINATED", "FAILED", "COMPLETED", "EXPIRED"}
    if session_payload.get("ended_at"):
        is_terminal = True

    for key in ("billed_seconds", "duration_seconds", "active_seconds", "runtime_seconds", "seconds"):
        val = session_payload.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0:
            return float(val), is_terminal

    end_ts = _parse_timestamp_value(session_payload.get("ended_at") or session_payload.get("closed_at"))
    start_ts = _parse_timestamp_value(
        session_payload.get("ready_at")
        or session_payload.get("started_at")
        or session_payload.get("active_at")
    )
    if end_ts is not None and start_ts is not None and end_ts >= start_ts:
        return round(end_ts - start_ts, 3), True

    return None, is_terminal


async def get_me(api_key: str, *, base_url: str, timeout: float = 10.0) -> dict:
    return await _request("GET", "/me", api_key, base_url=base_url, timeout=timeout)


async def get_account_credits(api_key: str, account_id: str, *, base_url: str, timeout: float = 10.0) -> dict:
    clean_id = str(account_id or "").strip()
    if not clean_id:
        raise ReactorApiError("Missing Reactor account_id")
    data = await _request(
        "GET",
        f"/accounts/{quote(clean_id, safe='')}/credits",
        api_key,
        base_url=base_url,
        timeout=timeout,
    )
    raw_balance = data.get("balance")
    if raw_balance is None and isinstance(data.get("credits"), (int, float)):
        raw_balance = data.get("credits")
    if not isinstance(raw_balance, (int, float)) or isinstance(raw_balance, bool):
        raw_balance = 0.0
    balance = max(0.0, float(raw_balance))

    raw_usd = data.get("balance_usd")
    balance_usd = (
        round(float(raw_usd), 4)
        if isinstance(raw_usd, (int, float)) and not isinstance(raw_usd, bool)
        else round(balance / 10000.0, 4)
    )
    return {
        "balance": balance,
        "balance_usd": balance_usd,
        "currency_code": str(data.get("currency_code") or "USD"),
        "raw": data,
    }


async def get_account_quotas(api_key: str, account_id: str, *, base_url: str, timeout: float = 10.0) -> dict:
    clean_id = str(account_id or "").strip()
    if not clean_id:
        raise ReactorApiError("Missing Reactor account_id")
    return await _request(
        "GET",
        f"/accounts/{quote(clean_id, safe='')}/quotas",
        api_key,
        base_url=base_url,
        timeout=timeout,
    )


async def get_balance(api_key: str, *, base_url: str, timeout: float = 10.0) -> dict:
    me = await get_me(api_key, base_url=base_url, timeout=timeout)
    account_id = extract_account_id(me)
    if not account_id:
        raise ReactorApiError("Reactor /me response missing account_id")
    credits_info = await get_account_credits(api_key, account_id, base_url=base_url, timeout=timeout)
    return {
        "account_id": account_id,
        "balance": credits_info["balance"],
        "balance_usd": credits_info["balance_usd"],
        "currency_code": credits_info["currency_code"],
    }


async def create_scoped_jwt(
    api_key: str,
    *,
    base_url: str,
    model_name: str,
    max_session_duration_seconds: int,
    expire_seconds: int,
    max_sessions: int = 1,
    timeout: float = 10.0,
) -> dict:
    clean_model = normalize_model(model_name)
    ttl = max(60, min(21600, int(expire_seconds)))
    duration_cap = max(1, min(86400, int(max_session_duration_seconds)))
    sessions_cap = max(1, min(500, int(max_sessions)))

    body = {
        "expires_after": ttl,
        "authorization_details": [
            {
                "type": "session",
                "resources": {
                    "models": {"match": [clean_model]},
                },
                "constraints": {
                    "max_sessions": sessions_cap,
                    "max_session_duration_seconds": duration_cap,
                },
            }
        ],
    }
    data = await _request("POST", "/tokens", api_key, base_url=base_url, json_body=body, timeout=timeout)
    token = str(data.get("jwt") or "").strip()
    if not token:
        raise ReactorApiError("Reactor did not return scoped jwt")
    return data


async def close_session(
    api_key: str,
    session_id: str,
    *,
    base_url: str,
    reason: str = "user_stopped",
    timeout: float = 10.0,
) -> None:
    clean_sid = str(session_id or "").strip()
    if not clean_sid:
        return
    url = base_url.rstrip("/") + f"/sessions/{quote(clean_sid, safe='')}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        resp = await client.request(
            "DELETE",
            url,
            headers=_headers(api_key),
            json={"reason": str(reason or "user_stopped")[:200]},
        )
    if resp.status_code in (404, 410):
        return
    _parse_response_json(resp)


async def get_session_usage(
    api_key: str,
    session_id: str,
    *,
    base_url: str,
    account_id: str = "",
    timeout: float = 10.0,
) -> dict | None:
    clean_sid = str(session_id or "").strip()
    if not clean_sid:
        return None
    url = base_url.rstrip("/") + f"/sessions/{quote(clean_sid, safe='')}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        resp = await client.get(url, headers=_headers(api_key))
    if 200 <= resp.status_code < 300:
        return _parse_response_json(resp)
    if resp.status_code not in (404, 405):
        _parse_response_json(resp)

    resolved_account = str(account_id or "").strip()
    if not resolved_account:
        me = await get_me(api_key, base_url=base_url, timeout=timeout)
        resolved_account = extract_account_id(me)
    if not resolved_account:
        return None

    listing = await _request(
        "GET",
        f"/accounts/{quote(resolved_account, safe='')}/sessions",
        api_key,
        base_url=base_url,
        params={"status": "all", "limit": 50},
        timeout=timeout,
    )
    items = listing.get("items") or listing.get("sessions") or []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or item.get("session_id") or "").strip()
            if item_id == clean_sid:
                return item
    return None


async def get_pricing(*, base_url: str = REACTOR_DEFAULT_BASE_URL, timeout: float = 10.0) -> dict:
    url = resolve_base_url(base_url).rstrip("/") + "/pricing"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        resp = await client.get(url, headers={"Accept": "application/json"})
    return _parse_response_json(resp)

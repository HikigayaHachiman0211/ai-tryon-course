"""Official Xmax X2.1 realtime REST API helpers."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

import httpx

XMAX_DEFAULT_URLS: dict[str, str] = {
    "global": "https://api.xmax.ai/open/api/v1",
    "china": "https://cloud.xmax.22duck.cn/open/api/v1",
}
XMAX_MODELS: tuple[str, ...] = ("x2.1", "x2.1-flash")
XMAX_ENV_MODELS: dict[str, tuple[str, ...]] = {
    "global": ("x2.1",),
    "china": ("x2.1", "x2.1-flash"),
}
XMAX_CAMERA_PRESETS: dict[str, tuple[str, ...]] = {
    "x2.1": ("1080x1920", "1920x1080", "1152x1536", "1536x1152", "1408x1408"),
    "x2.1-flash": ("704x1280", "1280x704", "768x1024", "1024x768", "960x960"),
}


class XmaxApiError(RuntimeError):
    """Normalized Xmax REST API failure without leaking credentials."""

    def __init__(self, message: str, *, api_code: int | None = None, http_status: int | None = None):
        super().__init__(message)
        self.api_code = api_code
        self.http_status = http_status


def normalize_environment(environment: str | None) -> str:
    env = str(environment or "").strip().lower()
    return "china" if env == "china" else "global"


def supported_models_for_environment(environment: str | None) -> tuple[str, ...]:
    return XMAX_ENV_MODELS[normalize_environment(environment)]


def normalize_model(
    model: str | None,
    *,
    default: str = "x2.1",
    environment: str | None = None,
) -> str:
    allowed = supported_models_for_environment(environment) if environment is not None else XMAX_MODELS
    candidate = str(model or "").strip().lower()
    if candidate in allowed:
        return candidate
    return default if default in allowed else allowed[0]


def normalize_camera_preset(model: str, preset: str | None) -> str:
    allowed = XMAX_CAMERA_PRESETS.get(normalize_model(model), XMAX_CAMERA_PRESETS["x2.1"])
    clean = str(preset or "").strip()
    if clean in allowed:
        return clean
    return allowed[0]


def resolve_base_url(environment: str | None = "global", custom_base_url: str = "") -> str:
    raw = str(custom_base_url or "").strip().rstrip("/")
    if not raw:
        return XMAX_DEFAULT_URLS[normalize_environment(environment)]
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid Xmax API base URL")
    return raw


def _headers(api_key: str) -> dict[str, str]:
    clean_key = str(api_key or "").strip()
    if not clean_key:
        raise XmaxApiError("Missing Xmax API key")
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": clean_key,
    }


def _parse_envelope(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except Exception as exc:
        raise XmaxApiError(
            f"Xmax returned non-JSON response (HTTP {resp.status_code})",
            http_status=resp.status_code,
        ) from exc

    if not isinstance(payload, dict):
        raise XmaxApiError(
            f"Xmax returned invalid payload (HTTP {resp.status_code})",
            http_status=resp.status_code,
        )

    success_flag = payload.get("success")
    api_code = payload.get("code")
    ok = (200 <= resp.status_code < 300) and (
        success_flag is True or (success_flag is None and api_code == 200)
    )
    if not ok:
        msg = str(payload.get("message") or "").strip() or f"Xmax API error (code={api_code})"
        raise XmaxApiError(
            msg,
            api_code=int(api_code) if isinstance(api_code, int) else None,
            http_status=resp.status_code,
        )

    data = payload.get("data")
    if data is None:
        raise XmaxApiError(
            "Xmax response missing data",
            api_code=int(api_code) if isinstance(api_code, int) else None,
            http_status=resp.status_code,
        )
    return data if isinstance(data, dict) else {"value": data}


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
    return _parse_envelope(resp)


async def get_balance(api_key: str, *, base_url: str, timeout: float = 10.0) -> float:
    data = await _request("GET", "/balance", api_key, base_url=base_url, timeout=timeout)
    balance = data.get("currentBalance")
    if not isinstance(balance, (int, float)) or isinstance(balance, bool) or balance < 0:
        raise XmaxApiError("Xmax returned invalid currentBalance")
    return float(balance)


async def create_temporary_api_key(
    api_key: str,
    *,
    base_url: str,
    expire_seconds: int,
    points_limit: int,
    session_limit: int = 1,
    timeout: float = 10.0,
) -> dict:
    body = {
        "expireSeconds": max(10, int(expire_seconds)),
        "pointsLimit": max(0, int(points_limit)),
        "temporaryApiKeySessionLimit": max(1, int(session_limit)),
    }
    data = await _request(
        "POST",
        "/temporary-api-key",
        api_key,
        base_url=base_url,
        json_body=body,
        timeout=timeout,
    )
    temp_key = str(data.get("temporaryApiKey") or "").strip()
    if not temp_key:
        raise XmaxApiError("Xmax did not return temporaryApiKey")
    return data


async def get_temporary_api_key_status(
    api_key: str,
    temp_key: str,
    *,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    return await _request(
        "GET",
        f"/temporary-api-key/{quote(temp_key, safe='')}/status",
        api_key,
        base_url=base_url,
        timeout=timeout,
    )


async def deactivate_temporary_api_key(
    api_key: str,
    temp_key: str,
    *,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    return await _request(
        "PUT",
        f"/temporary-api-key/{quote(temp_key, safe='')}/inactive",
        api_key,
        base_url=base_url,
        timeout=timeout,
    )


async def get_session_status(
    api_key: str,
    session_uid: str,
    *,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    return await _request(
        "GET",
        f"/session/{quote(session_uid, safe='')}/status",
        api_key,
        base_url=base_url,
        timeout=timeout,
    )


async def close_session(
    api_key: str,
    session_uid: str,
    *,
    base_url: str,
    timeout: float = 10.0,
) -> None:
    clean_uid = str(session_uid or "").strip()
    if not clean_uid:
        return
    url = base_url.rstrip("/") + f"/session/{quote(clean_uid, safe='')}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        resp = await client.delete(url, headers=_headers(api_key))
    if resp.status_code >= 400 and resp.status_code != 404:
        try:
            _parse_envelope(resp)
        except XmaxApiError as exc:
            if exc.api_code == 46012:
                return
            raise

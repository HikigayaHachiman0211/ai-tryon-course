"""01Router's native catalog / quote / asynchronous generation protocol."""
from __future__ import annotations

import copy
import ipaddress
import math
import socket
import time
from urllib.parse import urlsplit, urljoin

import httpx
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

_catalogs = {}


class VideoError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def public_media_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return False
        if host.lower() == "localhost" or host.lower().endswith((".local", ".localhost", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host and not host.isdigit()
    except ValueError:
        return False


def validate_input(params: list, values: dict) -> dict:
    if not isinstance(values, dict) or len(values) > 80:
        raise VideoError(400, "invalid_input", "Invalid video input")
    known = {p["name"] for p in params}
    unknown = set(values) - known
    if unknown:
        raise VideoError(400, "invalid_input", "Unsupported parameters: " + ", ".join(sorted(unknown)))
    result = {}
    for spec in params:
        name, kind = spec["name"], spec.get("type", "string")
        value = values.get(name)
        if value is None or value == "":
            value = spec.get("default")
        if value is None or value == "" or value == []:
            if spec.get("required"):
                raise VideoError(400, "invalid_input", f"{name}: required")
            continue
        invalid = False
        if kind in {"integer", "number"}:
            invalid = isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            if not invalid:
                invalid = (kind == "integer" and int(value) != value) or ("min" in spec and value < spec["min"]) or ("max" in spec and value > spec["max"])
        elif kind == "boolean":
            invalid = not isinstance(value, bool)
        elif kind in {"images", "videos", "audios"}:
            invalid = not isinstance(value, list) or len(value) > spec.get("maxItems", 30) or any(not isinstance(v, str) or len(v) > 8192 or not public_media_url(v) for v in value)
        elif kind != "enum":
            invalid = not isinstance(value, str) or len(value.encode("utf-16-le")) // 2 > min(spec.get("maxLength", 10000), 10000)
            if not invalid and kind in {"image", "video", "audio"}:
                invalid = not public_media_url(value)
        if spec.get("options") and not any(type(value) is type(option) and value == option for option in spec["options"]):
            invalid = True
        if invalid:
            raise VideoError(400, "invalid_input", f"{name}: invalid value or out of range")
        result[name] = value
    return result


def parameters_for(model: dict, provider: str = "") -> list:
    if provider and model.get("providers"):
        selected = next((p for p in model["providers"] if p.get("provider") == provider), None)
        if selected is None:
            raise VideoError(400, "invalid_provider", "Provider not available for this model")
        return selected.get("params", model.get("params", []))
    if provider and model.get("provider") != provider:
        raise VideoError(400, "invalid_provider", "Project provider is pinned")
    return model.get("params", [])


async def gateway_request(method: str, path: str, cfg: dict, *, body=None, params=None, protected=False):
    headers = {"Accept": "application/json"}
    if protected:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    try:
        async with httpx.AsyncClient(timeout=min(max(cfg.get("timeout_seconds", 60), 10), 120), follow_redirects=False) as client:
            response = await client.request(method, cfg["base_url"] + path, headers=headers, json=body, params=params)
    except httpx.RequestError as exc:
        ambiguous = method == "POST" and path == "/generations"
        raise VideoError(504 if ambiguous else 502, "submission_unknown" if ambiguous else "gateway_unavailable",
                         "Submission outcome unknown; do not resubmit automatically" if ambiguous else "01Router is temporarily unreachable") from exc
    try:
        data = response.json()
    except ValueError:
        code = "submission_unknown" if method == "POST" and path == "/generations" else "invalid_response"
        raise VideoError(502, code, "01Router returned an invalid response")
    if response.status_code >= 300:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        message = error.get("message", "01Router request failed") if isinstance(error, dict) else str(error)
        code = str(error.get("code", "gateway_error")) if isinstance(error, dict) else "gateway_error"
        if method == "POST" and path == "/generations" and response.status_code >= 500:
            code = "submission_unknown"
        # Never include request URLs, headers, credentials, or arbitrary response bodies.
        message = str(message).replace(cfg.get("api_key") or "\x00", "[redacted]")[:500]
        raise VideoError(response.status_code if response.status_code < 500 else 502, code, message)
    if not isinstance(data, dict):
        raise VideoError(502, "invalid_response", "01Router returned an invalid response")
    return data


def clear_catalog_cache():
    _catalogs.clear()


async def catalog(cfg: dict, refresh=False):
    key = (cfg["base_url"], cfg.get("project_id", ""))
    cached = _catalogs.get(key)
    if cached and not refresh and time.monotonic() - cached[0] < 60:
        return copy.deepcopy(cached[1])
    params = {"type": "video"}
    if cfg.get("project_id"):
        params["project"] = cfg["project_id"]
    data = await gateway_request("GET", "/models", cfg, params=params)
    if not isinstance(data.get("data"), list):
        raise VideoError(502, "invalid_response", "01Router returned an invalid catalog")
    models = [m for m in data["data"] if isinstance(m, dict) and m.get("type") == "video" and m.get("slug")]
    _catalogs[key] = (time.monotonic(), models)
    return copy.deepcopy(models)


async def prepare_request(cfg: dict, model_slug: str, provider: str, values: dict, resolve_image):
    model = next((m for m in await catalog(cfg) if m["slug"] == model_slug), None)
    if model is None:
        raise VideoError(400, "invalid_model", "Choose a video model from the current catalog")
    specs = parameters_for(model, provider)
    converted = dict(values)
    for spec in specs:
        value = converted.get(spec["name"])
        if value and spec.get("type") == "image":
            if not isinstance(value, str):
                raise VideoError(400, "invalid_input", f"{spec['name']}: expected image URL")
            converted[spec["name"]] = resolve_image(value)
        elif value and spec.get("type") == "images":
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                raise VideoError(400, "invalid_input", f"{spec['name']}: expected image URLs")
            converted[spec["name"]] = [resolve_image(v) for v in value]
    body = {"model": model_slug, "input": validate_input(specs, converted)}
    if provider:
        body["provider"] = provider
    if cfg.get("project_id"):
        body["project"] = cfg["project_id"]
    return body


def check_download_url(url):
    if not public_media_url(url):
        raise VideoError(400, "invalid_result", "Invalid video result URL")
    parsed = urlsplit(url)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise VideoError(502, "download_unavailable", "Video download host is unavailable") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise VideoError(400, "invalid_result", "Invalid video result host")


async def download_result(url, filename):
    """Stream an owned gateway result as an attachment, without buffering a full video."""
    client = httpx.AsyncClient(timeout=60, follow_redirects=False)
    response = None
    try:
        for _ in range(4):
            await run_in_threadpool(check_download_url, url)
            response = await client.send(client.build_request("GET", url), stream=True)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                await response.aclose()
                url = urljoin(url, location)
                continue
            break
        if response.status_code != 200:
            raise VideoError(502, "download_unavailable", "The video link is unavailable or expired")
        content_type = response.headers.get("content-type", "video/mp4").split(";")[0].lower()
        if not (content_type.startswith("video/") or content_type == "application/octet-stream"):
            raise VideoError(502, "invalid_result", "The result is not a video file")
        limit = 512 * 1024 * 1024
        if int(response.headers.get("content-length", "0")) > limit:
            raise VideoError(413, "download_too_large", "Video exceeds the 512 MB download limit")
    except Exception as exc:
        if response is not None:
            await response.aclose()
        await client.aclose()
        if isinstance(exc, VideoError):
            raise
        raise VideoError(502, "download_unavailable", "Could not download the video") from exc

    async def chunks():
        total = 0
        try:
            async for chunk in response.aiter_bytes(128 * 1024):
                total += len(chunk)
                if total > limit:
                    raise RuntimeError("Video download exceeded the size limit")
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(chunks(), media_type=content_type,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

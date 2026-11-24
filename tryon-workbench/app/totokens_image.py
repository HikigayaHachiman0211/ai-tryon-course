"""Image editing through the ToTokens relay without automatic paid retries."""

from __future__ import annotations

import base64
import binascii
import io
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from PIL import Image

MAX_IMAGE_BYTES = 24 * 1024 * 1024


def relay_root(base_url: str) -> str:
    """Accept either a relay origin or its conventional /v1 base URL."""
    parsed = urlsplit((base_url or "https://totokens.cc").strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        raise ValueError("中转站地址必须是有效的 HTTPS 地址，且不能包含凭据或查询参数")
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _read_image(path: str) -> tuple[bytes, str]:
    data = Path(path).read_bytes()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("输入图片为空或过大")
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt = image.format
            image.verify()
    except Exception as exc:
        raise ValueError("输入图片格式无效") from exc
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(fmt)
    if not mime:
        raise ValueError("中转站仅支持 JPEG、PNG 或 WebP 输入图片")
    return data, mime


def _decode_image(encoded: str) -> bytes:
    if not isinstance(encoded, str) or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 4:
        raise ValueError("中转站返回的图片数据无效或过大")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("中转站返回的图片数据无效") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("中转站返回的图片数据为空或过大")
    return data


def _as_png(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 64_000_000:
                raise ValueError("中转站返回的图片尺寸过大")
            image.load()
            output = io.BytesIO()
            if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"}:
                image = image.convert("RGB")
            image.save(output, format="PNG")
            return output.getvalue()
    except Exception as exc:
        raise ValueError("中转站未返回有效图片") from exc


def _is_gemini_model(model_key: str, model_id: str) -> bool:
    key = (model_key or "").strip().lower()
    mid = (model_id or "").strip().lower()
    if key in {"chatgpt", "gpt"} or "gpt" in mid or "chatgpt" in mid:
        return False
    if key == "flash" or mid.startswith("gemini"):
        return True
    return False


def _sanitize_error_detail(response: httpx.Response, api_key: str) -> str:
    try:
        body = response.json()
    except Exception:
        return ""
    if not isinstance(body, dict):
        return ""
    raw = body.get("error")
    detail = raw.get("message") if isinstance(raw, dict) else body.get("message") or ""
    text = str(detail or "").strip()
    if not text:
        return ""
    if api_key:
        text = text.replace(api_key, "***")
    return text[:180]


from app.tryon_options import (
    map_aspect_ratio_to_openai_size,
    map_image_size_to_openai_quality,
)


async def generate_image(
    *, base_url: str, api_key: str, model_id: str, model_key: str,
    prompt: str, model_path: str, garment_path: str, timeout_seconds: int,
    fetch_remote_image: Callable[[str], Awaitable[tuple[bytes, str]]],
    generation_options: Optional[dict[str, Any]] = None,
) -> bytes:
    """Send one edit request with both references and return a PNG image."""
    root = relay_root(base_url)
    model_image, model_mime = _read_image(model_path)
    garment_image, garment_mime = _read_image(garment_path)
    headers = {"Authorization": f"Bearer {api_key}"}
    use_gemini = _is_gemini_model(model_key, model_id)
    normalized_key = (model_key or "").strip().lower()
    opts = dict(generation_options or {})

    try:
        async with httpx.AsyncClient(timeout=max(10, min(int(timeout_seconds or 120), 300)), follow_redirects=False) as client:
            if use_gemini:
                endpoint = f"{root}/v1beta/models/{quote(model_id, safe='._-')}:generateContent"
                generation_config: dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"]}
                if opts.get("temperature") is not None:
                    generation_config["temperature"] = float(opts["temperature"])
                if opts.get("seed") is not None:
                    generation_config["seed"] = int(opts["seed"])
                image_config: dict[str, Any] = {}
                if opts.get("aspect_ratio") and str(opts["aspect_ratio"]).lower() != "auto":
                    image_config["aspectRatio"] = str(opts["aspect_ratio"])
                if opts.get("image_size") and str(opts["image_size"]).lower() != "auto":
                    image_config["imageSize"] = str(opts["image_size"]).upper()
                if image_config:
                    generation_config["imageConfig"] = image_config
                body = {
                    "contents": [{"role": "user", "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": model_mime, "data": base64.b64encode(model_image).decode("ascii")}},
                        {"inlineData": {"mimeType": garment_mime, "data": base64.b64encode(garment_image).decode("ascii")}},
                    ]}],
                    "generationConfig": generation_config,
                }
                response = await client.post(endpoint, headers=headers, json=body)
            elif normalized_key in {"pro", "chatgpt", "gpt"} or not use_gemini:
                endpoint = f"{root}/v1/images/edits"
                suffixes = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
                files = [
                    ("image[]", ("person" + suffixes[model_mime], model_image, model_mime)),
                    ("image[]", ("garment" + suffixes[garment_mime], garment_image, garment_mime)),
                ]
                form_data: dict[str, str] = {"model": model_id, "prompt": prompt, "n": "1"}
                openai_size = map_aspect_ratio_to_openai_size(
                    opts.get("aspect_ratio"),
                    image_size=opts.get("image_size"),
                )
                if openai_size:
                    form_data["size"] = openai_size
                openai_quality = str(
                    opts.get("quality") or map_image_size_to_openai_quality(opts.get("image_size")) or ""
                ).strip().lower()
                if openai_quality and openai_quality != "auto":
                    form_data["quality"] = openai_quality
                response = await client.post(endpoint, headers=headers, data=form_data, files=files)
            else:
                raise ValueError("不支持的中转站生图模型")
    except httpx.TimeoutException as exc:
        raise RuntimeError("中转站请求超时；请求可能仍在处理中，请确认后再重试") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("无法连接中转站，请检查地址和网络") from exc

    if not 200 <= response.status_code < 300:
        detail = _sanitize_error_detail(response, api_key)
        suffix = f" ({detail})" if detail else ""
        raise RuntimeError(f"中转站返回 HTTP {response.status_code}{suffix}，请检查密钥分组、模型权限和配额")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("中转站返回的响应格式无效") from exc

    encoded = None
    image_url = None
    if isinstance(payload, dict) and payload.get("candidates"):
        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if str(inline.get("mimeType") or inline.get("mime_type") or "").startswith("image/"):
                    encoded = inline.get("data")
                    if encoded:
                        break
            if encoded:
                break
    if isinstance(payload, dict) and not encoded and not image_url:
        for item in payload.get("data") or []:
            if isinstance(item, dict):
                encoded, image_url = item.get("b64_json"), item.get("url")
                if encoded or image_url:
                    break

    if encoded:
        data = _decode_image(encoded)
    elif image_url:
        if isinstance(image_url, str) and image_url.startswith("data:image/") and ";base64," in image_url:
            data = _decode_image(image_url.split(";base64,", 1)[1])
        else:
            data, _ = await fetch_remote_image(image_url)
    else:
        raise RuntimeError("中转站响应中没有生成的图片")
    return _as_png(data)

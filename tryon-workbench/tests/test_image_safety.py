"""Regression checks with synthetic media and mocked network responses only."""
import ast
import base64
import copy
import io
import json
import os
import pathlib
import re
import socket
import ipaddress
import tempfile
import zipfile
from types import SimpleNamespace
from urllib.parse import unquote, urljoin, urlparse

import PIL.Image
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from python_multipart.multipart import MultipartParser, parse_options_header


def load_functions(names, namespace):
    source = pathlib.Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node = copy.deepcopy(node)
            node.decorator_list = []
            body.append(node)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *body], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(source), "exec"), namespace)


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("test unexpectedly attempted real asynchronous I/O")


@pytest.fixture
def image_app(tmp_path):
    roots = {name: tmp_path / name for name in ("uploads", "assets", "history")}
    for root in roots.values():
        root.mkdir()
    namespace = dict(os=os, pathlib=pathlib, re=re, io=io, base64=base64, PIL=PIL,
                     socket=socket, ipaddress=ipaddress, urlparse=urlparse, unquote=unquote,
                     urljoin=urljoin, ASSET_DIR=str(roots["assets"]), UPLOAD_DIR=str(roots["uploads"]),
                     HISTORY_FILES_DIR=str(roots["history"]), INTAKE_MAX_IMAGE_BYTES=128,
                     UPLOADS_GCS_PREFIX="synthetic",
                     _SSRF_BLOCKED_NETWORKS=[], Response=Response, JSONResponse=JSONResponse,
                     resolve_locale=lambda _: "en", error_payload=lambda code, *_args, **_kw: {"error": code})
    load_functions({"_safe_media_path", "_extract_local_candidates", "_ensure_local_file",
                    "_check_url_safe_for_ssrf", "_fetch_remote_image_bytes", "download_single",
                    "_save_upload_file", "_save_upload_bytes", "_validate_and_resolve_image_suffix"}, namespace)
    return namespace, roots


def test_local_media_paths_stay_in_roots(image_app, tmp_path, monkeypatch):
    app, roots = image_app
    (tmp_path / "secret.png").write_bytes(b"outside" * 30)
    (roots["assets"] / "ok.png").write_bytes(b"image" * 30)
    assert immediate(app["download_single"]("/assets/ok.png", None)).body == b"image" * 30
    assert immediate(app["download_single"]("secret.png", None)).status_code == 404
    assert app["_extract_local_candidates"]("https://public/assets/ok.png") == []
    for value in ("../secret.png", "..\\secret.png", "/secret.png", "C:\\secret.png",
                  "/assets/%2e%2e%2fsecret.png", "/assets/%252e%252e%255csecret.png"):
        assert app["_extract_local_candidates"](value) == []
    for value in ("../secret.png", "..\\secret.png", "/secret.png", "C:\\secret.png", "%2e%2e%2fsecret.png"):
        with pytest.raises(ValueError):
            immediate(app["_ensure_local_file"](value, None))
    try:
        (roots["assets"] / "link.png").symlink_to(tmp_path / "secret.png")
    except OSError:
        pass
    else:
        assert not app["_extract_local_candidates"]("/assets/link.png")
    realpath = os.path.realpath
    monkeypatch.setattr(os.path, "realpath", lambda value: str(tmp_path / "secret.png") if str(value).endswith("link.png") else realpath(value))
    assert not app["_extract_local_candidates"]("/assets/link.png")


class FakeResponse:
    def __init__(self, status, headers=None, chunks=()):
        self.status_code, self.headers, self.chunks = status, headers or {}, chunks
        self.content = b"".join(chunks)
        self.read_chunks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def aiter_bytes(self, **_kwargs):
        for chunk in self.chunks:
            self.read_chunks += 1
            yield chunk


def test_remote_fetch_validates_redirects_and_stops_oversize(image_app, monkeypatch):
    app, roots = image_app
    requested = []
    responses = {}

    class Client:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        def stream(self, _method, url):
            requested.append(url)
            return responses[url]
        async def get(self, url):
            requested.append(url)
            return responses[url]

    app["httpx"] = SimpleNamespace(AsyncClient=Client, HTTPError=Exception)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *_: [(socket.AF_INET, 0, 0, "", ("127.0.0.1" if host == "internal" else "8.8.8.8", 0))])
    responses["https://public/image"] = FakeResponse(302, {"location": "http://internal/private"})
    with pytest.raises(ValueError):
        immediate(app["_fetch_remote_image_bytes"]("https://public/image"))
    assert requested == ["https://public/image"]
    with pytest.raises(ValueError):
        immediate(app["_ensure_local_file"]("restore.png", "http://internal/private"))
    assert requested == ["https://public/image"]
    assert immediate(app["download_single"]("http://internal/private", None)).status_code == 502
    assert requested == ["https://public/image"]
    app.update(json=json, tempfile=tempfile, zipfile=zipfile, _build_download_stamp=lambda: "synthetic",
               _append_error_log=lambda *_args, **_kwargs: None, Form=lambda default: default)
    load_functions({"download_batch"}, app)
    assert immediate(app["download_batch"](None, json.dumps(["http://internal/private"]))).status_code == 400
    assert requested == ["https://public/image"]
    oversized = FakeResponse(200, {"content-type": "image/png", "content-length": "1"}, [b"a" * 80, b"b" * 80, b"c"])
    responses["https://public/image"] = oversized
    with pytest.raises(ValueError):
        immediate(app["_fetch_remote_image_bytes"]("https://public/image"))
    assert oversized.read_chunks == 2
    responses["https://public/image"] = FakeResponse(200, {"content-length": "129"}, [b"x"])
    with pytest.raises(ValueError):
        immediate(app["_fetch_remote_image_bytes"]("https://public/image"))
    assert responses["https://public/image"].read_chunks == 0
    responses["https://public/image"] = FakeResponse(200, {"content-type": "image/png"}, [b"valid"])
    assert immediate(app["_fetch_remote_image_bytes"]("https://public/image"))[0] == b"valid"
    image = io.BytesIO()
    PIL.Image.new("RGB", (2, 2)).save(image, "PNG")
    (roots["assets"] / "local.png").write_bytes(image.getvalue())
    count = len(requested)
    restored_local = immediate(app["_ensure_local_file"]("local-copy.png", "http://127.0.0.1/assets/local.png"))
    assert pathlib.Path(restored_local).read_bytes() == image.getvalue() and len(requested) == count
    responses["https://public/image"] = FakeResponse(200, {"content-type": "image/png"}, [image.getvalue()])
    restored = immediate(app["_ensure_local_file"]("restored.png", "https://public/image"))
    assert pathlib.Path(restored).read_bytes() == image.getvalue()


def test_manual_multipart_upload_stops_before_consuming_oversize_body(image_app):
    app, roots = image_app
    import uuid
    app.update(uuid=uuid, HTTPException=HTTPException, MultipartParser=MultipartParser,
               parse_options_header=parse_options_header, _upload_bytes_to_gcs=lambda *_: None,
               _content_type_from_ext=lambda _: "image/png")
    load_functions({"_upload_response", "_read_upload_request"}, app)

    class Request:
        headers = {"content-type": "multipart/form-data; boundary=synthetic"}
        def __init__(self, pieces): self.pieces, self.consumed = pieces, 0
        async def stream(self):
            for piece in self.pieces:
                self.consumed += 1
                yield piece

    prefix = b'--synthetic\r\nContent-Disposition: form-data; name="file"; filename="file.png"\r\nContent-Type: image/png\r\n\r\n'
    suffix = b'\r\n--synthetic--\r\n'
    output = io.BytesIO()
    PIL.Image.new("RGB", (2, 2)).save(output, "PNG")
    valid = Request([prefix, output.getvalue(), suffix])
    response = immediate(app["_upload_response"](valid))
    assert valid.consumed == 3
    assert (roots["uploads"] / response["filename"]).read_bytes() == output.getvalue()
    for content in (b"", b"not an image"):
        with pytest.raises(HTTPException):
            immediate(app["_upload_response"](Request([prefix, content, suffix])))
    oversized = Request([prefix, b"x" * 80, b"x" * 80, b"must not be consumed", suffix])
    with pytest.raises(HTTPException) as caught:
        immediate(app["_upload_response"](oversized))
    assert caught.value.status_code == 400
    assert oversized.consumed == 3
    assert len(list(roots["uploads"].iterdir())) == 1


def test_task_freedom_retains_zero_and_clamps_values(image_app):
    app, _ = image_app
    app.update(normalize_locale=lambda _: "zh-CN", task_message=lambda *_: "", DEFAULT_LOCALE="zh-CN")
    load_functions({"_normalize_freedom", "_task_public_payload", "_build_prompt"}, app)
    app.update(_read_base_prompt=lambda: "base", _normalize_garment_type=lambda _: {"instruction": ""})
    store_source = pathlib.Path(__file__).resolve().parents[1] / "app" / "store.py"
    store_tree = ast.parse(store_source.read_text(encoding="utf-8-sig"))
    store_function = next(node for node in store_tree.body if isinstance(node, ast.FunctionDef) and node.name == "task_public_payload")
    store_module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), store_function], type_ignores=[])
    ast.fix_missing_locations(store_module)
    store = {}
    exec(compile(store_module, str(store_source), "exec"), store)
    for value, expected in ((0, 0), (5, 5), (10, 10), (None, 5), (-1, 0), (11, 10)):
        assert app["_task_public_payload"]({"freedom": value})["freedom"] == expected
        assert store["task_public_payload"]({"freedom": value})["freedom"] == expected
        assert f"FREEDOM LEVEL: {expected}/10" in app["_build_prompt"](None, "append", expected)

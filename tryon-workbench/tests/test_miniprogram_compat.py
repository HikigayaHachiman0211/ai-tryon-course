import base64
import io
import os
from types import SimpleNamespace

import PIL.Image
from fastapi.testclient import TestClient


def _isolated_main(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if any(part in key.upper() for part in ("API_KEY", "SECRET", "CREDENTIAL", "GCS_BUCKET", "OSS_ACCESS")):
            monkeypatch.delenv(key, raising=False)
    for key in ("UPLOAD_DIR", "ASSET_DIR", "HISTORY_DIR"):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("ENABLE_ADMIN_REPORTING", "false")
    import main
    (tmp_path / "upload_dir").mkdir(exist_ok=True)
    monkeypatch.setattr(main, "UPLOAD_DIR", str(tmp_path / "upload_dir"))
    monkeypatch.setattr(main, "_upload_bytes_to_gcs", lambda *_: None)
    return main


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PIL.Image.new("RGB", (4, 4), color=(12, 34, 56)).save(buf, "PNG")
    return buf.getvalue()


def test_upload_and_intake_return_task_token_for_cookieless_clients(monkeypatch, tmp_path):
    main = _isolated_main(monkeypatch, tmp_path)
    client = TestClient(main.app)

    upload_res = client.post(
        "/upload/model",
        files={"file": ("model.png", _png_bytes(), "image/png")},
        headers={"X-Task-Token": "mp-token-12345"},
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert upload_data["task_token"] == "mp-token-12345"
    assert upload_data["url"].startswith("/uploads/")

    # Also test accessing the uploaded file via X-Task-Token without cookies
    client.cookies.clear()
    fetch_uploaded = client.get(
        f"/uploads/{upload_data['filename']}",
        headers={"X-Task-Token": "mp-token-12345"},
    )
    assert fetch_uploaded.status_code == 200

    b64_png = base64.b64encode(_png_bytes()).decode("ascii")
    intake_res = client.post(
        "/api/intake-image",
        json={
            "image_data_url": f"data:image/png;base64,{b64_png}",
            "role": "garment",
            "locale": "zh-CN",
        },
        headers={"X-Task-Token": "mp-token-12345"},
    )
    assert intake_res.status_code == 200
    intake_data = intake_res.json()
    assert intake_data["ok"] is True
    assert intake_data["task_token"] == "mp-token-12345"
    client.close()


def test_resolve_video_image_url_supports_mp_tryon_proxy_prefix(monkeypatch, tmp_path):
    main = _isolated_main(monkeypatch, tmp_path)
    monkeypatch.setenv("ROUTER01_MEDIA_BASE_URL", "https://demo.example.com/mp-tryon")

    media_meta = {
        "filename": "result_demo.png",
        "access_token_hash": main.hash_access_token("mp-token-12345"),
        "task_id": "task-1",
    }
    monkeypatch.setattr(main, "get_media_file", lambda fname: media_meta if fname == "result_demo.png" else None)

    fake_req = SimpleNamespace(
        base_url="https://demo.example.com/mp-tryon/",
        headers={"x-task-token": "mp-token-12345"},
        query_params={},
        cookies={},
    )
    resolved_prefixed = main._resolve_video_image_url(
        fake_req,
        "/mp-tryon/api/media/results/result_demo.png",
    )
    resolved_direct = main._resolve_video_image_url(
        fake_req,
        "/api/media/results/result_demo.png",
    )
    assert resolved_prefixed.startswith("https://demo.example.com/mp-tryon/api/media/results/result_demo.png?")
    assert resolved_direct.startswith("https://demo.example.com/mp-tryon/api/media/results/result_demo.png?")

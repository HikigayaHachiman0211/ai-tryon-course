import io
import os
from types import SimpleNamespace

import PIL.Image
from fastapi.testclient import TestClient


def isolated_main(monkeypatch, tmp_path):
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
    return main


def test_upload_api_accepts_images_and_rejects_invalid_or_oversized_data(monkeypatch, tmp_path):
    main = isolated_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "INTAKE_MAX_IMAGE_BYTES", 128)
    monkeypatch.setattr(main, "_upload_bytes_to_gcs", lambda *_: None)
    client = TestClient(main.app)
    image = io.BytesIO()
    PIL.Image.new("RGB", (2, 2)).save(image, "PNG")
    valid = client.post("/upload/model", files={"file": ("picture.png", image.getvalue(), "image/png")})
    assert valid.status_code == 200
    assert (tmp_path / "upload_dir" / valid.json()["filename"]).read_bytes() == image.getvalue()
    for payload in (b"", b"not a picture", b"x" * 129):
        response = client.post("/upload/garment", files={"file": ("picture.png", payload, "image/png")})
        assert response.status_code == 400
    assert len(list((tmp_path / "upload_dir").iterdir())) == 1
    client.close()


def test_zero_freedom_reaches_both_generation_paths_without_ai_calls(monkeypatch, tmp_path):
    main = isolated_main(monkeypatch, tmp_path)
    observed, prompts = [], []

    async def fake_generate(**kwargs):
        observed.append(kwargs["freedom"])
        return b"synthetic"

    async def fake_async(*_args, **_kwargs):
        return None

    def run_immediately(coroutine):
        try:
            coroutine.send(None)
        except StopIteration:
            return None
        raise AssertionError("unexpected asynchronous operation")

    monkeypatch.setattr(main, "asyncio", SimpleNamespace(create_task=run_immediately))
    monkeypatch.setattr(main, "TASKS", {})
    monkeypatch.setattr(main, "_PENDING_DEDUP", {})
    monkeypatch.setattr(main, "_admin_report", SimpleNamespace(report_tryon_task=fake_async))
    monkeypatch.setattr(main, "_generate_tryon_image_bytes", fake_generate)
    monkeypatch.setattr(main, "_check_and_consume_rate_limit", fake_async)
    monkeypatch.setattr(main, "_validate_model_key", lambda _model: "flash")
    monkeypatch.setattr(main, "_require_tryon_runtime_config", lambda: None)
    monkeypatch.setattr(main, "resolve_tryon_runtime_config", lambda: {"enabled": True, "api_key": "synthetic"})
    monkeypatch.setattr(main, "_read_base_prompt", lambda: "base")
    monkeypatch.setattr(main, "_rate_identity", lambda: "synthetic")
    monkeypatch.setattr(main, "_estimate_token_cost", lambda prompt: prompts.append(prompt) or 1)
    monkeypatch.setattr(main, "_save_generated_bytes", lambda _data, **_metadata: {"result_url": "/assets/result.png", "result_data_url": "data:image/png;base64,eA=="})
    monkeypatch.setattr(main, "_persist_task", lambda *_args: None)
    monkeypatch.setattr(main, "_prune_old_tasks", lambda: None)
    monkeypatch.setattr(main, "_record_key_usage", lambda *_args: None)
    client = TestClient(main.app)
    payload = {"target_image": "model.png", "reference_image": "garment.png", "freedom": "0"}
    assert client.post("/generate", data=payload).status_code == 200
    task = client.post("/submit-task", data=payload).json()
    assert client.get(f"/task/{task['task_id']}").json()["freedom"] == 0
    assert observed == [0, 0]
    assert all("FREEDOM LEVEL: 0/10" in prompt for prompt in prompts)
    client.close()

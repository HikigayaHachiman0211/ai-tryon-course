from __future__ import annotations

import sys

from app.object_storage import LocalObjectStorage, ObjectStorageSettings, build_public_blob_url, load_object_storage_settings


def test_workbench_azure_mode_does_not_require_gcp_configuration(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "courseassets")
    monkeypatch.setenv("AZURE_MEDIA_CONTAINER", "course-media")
    monkeypatch.delenv("RESULTS_GCS_BUCKET", raising=False)
    settings = load_object_storage_settings()
    assert settings.provider == "azure"
    assert settings.container == "course-media"


def test_workbench_azure_adapter_creation_does_not_import_gcp(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.cloud.storage", None)
    settings = ObjectStorageSettings(provider="azure", account_name="courseassets")
    from app.object_storage import create_object_storage

    assert create_object_storage(settings).__class__.__name__ == "AzureBlobStorage"


def test_workbench_public_url_preserves_encoded_object_name():
    settings = ObjectStorageSettings(
        provider="azure",
        account_name="courseassets",
        container="course-media",
        public_base_url="https://courseassets.blob.core.windows.net/course-media",
    )
    assert build_public_blob_url(settings, "uploads/a b(1).png").endswith("uploads/a%20b%281%29.png")


def test_workbench_local_adapter_supports_media_lifecycle(tmp_path):
    adapter = LocalObjectStorage(ObjectStorageSettings(provider="local", local_root=tmp_path))
    adapter.upload_bytes("history/result.png", b"result", content_type="image/png")
    assert adapter.exists("history/result.png")
    assert adapter.download_bytes("history/result.png") == b"result"
    assert [item.name for item in adapter.list_objects("history/")] == ["history/result.png"]
    assert adapter.delete("history/result.png") is True
    assert adapter.exists("history/result.png") is False

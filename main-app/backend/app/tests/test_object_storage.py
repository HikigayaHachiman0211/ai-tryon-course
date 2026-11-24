from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.object_storage import (
    AzureBlobStorage,
    ObjectStorageSettings,
    create_object_storage,
    load_object_storage_settings,
    ObjectStorageError,
)


class _Download:
    def __init__(self, value: bytes):
        self.value = value

    def readall(self) -> bytes:
        return self.value


class _Blob:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.value = b""
        self.content_type = None
        self.cache_control = None
        self.last_modified = datetime.now(timezone.utc)
        self.container = None

    def exists(self) -> bool:
        return bool(self.value)

    def download_blob(self) -> _Download:
        return _Download(self.value)

    def delete_blob(self) -> None:
        self.value = b""


class _Container:
    def __init__(self, account: str, name: str):
        self.objects: dict[str, _Blob] = {}
        self.account = account
        self.name = name

    def get_blob_client(self, name: str) -> _Blob:
        blob = self.objects.setdefault(
            name,
            _Blob(
                name,
                f"https://{self.account}.blob.core.windows.net/{self.name}/{name}",
            ),
        )
        blob.container = self
        return blob

    def upload_blob(self, name: str, data, overwrite: bool, content_settings):
        blob = self.get_blob_client(name)
        blob.value = data.read() if hasattr(data, "read") else data
        blob.content_type = content_settings.content_type
        blob.cache_control = content_settings.cache_control

    def list_blobs(self, name_starts_with: str = ""):
        return [blob for name, blob in self.objects.items() if name.startswith(name_starts_with)]


class _Service:
    def __init__(self):
        self.containers: dict[str, _Container] = {}

    def get_container_client(self, name: str) -> _Container:
        return self.containers.setdefault(name, _Container("courseassets", name))


def test_azure_provider_is_selected_without_importing_gcp(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "courseassets")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    settings = load_object_storage_settings()

    assert settings.provider == "azure"
    assert create_object_storage(settings).__class__.__name__ == "AzureBlobStorage"


def test_azure_blob_adapter_supports_upload_read_exists_list_delete_and_public_url():
    settings = ObjectStorageSettings(
        provider="azure",
        account_name="courseassets",
        connection_string="UseDevelopmentStorage=true",
        container="course-media",
        public_base_url="https://courseassets.blob.core.windows.net/course-media",
    )
    adapter = AzureBlobStorage(settings, service_client=_Service())

    url = adapter.upload_bytes(
        "history/用户 photo (1).png",
        b"image-bytes",
        content_type="image/png",
        cache_control="public, max-age=60",
    )

    assert url == "https://courseassets.blob.core.windows.net/course-media/history/%E7%94%A8%E6%88%B7%20photo%20%281%29.png"
    assert adapter.exists("history/用户 photo (1).png")
    assert adapter.download_bytes("history/用户 photo (1).png") == b"image-bytes"
    assert [item.name for item in adapter.list_objects("history/")] == ["history/用户 photo (1).png"]
    assert adapter.delete("history/用户 photo (1).png") is True
    assert adapter.exists("history/用户 photo (1).png") is False


def test_local_provider_is_rejected_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    with pytest.raises(ObjectStorageError):
        load_object_storage_settings()

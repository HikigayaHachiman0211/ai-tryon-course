"""Provider-neutral object storage for Admin.

The Admin routes keep their historical helper API in ``gcs.py``; this module
contains the provider selection and Azure Blob implementation behind it.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


class ObjectStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectStorageSettings:
    provider: str
    account_name: str = ""
    connection_string: str = ""
    container: str = "course-media"
    product_container: str = "product-assets"
    media_container: str = "course-media"
    backup_container: str = "backups"
    public_base_url: str = ""
    public_media_base_url: str = ""
    local_root: Path = Path("/tmp/admin-object-storage")
    gcs_bucket: str = ""
    oss_region: str = ""
    oss_endpoint: str = ""

    def base_url(self, container: str | None = None) -> str:
        selected = container or self.container
        if selected == self.product_container and self.public_base_url:
            return self.public_base_url.rstrip("/")
        if selected == self.media_container and self.public_media_base_url:
            return self.public_media_base_url.rstrip("/")
        if self.provider == "azure" and self.account_name:
            return f"https://{self.account_name}.blob.core.windows.net/{selected}"
        if self.provider == "gcs" and self.gcs_bucket:
            return f"https://storage.googleapis.com/{self.gcs_bucket}"
        if self.provider == "oss" and self.oss_region and selected:
            return f"https://{selected}.oss-{self.oss_region}.aliyuncs.com"
        return ""


def load_object_storage_settings(environ: dict[str, str] | None = None) -> ObjectStorageSettings:
    values = dict(os.environ if environ is None else environ)
    get = lambda key, default="": str(values.get(key, default) or "").strip()
    provider = get("OBJECT_STORAGE_PROVIDER").lower()
    if not provider:
        provider = "azure" if get("AZURE_STORAGE_ACCOUNT_NAME") else ("gcs" if get("GCS_BUCKET_NAME") else "local")
    if provider not in {"azure", "gcs", "oss", "local"}:
        raise ObjectStorageError("OBJECT_STORAGE_PROVIDER must be azure, gcs, oss, or local")
    if provider == "local" and get("APP_ENV").lower() in {"production", "prod"}:
        raise ObjectStorageError("local object storage is restricted to development and tests")
    if provider == "oss" and not (get("OSS_REGION") and get("OSS_MEDIA_BUCKET") and get("OSS_PRODUCT_BUCKET")):
        raise ObjectStorageError("OSS_REGION, OSS_MEDIA_BUCKET, and OSS_PRODUCT_BUCKET are required for OSS")
    return ObjectStorageSettings(
        provider=provider,
        account_name=get("AZURE_STORAGE_ACCOUNT_NAME"),
        connection_string=get("AZURE_STORAGE_CONNECTION_STRING"),
        container=get("OBJECT_STORAGE_CONTAINER") or (get("OSS_MEDIA_BUCKET") if provider == "oss" else get("AZURE_MEDIA_CONTAINER", "course-media")),
        product_container=get("OSS_PRODUCT_BUCKET") if provider == "oss" else get("AZURE_PRODUCT_CONTAINER", "product-assets"),
        media_container=get("OSS_MEDIA_BUCKET") if provider == "oss" else get("AZURE_MEDIA_CONTAINER", "course-media"),
        backup_container=get("OSS_BACKUP_BUCKET") if provider == "oss" else get("AZURE_BACKUP_CONTAINER", "backups"),
        public_base_url=get("PUBLIC_IMAGE_BASE_URL"),
        public_media_base_url=get("PUBLIC_MEDIA_BASE_URL"),
        local_root=Path(get("OBJECT_STORAGE_LOCAL_ROOT", "/tmp/admin-object-storage")),
        gcs_bucket=get("GCS_BUCKET_NAME"),
        oss_region=get("OSS_REGION"),
        oss_endpoint=get("OSS_ENDPOINT"),
    )


def build_public_blob_url(settings: ObjectStorageSettings, name: str, *, container: str | None = None) -> str:
    base = settings.base_url(container)
    return f"{base}/{quote(str(name).lstrip('/'), safe='/')}" if base else ""


class LocalObjectStorage:
    def __init__(self, settings: ObjectStorageSettings):
        self.settings = settings
        self.root = settings.local_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        path = (self.root / str(name).lstrip("/")).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ObjectStorageError("object name escapes local storage root") from exc
        return path

    def upload(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None, container: str | None = None) -> str:
        del content_type, cache_control
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return build_public_blob_url(self.settings, name, container=container) or f"file://{path}"

    def list(self, prefix: str = "", *, max_results: int = 500, container: str | None = None) -> list[dict[str, Any]]:
        del container
        result = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.relative_to(self.root).as_posix().startswith(prefix):
                result.append({"name": path.relative_to(self.root).as_posix(), "size": path.stat().st_size, "content_type": None, "updated": None, "url": ""})
                if len(result) >= max_results:
                    break
        return result

    def download(self, name: str, *, container: str | None = None) -> bytes | None:
        del container
        path = self._path(name)
        return path.read_bytes() if path.is_file() else None

    def exists(self, name: str, *, container: str | None = None) -> bool:
        del container
        return self._path(name).is_file()

    def delete(self, name: str, *, container: str | None = None) -> bool:
        del container
        path = self._path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "provider": "local", "container": self.settings.container}


class AzureBlobStorage:
    def __init__(self, settings: ObjectStorageSettings, *, service_client: Any = None):
        if settings.provider != "azure":
            raise ObjectStorageError("AzureBlobStorage requires provider=azure")
        self.settings = settings
        self._service_client = service_client

    def _service(self):
        if self._service_client is not None:
            return self._service_client
        try:
            from azure.storage.blob import BlobServiceClient
            if self.settings.connection_string:
                self._service_client = BlobServiceClient.from_connection_string(self.settings.connection_string)
            else:
                from azure.identity import DefaultAzureCredential
                self._service_client = BlobServiceClient(
                    account_url=f"https://{self.settings.account_name}.blob.core.windows.net",
                    credential=DefaultAzureCredential(),
                )
            return self._service_client
        except Exception as exc:
            raise ObjectStorageError("Azure Blob SDK could not be initialized") from exc

    def _container(self, name: str | None = None):
        return self._service().get_container_client(name or self.settings.container)

    def upload(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None, container: str | None = None) -> str:
        from azure.storage.blob import ContentSettings
        self._container(container).upload_blob(
            str(name).lstrip("/"), io.BytesIO(data), overwrite=True,
            content_settings=ContentSettings(content_type=content_type, cache_control=cache_control),
        )
        return build_public_blob_url(self.settings, name, container=container)

    def list(self, prefix: str = "", *, max_results: int = 500, container: str | None = None) -> list[dict[str, Any]]:
        result = []
        for blob in self._container(container).list_blobs(name_starts_with=prefix):
            result.append({
                "name": str(blob.name),
                "size": getattr(blob, "size", None),
                "updated": getattr(blob, "last_modified", None),
                "content_type": getattr(blob, "content_type", None),
                "url": build_public_blob_url(self.settings, str(blob.name), container=container),
            })
            if len(result) >= max_results:
                break
        return result

    def download(self, name: str, *, container: str | None = None) -> bytes | None:
        blob = self._container(container).get_blob_client(str(name).lstrip("/"))
        if not blob.exists():
            return None
        return blob.download_blob().readall()

    def exists(self, name: str, *, container: str | None = None) -> bool:
        return bool(self._container(container).get_blob_client(str(name).lstrip("/")).exists())

    def delete(self, name: str, *, container: str | None = None) -> bool:
        blob = self._container(container).get_blob_client(str(name).lstrip("/"))
        if not blob.exists():
            return False
        blob.delete_blob()
        return True

    def health_check(self) -> dict[str, Any]:
        try:
            self.list(max_results=1)
            return {"ok": True, "provider": "azure", "container": self.settings.container}
        except Exception as exc:
            return {"ok": False, "provider": "azure", "container": self.settings.container, "error": type(exc).__name__}


class OSSObjectStorage:
    def __init__(self, settings: ObjectStorageSettings, *, service_client: Any = None):
        from app.services.oss_client import OSSClient

        if settings.provider != "oss":
            raise ObjectStorageError("OSSObjectStorage requires provider=oss")
        self.settings = settings
        self._oss = OSSClient(settings.oss_region, settings.oss_endpoint, service_client=service_client)

    def upload(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None, container: str | None = None) -> str:
        selected = container or self.settings.container
        self._oss.upload(selected, name, data, content_type=content_type, cache_control=cache_control)
        return build_public_blob_url(self.settings, name, container=selected)

    def download(self, name: str, *, container: str | None = None) -> bytes | None:
        return self._oss.download(container or self.settings.container, name)

    def exists(self, name: str, *, container: str | None = None) -> bool:
        return self._oss.exists(container or self.settings.container, name)

    def delete(self, name: str, *, container: str | None = None) -> bool:
        return self._oss.delete(container or self.settings.container, name)

    def list(self, prefix: str = "", *, max_results: int = 500, container: str | None = None) -> list[dict[str, Any]]:
        selected = container or self.settings.container
        return [{"name": item.key, "size": item.size, "updated": item.last_modified,
                 "content_type": None, "url": build_public_blob_url(self.settings, item.key, container=selected)}
                for item in self._oss.list(selected, prefix, max_results=max_results)]

    def health_check(self) -> dict[str, Any]:
        try:
            self.list(max_results=1)
            return {"ok": True, "provider": "oss", "container": self.settings.container}
        except Exception as exc:
            return {"ok": False, "provider": "oss", "container": self.settings.container, "error": type(exc).__name__}


class GCSObjectStorage:
    def __init__(self, settings: ObjectStorageSettings):
        self.settings = settings
        self._bucket = None

    def _get_bucket(self):
        if self._bucket is None:
            from google.cloud import storage
            self._bucket = storage.Client().bucket(self.settings.gcs_bucket)
        return self._bucket

    def upload(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None, container: str | None = None) -> str:
        del container
        blob = self._get_bucket().blob(str(name).lstrip("/"))
        blob.cache_control = cache_control
        blob.upload_from_string(data, content_type=content_type)
        return build_public_blob_url(self.settings, name)

    def list(self, prefix: str = "", *, max_results: int = 500, container: str | None = None) -> list[dict[str, Any]]:
        del container
        return [{"name": b.name, "size": b.size, "updated": b.updated, "content_type": b.content_type, "url": b.public_url} for b in self._get_bucket().list_blobs(prefix=prefix, max_results=max_results)]

    def download(self, name: str, *, container: str | None = None) -> bytes | None:
        del container
        blob = self._get_bucket().blob(name)
        return blob.download_as_bytes() if blob.exists() else None

    def exists(self, name: str, *, container: str | None = None) -> bool:
        del container
        return bool(self._get_bucket().blob(name).exists())

    def delete(self, name: str, *, container: str | None = None) -> bool:
        del container
        blob = self._get_bucket().blob(name)
        if not blob.exists():
            return False
        blob.delete()
        return True

    def health_check(self) -> dict[str, Any]:
        try:
            self.list(max_results=1)
            return {"ok": True, "provider": "gcs", "container": self.settings.gcs_bucket}
        except Exception as exc:
            return {"ok": False, "provider": "gcs", "error": type(exc).__name__}


def create_object_storage(settings: ObjectStorageSettings | None = None, *, service_client: Any = None):
    selected = settings or load_object_storage_settings()
    if selected.provider == "local" and os.environ.get("APP_ENV", "").strip().lower() in {"production", "prod"}:
        raise ObjectStorageError("local object storage is restricted to development and tests")
    if selected.provider == "azure":
        return AzureBlobStorage(selected, service_client=service_client)
    if selected.provider == "oss":
        return OSSObjectStorage(selected, service_client=service_client)
    if selected.provider == "gcs":
        return GCSObjectStorage(selected)
    if selected.provider == "local":
        return LocalObjectStorage(selected)
    raise ObjectStorageError(f"unsupported object storage provider: {selected.provider}")

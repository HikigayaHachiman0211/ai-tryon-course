"""Object storage adapter used by Workbench uploads and generated media."""

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
class ObjectInfo:
    name: str
    size: int | None = None
    content_type: str | None = None
    last_modified: Any = None


@dataclass(frozen=True)
class ObjectStorageSettings:
    provider: str
    account_name: str = ""
    connection_string: str = ""
    container: str = "course-media"
    public_base_url: str = ""
    local_root: Path = Path("/tmp/workbench-object-storage")
    gcs_bucket: str = ""
    oss_region: str = ""
    oss_endpoint: str = ""

    def base_url(self) -> str:
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        if self.provider == "azure" and self.account_name:
            return f"https://{self.account_name}.blob.core.windows.net/{self.container}"
        if self.provider == "gcs" and self.gcs_bucket:
            return f"https://storage.googleapis.com/{self.gcs_bucket}"
        if self.provider == "oss" and self.oss_region and self.container:
            return f"https://{self.container}.oss-{self.oss_region}.aliyuncs.com"
        return ""


def load_object_storage_settings(environ: dict[str, str] | None = None) -> ObjectStorageSettings:
    values = dict(os.environ if environ is None else environ)
    get = lambda key, default="": str(values.get(key, default) or "").strip()
    provider = get("OBJECT_STORAGE_PROVIDER").lower()
    if not provider:
        provider = "azure" if get("AZURE_STORAGE_ACCOUNT_NAME") else ("gcs" if get("RESULTS_GCS_BUCKET") else "local")
    if provider not in {"azure", "gcs", "oss", "local"}:
        raise ObjectStorageError("OBJECT_STORAGE_PROVIDER must be azure, gcs, oss, or local")
    if provider == "local" and get("APP_ENV").lower() in {"production", "prod"}:
        raise ObjectStorageError("local object storage is restricted to development and tests")
    if provider == "oss" and not (get("OSS_REGION") and get("OSS_MEDIA_BUCKET")):
        raise ObjectStorageError("OSS_REGION and OSS_MEDIA_BUCKET are required for OSS")
    return ObjectStorageSettings(
        provider=provider,
        account_name=get("AZURE_STORAGE_ACCOUNT_NAME"),
        connection_string=get("AZURE_STORAGE_CONNECTION_STRING"),
        container=get("OBJECT_STORAGE_CONTAINER") or (get("OSS_MEDIA_BUCKET") if provider == "oss" else get("AZURE_MEDIA_CONTAINER", "course-media")),
        public_base_url=get("PUBLIC_MEDIA_BASE_URL"),
        local_root=Path(get("OBJECT_STORAGE_LOCAL_ROOT", "/tmp/workbench-object-storage")),
        gcs_bucket=get("RESULTS_GCS_BUCKET"),
        oss_region=get("OSS_REGION"),
        oss_endpoint=get("OSS_ENDPOINT"),
    )


def build_public_blob_url(settings: ObjectStorageSettings, name: str) -> str:
    base = settings.base_url()
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

    def upload_bytes(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None) -> str:
        del content_type, cache_control
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return build_public_blob_url(self.settings, name) or f"file://{path}"

    def download_bytes(self, name: str) -> bytes | None:
        path = self._path(name)
        return path.read_bytes() if path.is_file() else None

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def list_objects(self, prefix: str = "", *, max_results: int = 500) -> list[ObjectInfo]:
        normalized = str(prefix).lstrip("/")
        result: list[ObjectInfo] = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                name = path.relative_to(self.root).as_posix()
                if name.startswith(normalized):
                    result.append(ObjectInfo(name=name, size=path.stat().st_size))
                    if len(result) >= max_results:
                        break
        return result

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

    def upload_bytes(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None) -> str:
        from azure.storage.blob import ContentSettings
        self._service().get_container_client(self.settings.container).upload_blob(
            str(name).lstrip("/"), io.BytesIO(data), overwrite=True,
            content_settings=ContentSettings(content_type=content_type, cache_control=cache_control),
        )
        return build_public_blob_url(self.settings, name)

    def _container(self):
        return self._service().get_container_client(self.settings.container)

    def download_bytes(self, name: str) -> bytes | None:
        blob = self._container().get_blob_client(str(name).lstrip("/"))
        try:
            if hasattr(blob, "exists") and not blob.exists():
                return None
            return blob.download_blob().readall()
        except Exception as exc:
            if exc.__class__.__name__ in {"ResourceNotFoundError", "BlobNotFound"}:
                return None
            raise

    def exists(self, name: str) -> bool:
        return bool(self._container().get_blob_client(str(name).lstrip("/")).exists())

    def delete(self, name: str) -> bool:
        blob = self._container().get_blob_client(str(name).lstrip("/"))
        if not blob.exists():
            return False
        blob.delete_blob()
        return True

    def list_objects(self, prefix: str = "", *, max_results: int = 500) -> list[ObjectInfo]:
        result: list[ObjectInfo] = []
        for blob in self._container().list_blobs(name_starts_with=str(prefix).lstrip("/")):
            result.append(
                ObjectInfo(
                    name=str(blob.name),
                    size=getattr(blob, "size", None),
                    content_type=getattr(blob, "content_type", None),
                    last_modified=getattr(blob, "last_modified", None),
                )
            )
            if len(result) >= max_results:
                break
        return result

    def health_check(self) -> dict[str, Any]:
        try:
            list(self._service().get_container_client(self.settings.container).list_blobs(results_per_page=1))
            return {"ok": True, "provider": "azure", "container": self.settings.container}
        except Exception as exc:
            return {"ok": False, "provider": "azure", "container": self.settings.container, "error": type(exc).__name__}


class OSSObjectStorage:
    def __init__(self, settings: ObjectStorageSettings, *, service_client: Any = None):
        from app.oss_client import OSSClient

        if settings.provider != "oss":
            raise ObjectStorageError("OSSObjectStorage requires provider=oss")
        self.settings = settings
        self._oss = OSSClient(settings.oss_region, settings.oss_endpoint, service_client=service_client)

    def upload_bytes(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None) -> str:
        self._oss.upload(self.settings.container, name, data, content_type=content_type, cache_control=cache_control)
        return build_public_blob_url(self.settings, name)

    def download_bytes(self, name: str) -> bytes | None:
        return self._oss.download(self.settings.container, name)

    def exists(self, name: str) -> bool:
        return self._oss.exists(self.settings.container, name)

    def delete(self, name: str) -> bool:
        return self._oss.delete(self.settings.container, name)

    def list_objects(self, prefix: str = "", *, max_results: int = 500) -> list[ObjectInfo]:
        return [ObjectInfo(name=item.key, size=item.size, last_modified=item.last_modified)
                for item in self._oss.list(self.settings.container, prefix, max_results=max_results)]

    def health_check(self) -> dict[str, Any]:
        try:
            self.list_objects(max_results=1)
            return {"ok": True, "provider": "oss", "container": self.settings.container}
        except Exception as exc:
            return {"ok": False, "provider": "oss", "container": self.settings.container, "error": type(exc).__name__}


class GCSObjectStorage:
    """Optional compatibility adapter; imported only when provider=gcs."""

    def __init__(self, settings: ObjectStorageSettings):
        self.settings = settings
        self._bucket = None

    def _get_bucket(self):
        if self._bucket is None:
            from google.cloud import storage
            self._bucket = storage.Client().bucket(self.settings.gcs_bucket)
        return self._bucket

    def upload_bytes(self, name: str, data: bytes, *, content_type: str = "application/octet-stream", cache_control: str | None = None) -> str:
        blob = self._get_bucket().blob(name)
        blob.cache_control = cache_control
        blob.upload_from_string(data, content_type=content_type)
        return build_public_blob_url(self.settings, name)

    def download_bytes(self, name: str) -> bytes | None:
        blob = self._get_bucket().blob(str(name).lstrip("/"))
        return blob.download_as_bytes() if blob.exists() else None

    def exists(self, name: str) -> bool:
        return bool(self._get_bucket().blob(str(name).lstrip("/")).exists())

    def delete(self, name: str) -> bool:
        blob = self._get_bucket().blob(str(name).lstrip("/"))
        if not blob.exists():
            return False
        blob.delete()
        return True

    def list_objects(self, prefix: str = "", *, max_results: int = 500) -> list[ObjectInfo]:
        return [
            ObjectInfo(
                name=str(blob.name),
                size=getattr(blob, "size", None),
                content_type=getattr(blob, "content_type", None),
                last_modified=getattr(blob, "updated", None),
            )
            for blob in self._get_bucket().list_blobs(prefix=str(prefix).lstrip("/"), max_results=max_results)
        ]

    def health_check(self) -> dict[str, Any]:
        try:
            next(iter(self._get_bucket().list_blobs(max_results=1)), None)
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


_cached_storage: Any = None


def get_object_storage():
    global _cached_storage
    if _cached_storage is None:
        _cached_storage = create_object_storage(load_object_storage_settings())
    return _cached_storage

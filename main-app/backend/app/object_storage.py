"""Provider-neutral object storage for the main application.

Azure is the release provider.  GCS remains a lazy, opt-in compatibility
provider and local storage is available for development and tests.  Keeping
provider construction here prevents route handlers from importing cloud SDKs
or accidentally initializing GCP clients in Azure mode.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

logger = logging.getLogger(__name__)


class ObjectStorageError(RuntimeError):
    """Raised when a configured object-storage provider cannot be used."""


@dataclass(frozen=True)
class ObjectStorageSettings:
    provider: str
    account_name: str = ""
    connection_string: str = ""
    container: str = "course-media"
    public_base_url: str = ""
    local_root: Path = Path("/tmp/object-storage")
    gcs_bucket: str = ""
    oss_region: str = ""
    oss_endpoint: str = ""

    @property
    def public_url_base(self) -> str:
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        if self.provider == "azure" and self.account_name:
            return f"https://{self.account_name}.blob.core.windows.net/{self.container}"
        if self.provider == "gcs" and self.gcs_bucket:
            return f"https://storage.googleapis.com/{self.gcs_bucket}"
        if self.provider == "oss" and self.oss_region and self.container:
            return f"https://{self.container}.oss-{self.oss_region}.aliyuncs.com"
        return ""


@dataclass(frozen=True)
class ObjectInfo:
    name: str
    size: int | None = None
    content_type: str | None = None
    last_modified: Any = None


def _env_value(environ: dict[str, str], key: str, default: str = "") -> str:
    return str(environ.get(key, default) or "").strip()


def load_object_storage_settings(environ: dict[str, str] | None = None) -> ObjectStorageSettings:
    values = dict(os.environ if environ is None else environ)
    provider = _env_value(values, "OBJECT_STORAGE_PROVIDER").lower()
    if not provider:
        provider = "azure" if _env_value(values, "AZURE_STORAGE_ACCOUNT_NAME") else (
            "gcs" if _env_value(values, "GCS_BUCKET_NAME") else "local"
        )
    if provider not in {"azure", "gcs", "oss", "local"}:
        raise ObjectStorageError("OBJECT_STORAGE_PROVIDER must be azure, gcs, oss, or local")
    if provider == "local" and _env_value(values, "APP_ENV").lower() in {"production", "prod"}:
        raise ObjectStorageError("local object storage is restricted to development and tests")
    if provider == "oss" and not (_env_value(values, "OSS_REGION") and _env_value(values, "OSS_MEDIA_BUCKET")):
        raise ObjectStorageError("OSS_REGION and OSS_MEDIA_BUCKET are required for OSS")

    account_name = _env_value(values, "AZURE_STORAGE_ACCOUNT_NAME")
    container = _env_value(values, "OBJECT_STORAGE_CONTAINER") or (
        _env_value(values, "OSS_MEDIA_BUCKET") if provider == "oss"
        else _env_value(values, "AZURE_MEDIA_CONTAINER", "course-media")
    )
    public_base_url = _env_value(values, "PUBLIC_MEDIA_BASE_URL")
    if not public_base_url and provider != "oss":
        public_base_url = _env_value(values, "PUBLIC_IMAGE_BASE_URL")
    local_root = Path(_env_value(values, "OBJECT_STORAGE_LOCAL_ROOT", "/tmp/object-storage"))
    return ObjectStorageSettings(
        provider=provider,
        account_name=account_name,
        connection_string=_env_value(values, "AZURE_STORAGE_CONNECTION_STRING"),
        container=container,
        public_base_url=public_base_url,
        local_root=local_root,
        gcs_bucket=_env_value(values, "GCS_BUCKET_NAME"),
        oss_region=_env_value(values, "OSS_REGION"),
        oss_endpoint=_env_value(values, "OSS_ENDPOINT"),
    )


def build_public_blob_url(settings: ObjectStorageSettings, name: str) -> str:
    base = settings.public_url_base
    if not base:
        return ""
    return f"{base}/{quote(str(name).lstrip('/'), safe='/')}"


class LocalObjectStorage:
    def __init__(self, settings: ObjectStorageSettings):
        self.settings = settings
        self.root = settings.local_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        candidate = (self.root / str(name).lstrip("/")).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ObjectStorageError("object name escapes local storage root") from exc
        return candidate

    def upload_bytes(self, name: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None) -> str:
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
        results: list[ObjectInfo] = []
        if not self.root.exists():
            return results
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                name = path.relative_to(self.root).as_posix()
                if name.startswith(normalized):
                    results.append(ObjectInfo(name=name, size=path.stat().st_size))
                    if len(results) >= max_results:
                        break
        return results

    def health_check(self) -> dict[str, Any]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "provider": "local", "container": self.settings.container}
        except OSError as exc:
            return {"ok": False, "provider": "local", "error": type(exc).__name__}


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

                if not self.settings.account_name:
                    raise ObjectStorageError("AZURE_STORAGE_ACCOUNT_NAME is required without a connection string")
                self._service_client = BlobServiceClient(
                    account_url=f"https://{self.settings.account_name}.blob.core.windows.net",
                    credential=DefaultAzureCredential(),
                )
            return self._service_client
        except ObjectStorageError:
            raise
        except Exception as exc:
            raise ObjectStorageError("Azure Blob SDK could not be initialized") from exc

    def _container(self):
        return self._service().get_container_client(self.settings.container)

    @staticmethod
    def _content_settings(content_type: str | None, cache_control: str | None):
        from azure.storage.blob import ContentSettings

        return ContentSettings(content_type=content_type, cache_control=cache_control)

    def upload_bytes(self, name: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None) -> str:
        self._container().upload_blob(
            str(name).lstrip("/"),
            io.BytesIO(data),
            overwrite=True,
            content_settings=self._content_settings(content_type, cache_control),
        )
        return build_public_blob_url(self.settings, name)

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
        blob = self._container().get_blob_client(str(name).lstrip("/"))
        return bool(blob.exists())

    def delete(self, name: str) -> bool:
        blob = self._container().get_blob_client(str(name).lstrip("/"))
        if not blob.exists():
            return False
        blob.delete_blob()
        return True

    def list_objects(self, prefix: str = "", *, max_results: int = 500) -> list[ObjectInfo]:
        items: list[ObjectInfo] = []
        for blob in self._container().list_blobs(name_starts_with=str(prefix).lstrip("/")):
            items.append(
                ObjectInfo(
                    name=str(blob.name),
                    size=getattr(blob, "size", None),
                    content_type=getattr(blob, "content_type", None),
                    last_modified=getattr(blob, "last_modified", None),
                )
            )
            if len(items) >= max_results:
                break
        return items

    def health_check(self) -> dict[str, Any]:
        try:
            self.list_objects("", max_results=1)
            return {"ok": True, "provider": "azure", "container": self.settings.container}
        except Exception as exc:
            logger.warning("Azure Blob health check failed: %s", type(exc).__name__)
            return {"ok": False, "provider": "azure", "container": self.settings.container, "error": type(exc).__name__}


class OSSObjectStorage:
    def __init__(self, settings: ObjectStorageSettings, *, service_client: Any = None):
        from app.oss_client import OSSClient

        if settings.provider != "oss":
            raise ObjectStorageError("OSSObjectStorage requires provider=oss")
        self.settings = settings
        self._oss = OSSClient(settings.oss_region, settings.oss_endpoint, service_client=service_client)

    def upload_bytes(self, name: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None) -> str:
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
    """Lazy GCS compatibility adapter. It is never constructed in Azure mode."""

    def __init__(self, settings: ObjectStorageSettings):
        if settings.provider != "gcs":
            raise ObjectStorageError("GCSObjectStorage requires provider=gcs")
        self.settings = settings
        self._bucket = None

    def _get_bucket(self):
        if self._bucket is not None:
            return self._bucket
        try:
            from google.cloud import storage

            self._bucket = storage.Client().bucket(self.settings.gcs_bucket)
            return self._bucket
        except Exception as exc:
            raise ObjectStorageError("GCS client could not be initialized") from exc

    def upload_bytes(self, name: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None) -> str:
        blob = self._get_bucket().blob(str(name).lstrip("/"))
        if cache_control:
            blob.cache_control = cache_control
        blob.upload_from_string(data, content_type=content_type)
        return build_public_blob_url(self.settings, name)

    def download_bytes(self, name: str) -> bytes | None:
        blob = self._get_bucket().blob(str(name).lstrip("/"))
        if not blob.exists():
            return None
        return blob.download_as_bytes()

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
            ObjectInfo(name=blob.name, size=blob.size, content_type=blob.content_type, last_modified=blob.updated)
            for blob in self._get_bucket().list_blobs(prefix=prefix, max_results=max_results)
        ]

    def health_check(self) -> dict[str, Any]:
        try:
            self.list_objects("", max_results=1)
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
        settings = load_object_storage_settings()
        if settings.provider not in {"azure", "gcs", "oss", "local"}:
            if os.getenv("APP_ENV", "").lower() in {"production", "prod"}:
                raise ObjectStorageError("unknown object storage provider in production")
        _cached_storage = create_object_storage(settings)
    return _cached_storage

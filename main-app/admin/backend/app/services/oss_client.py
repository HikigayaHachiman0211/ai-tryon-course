"""Small Alibaba OSS SDK v2 wrapper shared by each independently built service."""
from __future__ import annotations

import os
from typing import Any


def _missing_object(exc: Exception) -> bool:
    """Recognize a missing object without hiding missing buckets or access errors."""
    import alibabacloud_oss_v2 as oss

    detail = exc.unwrap() if isinstance(exc, oss.exceptions.OperationError) else exc
    return isinstance(detail, oss.exceptions.ServiceError) and (
        detail.code == "NoSuchKey"
        or (detail.status_code == 404 and detail.code == "BadErrorResponse")
    )


class OSSClient:
    def __init__(self, region: str, endpoint: str = "", *, service_client: Any = None):
        self.region = region
        self.endpoint = endpoint
        self._service_client = service_client

    def _client(self):
        if self._service_client is not None:
            return self._service_client

        import alibabacloud_oss_v2 as oss

        if not self.region:
            raise ValueError("OSS_REGION is required")
        mode = os.getenv("OSS_CREDENTIAL_MODE", "env").strip().lower()
        if mode == "env":
            provider = oss.credentials.EnvironmentVariableCredentialsProvider()
        elif mode == "ecs_role":
            from alibabacloud_credentials.client import Client as CredentialsClient
            from alibabacloud_credentials.models import Config as CredentialsConfig

            role = os.getenv("OSS_ECS_ROLE_NAME", "").strip()
            credentials = CredentialsClient(CredentialsConfig(type="ecs_ram_role", role_name=role or None))

            def fetch_credentials():
                value = credentials.get_credential()
                return oss.credentials.Credentials(
                    access_key_id=value.access_key_id,
                    access_key_secret=value.access_key_secret,
                    security_token=value.security_token,
                )

            provider = oss.credentials.CredentialsProviderFunc(func=fetch_credentials)
        else:
            raise ValueError("OSS_CREDENTIAL_MODE must be env or ecs_role")
        config = oss.config.load_default()
        config.region = self.region
        config.credentials_provider = provider
        if self.endpoint:
            config.endpoint = self.endpoint
        self._service_client = oss.Client(config)
        return self._service_client

    def upload(self, bucket: str, name: str, data: bytes, *, content_type: str | None, cache_control: str | None):
        import alibabacloud_oss_v2 as oss

        self._client().put_object(oss.PutObjectRequest(
            bucket=bucket, key=str(name).lstrip("/"), body=data,
            content_type=content_type, cache_control=cache_control,
        ))

    def download(self, bucket: str, name: str) -> bytes | None:
        import alibabacloud_oss_v2 as oss

        try:
            result = self._client().get_object(oss.GetObjectRequest(bucket=bucket, key=str(name).lstrip("/")))
            try:
                return result.body.read()
            finally:
                result.body.close()
        except Exception as exc:
            if _missing_object(exc):
                return None
            raise

    def exists(self, bucket: str, name: str) -> bool:
        import alibabacloud_oss_v2 as oss

        try:
            self._client().head_object(oss.HeadObjectRequest(bucket=bucket, key=str(name).lstrip("/")))
            return True
        except Exception as exc:
            if _missing_object(exc):
                return False
            raise

    def delete(self, bucket: str, name: str) -> bool:
        import alibabacloud_oss_v2 as oss

        if not self.exists(bucket, name):
            return False
        self._client().delete_object(oss.DeleteObjectRequest(bucket=bucket, key=str(name).lstrip("/")))
        return True

    def list(self, bucket: str, prefix: str = "", *, max_results: int = 500) -> list[Any]:
        import alibabacloud_oss_v2 as oss

        items = []
        token = None
        while len(items) < max_results:
            page = self._client().list_objects_v2(oss.ListObjectsV2Request(
                bucket=bucket, prefix=str(prefix).lstrip("/"),
                max_keys=min(1000, max_results - len(items)), continuation_token=token,
            ))
            items.extend((page.contents or [])[:max_results - len(items)])
            if not page.is_truncated:
                break
            next_token = page.next_continuation_token
            if not next_token or next_token == token:
                raise RuntimeError("OSS returned an invalid continuation token")
            token = next_token
        return items

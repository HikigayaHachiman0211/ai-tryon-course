from pathlib import Path
import sys
from unittest.mock import patch
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.test_fakes.oss import FakeOSSClient
from app.object_storage import create_object_storage, load_object_storage_settings


def _settings():
    return load_object_storage_settings({
        "OBJECT_STORAGE_PROVIDER": "oss", "OSS_REGION": "cn-hangzhou",
        "OSS_MEDIA_BUCKET": "course-media-example", "OSS_PRODUCT_BUCKET": "product-example",
        "PUBLIC_IMAGE_BASE_URL": "https://cdn.example.com/products",
    })


def test_oss_media_settings_do_not_use_product_url():
    settings = _settings()
    assert settings.container == "course-media-example"
    assert settings.public_url_base == "https://course-media-example.oss-cn-hangzhou.aliyuncs.com"


def test_oss_media_lifecycle_and_paginated_listing():
    client = FakeOSSClient()
    adapter = create_object_storage(_settings(), service_client=client)
    url = adapter.upload_bytes("history/用户 (1).png", b"img", content_type="image/png", cache_control="no-store")
    adapter.upload_bytes("history/b.png", b"b")
    adapter.upload_bytes("history/c.png", b"")
    assert url == "https://course-media-example.oss-cn-hangzhou.aliyuncs.com/history/%E7%94%A8%E6%88%B7%20%281%29.png"
    assert client.objects[("course-media-example", "history/用户 (1).png")][1:] == ("image/png", "no-store")
    assert adapter.exists("history/c.png")
    assert adapter.download_bytes("history/用户 (1).png") == b"img"
    assert len(adapter.list_objects("history/", max_results=3)) == 3
    assert len(client.list_requests) == 2
    assert adapter.delete("history/用户 (1).png") is True
    assert adapter.delete("history/用户 (1).png") is False
    assert adapter.download_bytes("missing") is None
    client.read_forbidden = True
    with pytest.raises(Exception):
        adapter.exists("history/c.png")


def test_history_photo_upload_uses_oss_media_bucket():
    from app.gcs_storage import save_user_photo
    client = FakeOSSClient()
    adapter = create_object_storage(_settings(), service_client=client)
    with patch("app.gcs_storage.get_object_storage", return_value=adapter):
        url = save_user_photo("test-id", b"jpeg", content_type="image/jpeg")
    assert url.startswith("https://course-media-example.oss-cn-hangzhou.aliyuncs.com/")
    assert client.objects[("course-media-example", "ai-tryon-results/user_photos/test-id.jpg")][2] == "no-store, max-age=0"


def test_ecs_role_credentials_are_refreshed_per_request(monkeypatch):
    import alibabacloud_oss_v2 as oss
    from app.oss_client import OSSClient

    class CredentialClient:
        def __init__(self, config):
            assert config.type == "ecs_ram_role" and config.role_name == "course-role"
            self.calls = 0

        def get_credential(self):
            self.calls += 1
            return SimpleNamespace(access_key_id=f"id-{self.calls}", access_key_secret="test-secret", security_token="test-token")

    monkeypatch.setenv("OSS_CREDENTIAL_MODE", "ecs_role")
    monkeypatch.setenv("OSS_ECS_ROLE_NAME", "course-role")
    with patch("alibabacloud_credentials.client.Client", CredentialClient), patch.object(oss, "Client", side_effect=lambda config: config):
        config = OSSClient("cn-hangzhou")._client()
        assert config.credentials_provider.get_credentials().access_key_id == "id-1"
        assert config.credentials_provider.get_credentials().access_key_id == "id-2"


def test_oss_requires_region_and_media_bucket():
    from app.object_storage import ObjectStorageError
    with pytest.raises(ObjectStorageError):
        load_object_storage_settings({"OBJECT_STORAGE_PROVIDER": "oss", "OSS_REGION": "cn-hangzhou"})


def test_real_oss_sdk_signs_upload_for_the_configured_bucket(monkeypatch):
    import requests

    monkeypatch.setenv("OSS_CREDENTIAL_MODE", "env")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "test-id")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "test-secret")
    captured = []

    def send(self, method, url, **kwargs):
        captured.append((method, url, kwargs))
        response = requests.Response()
        response.status_code = 200
        response._content = b""
        response.headers["x-oss-request-id"] = "test-request"
        response.url = url
        return response

    with patch("requests.sessions.Session.request", send):
        adapter = create_object_storage(_settings())
        adapter.upload_bytes("uploads/image.png", b"image", content_type="image/png", cache_control="no-store")

    method, url, kwargs = captured[0]
    assert method == "PUT"
    assert url == "https://course-media-example.oss-cn-hangzhou.aliyuncs.com/uploads/image.png"
    headers = {key.lower(): value for key, value in kwargs["headers"].items()}
    assert headers["content-type"] == "image/png"
    assert headers["cache-control"] == "no-store"
    assert headers["authorization"].startswith("OSS4-HMAC-SHA256")

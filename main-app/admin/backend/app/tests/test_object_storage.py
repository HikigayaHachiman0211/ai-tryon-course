from __future__ import annotations

from app.services.object_storage import ObjectStorageSettings, build_public_blob_url, load_object_storage_settings


def test_admin_storage_settings_use_azure_media_container(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "courseassets")
    monkeypatch.setenv("AZURE_MEDIA_CONTAINER", "course-media")
    settings = load_object_storage_settings()
    assert settings.provider == "azure"
    assert settings.container == "course-media"


def test_admin_public_blob_url_quotes_unicode_and_parentheses():
    settings = ObjectStorageSettings(
        provider="azure",
        account_name="courseassets",
        container="product-assets",
        public_base_url="https://courseassets.blob.core.windows.net/product-assets",
    )
    assert build_public_blob_url(settings, "羽绒服 (蓝).png") == (
        "https://courseassets.blob.core.windows.net/product-assets/%E7%BE%BD%E7%BB%92%E6%9C%8D%20%28%E8%93%9D%29.png"
    )

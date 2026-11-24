from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from scripts.test_fakes.oss import FakeOSSClient
from app.services.object_storage import create_object_storage, load_object_storage_settings


def _settings():
    return load_object_storage_settings({
        "OBJECT_STORAGE_PROVIDER": "oss", "OSS_REGION": "cn-hangzhou",
        "OSS_PRODUCT_BUCKET": "product-example", "OSS_MEDIA_BUCKET": "course-media-example",
    })


def test_admin_oss_separates_product_and_media_buckets():
    settings = _settings()
    client = FakeOSSClient()
    storage = create_object_storage(settings, service_client=client)
    product_url = storage.upload("sample_models/男/a.png", b"product", container=settings.product_container)
    media_url = storage.upload("tryon-results/result.png", b"media", container=settings.media_container)
    assert product_url.startswith("https://product-example.oss-cn-hangzhou.aliyuncs.com/")
    assert media_url.startswith("https://course-media-example.oss-cn-hangzhou.aliyuncs.com/")
    assert storage.download("sample_models/男/a.png", container=settings.product_container) == b"product"
    assert storage.exists("tryon-results/result.png", container=settings.media_container)
    assert [item["name"] for item in storage.list("sample_models/", container=settings.product_container)] == ["sample_models/男/a.png"]
    assert storage.delete("tryon-results/result.png", container=settings.media_container)
    assert not storage.delete("tryon-results/result.png", container=settings.media_container)


def test_sample_model_seed_uses_oss_product_bucket():
    from app import database
    session = Mock()
    settings = SimpleNamespace(OBJECT_STORAGE_PROVIDER="oss", OSS_REGION="cn-hangzhou",
                               OSS_PRODUCT_BUCKET="product-example", PUBLIC_IMAGE_BASE_URL="")
    with patch.object(database, "get_settings", return_value=settings):
        database._seed_sample_models(session)
    assert all(call.args[0].gcs_url.startswith("https://product-example.oss-cn-hangzhou.aliyuncs.com/")
               for call in session.add.call_args_list)


def test_old_azure_sample_url_uses_current_oss_bucket(monkeypatch):
    from app.routers.sample_models import _resolve_image_url
    monkeypatch.setattr("app.routers.sample_models.gcs.get_blob_url", lambda name: "https://oss.example/" + name)
    model = SimpleNamespace(gender="男", image_filename="a.webp",
                            gcs_url="https://old.blob.core.windows.net/product-assets/sample_models/男/a.webp")
    assert _resolve_image_url(model) == "https://oss.example/sample_models/男/a.webp"


def test_admin_default_product_url_follows_oss_configuration(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "oss")
    monkeypatch.setenv("OSS_REGION", "cn-hangzhou")
    monkeypatch.setenv("OSS_PRODUCT_BUCKET", "product-example")
    monkeypatch.delenv("PUBLIC_IMAGE_BASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.PUBLIC_IMAGE_BASE_URL == "https://product-example.oss-cn-hangzhou.aliyuncs.com"


def test_admin_product_upload_uses_same_key_as_public_catalog(monkeypatch):
    from app.services import gcs
    settings = _settings()
    client = FakeOSSClient()
    storage = create_object_storage(settings, service_client=client)
    monkeypatch.setattr(gcs, "load_object_storage_settings", lambda: settings)
    monkeypatch.setattr(gcs, "_get_storage", lambda: storage)
    url = gcs.upload_blob("羽绒服_png/new.png", b"image")
    storage.upload("sample_models/male/model.png", b"sample", container=settings.product_container)
    assert url == "https://product-example.oss-cn-hangzhou.aliyuncs.com/new.png"
    assert ("product-example", "new.png") in client.objects
    assert [item["name"] for item in gcs.list_blobs("羽绒服_png/")] == ["羽绒服_png/new.png"]
    assert gcs.get_blob_url("羽绒服_png/new.png") == url
    assert gcs.delete_blob("羽绒服_png/new.png")


def test_admin_can_still_read_and_delete_legacy_prefixed_images(monkeypatch):
    from app.services import gcs
    settings = _settings()
    storage = create_object_storage(settings, service_client=FakeOSSClient())
    storage.upload("羽绒服_png/old.png", b"legacy", container=settings.product_container)
    monkeypatch.setattr(gcs, "load_object_storage_settings", lambda: settings)
    monkeypatch.setattr(gcs, "_get_storage", lambda: storage)
    assert gcs.blob_exists("羽绒服_png/old.png")
    assert gcs.download_blob("羽绒服_png/old.png") == b"legacy"
    assert [item["name"] for item in gcs.list_blobs("羽绒服_png/")] == ["羽绒服_png/old.png"]
    assert gcs.delete_blob("羽绒服_png/old.png")


def test_admin_history_and_workbench_uploads_use_media_bucket(monkeypatch):
    from app.services import gcs
    settings = _settings()
    monkeypatch.setattr(gcs, "load_object_storage_settings", lambda: settings)
    assert gcs._container_for_name("ai-tryon-results/history_index.json") == settings.media_container
    assert gcs._container_for_name("tryon-uploads/photo.png") == settings.media_container
    assert gcs._container_for_name("sample_models/male/model.png") == settings.product_container


def test_azure_and_gcs_product_paths_remain_compatible(monkeypatch):
    from app.services import gcs
    from app.services.object_storage import ObjectStorageSettings, build_public_blob_url

    class Storage:
        def __init__(self, settings):
            self.settings = settings
            self.uploaded = []

        def upload(self, name, data, **kwargs):
            self.uploaded.append(name)
            return build_public_blob_url(self.settings, name, container=kwargs["container"])

    azure = ObjectStorageSettings(provider="azure", account_name="courseassets")
    azure_storage = Storage(azure)
    monkeypatch.setattr(gcs, "load_object_storage_settings", lambda: azure)
    monkeypatch.setattr(gcs, "_get_storage", lambda: azure_storage)
    assert gcs.upload_blob("羽绒服_png/a.png", b"a") == "https://courseassets.blob.core.windows.net/product-assets/a.png"
    assert azure_storage.uploaded == ["a.png"]

    legacy = ObjectStorageSettings(provider="gcs", gcs_bucket="legacy-bucket")
    legacy_storage = Storage(legacy)
    monkeypatch.setattr(gcs, "load_object_storage_settings", lambda: legacy)
    monkeypatch.setattr(gcs, "_get_storage", lambda: legacy_storage)
    gcs.upload_blob("羽绒服_png/a.png", b"a")
    assert legacy_storage.uploaded == ["羽绒服_png/a.png"]

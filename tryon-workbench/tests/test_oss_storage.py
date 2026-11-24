from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.test_fakes.oss import FakeOSSClient
from app.object_storage import create_object_storage, load_object_storage_settings


def test_workbench_oss_upload_and_read_use_media_bucket():
    settings = load_object_storage_settings({
        "OBJECT_STORAGE_PROVIDER": "oss", "OSS_REGION": "cn-hangzhou",
        "OSS_MEDIA_BUCKET": "course-media-example", "OSS_PRODUCT_BUCKET": "product-example",
    })
    client = FakeOSSClient()
    storage = create_object_storage(settings, service_client=client)
    url = storage.upload_bytes("uploads/photo (1).png", b"image", content_type="image/png", cache_control="no-store")
    assert url == "https://course-media-example.oss-cn-hangzhou.aliyuncs.com/uploads/photo%20%281%29.png"
    assert storage.download_bytes("uploads/photo (1).png") == b"image"
    assert storage.exists("uploads/photo (1).png")
    assert [item.name for item in storage.list_objects("uploads/")] == ["uploads/photo (1).png"]
    assert storage.delete("uploads/photo (1).png")


def test_workbench_product_url_prefers_oss_over_stale_azure_config(monkeypatch):
    from app import products
    monkeypatch.setattr(products, "PUBLIC_IMAGE_BASE_URL", "")
    monkeypatch.setattr(products, "AZURE_STORAGE_ACCOUNT_NAME", "oldazure")
    monkeypatch.setattr(products, "OBJECT_STORAGE_PROVIDER", "oss", raising=False)
    monkeypatch.setattr(products, "OSS_REGION", "cn-hangzhou", raising=False)
    monkeypatch.setattr(products, "OSS_PRODUCT_BUCKET", "product-example", raising=False)
    assert products._build_image_url("folder/coat.png") == "https://product-example.oss-cn-hangzhou.aliyuncs.com/coat.png"

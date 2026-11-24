from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.test_fakes.oss import FakeOSSClient


def _uploader():
    path = ROOT / "deploy/aliyun/scripts/upload_product_assets.py"
    assert path.is_file(), "Aliyun product-asset upload helper is missing"
    spec = importlib.util.spec_from_file_location("aliyun_asset_upload", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(tmp_path, names_and_data):
    objects = []
    for name, data in names_and_data:
        (tmp_path / name).write_bytes(data)
        objects.append({"name": name, "sha256": sha256(data).hexdigest(), "mime_type": "image/png"})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"product_count": 4721, "unique_object_count": len(objects), "objects": objects}), encoding="utf-8")
    return path


def test_upload_is_idempotent_and_refuses_to_replace_other_data(tmp_path):
    uploader = _uploader()
    manifest = _manifest(tmp_path, [("a.png", b"image-a"), ("b.png", b"image-b")])
    client = FakeOSSClient()
    assert uploader.upload_manifest(manifest, tmp_path, "product-example", client) == {"uploaded": 2, "existing": 0}
    assert uploader.upload_manifest(manifest, tmp_path, "product-example", client) == {"uploaded": 0, "existing": 2}
    client.metadata[("product-example", "a.png")]["sha256"] = "incorrect"
    with pytest.raises(ValueError, match="hash"):
        uploader.upload_manifest(manifest, tmp_path, "product-example", client)
    assert client.objects[("product-example", "a.png")][0] == b"image-a"


def test_all_local_assets_are_verified_before_any_upload(tmp_path):
    uploader = _uploader()
    manifest = _manifest(tmp_path, [("a.png", b"image-a"), ("b.png", b"image-b")])
    (tmp_path / "b.png").write_bytes(b"tampered")
    client = FakeOSSClient()
    with pytest.raises(ValueError, match="hash"):
        uploader.upload_manifest(manifest, tmp_path, "product-example", client)
    assert client.objects == {}


def test_sample_models_are_uploaded_to_the_names_used_by_admin(tmp_path):
    uploader = _uploader()
    for gender, filenames in {
        "male": ["mannequin-male-1.png", "mannequin-male-2.png"],
        "female": ["mannequin-female-1.png", "mannequin-female-2.png"],
    }.items():
        folder = tmp_path / gender
        folder.mkdir()
        for name in filenames:
            (folder / name).write_bytes(name.encode())
    client = FakeOSSClient()
    assert uploader.upload_sample_models(tmp_path, "product-example", client) == {"uploaded": 4, "existing": 0}
    assert ("product-example", "sample_models/男/mannequin-male-1.png") in client.objects
    assert ("product-example", "sample_models/女/mannequin-female-1.png") in client.objects
    assert uploader.upload_sample_models(tmp_path, "product-example", client) == {"uploaded": 0, "existing": 4}

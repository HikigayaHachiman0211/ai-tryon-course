"""Upload an already-verified product manifest to OSS without overwriting objects."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

import alibabacloud_oss_v2 as oss

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "main-app" / "backend"))
from app.oss_client import OSSClient, _missing_object

_SAMPLE_MODELS = {
    "male": ("男", ("mannequin-male-1.png", "mannequin-male-2.png")),
    "female": ("女", ("mannequin-female-1.png", "mannequin-female-2.png")),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_manifest(manifest_path: Path, stage_dir: Path, bucket: str, client: Any) -> dict[str, int]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    objects = manifest.get("objects")
    if manifest.get("product_count") != 4721 or not isinstance(objects, list) or manifest.get("unique_object_count") != len(objects):
        raise ValueError("Invalid product manifest counts")
    if not bucket:
        raise ValueError("OSS product bucket is required")

    stage = stage_dir.resolve()
    verified = []
    names = set()
    for item in objects:
        name = item.get("name", "")
        expected = str(item.get("sha256", "")).lower()
        if not name or name in {".", ".."} or "/" in name or "\\" in name or name in names:
            raise ValueError("Invalid or duplicate product object name")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Invalid hash for {name}")
        path = (stage / name).resolve()
        if path.parent != stage or not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"Local product hash mismatch: {name}")
        names.add(name)
        verified.append((item, path, expected))

    return _upload_verified(verified, bucket, client)


def _upload_verified(verified: list, bucket: str, client: Any) -> dict[str, int]:
    if not bucket:
        raise ValueError("OSS product bucket is required")
    missing = []
    for item, path, expected in verified:
        try:
            head = client.head_object(oss.HeadObjectRequest(bucket=bucket, key=item["name"]))
        except Exception as exc:
            if _missing_object(exc):
                missing.append((item, path, expected))
                continue
            raise
        if str((head.metadata or {}).get("sha256", "")).lower() != expected:
            raise ValueError(f"Existing OSS product hash mismatch: {item['name']}")

    for item, path, expected in missing:
        with path.open("rb") as source:
            client.put_object(oss.PutObjectRequest(
                bucket=bucket, key=item["name"], body=source, content_length=path.stat().st_size,
                content_type=item.get("mime_type") or "application/octet-stream",
                cache_control="public, max-age=31536000, immutable",
                metadata={"sha256": expected}, forbid_overwrite=True,
            ))
    return {"uploaded": len(missing), "existing": len(verified) - len(missing)}


def upload_sample_models(sample_root: Path, bucket: str, client: Any) -> dict[str, int]:
    verified = []
    for folder, (gender, filenames) in _SAMPLE_MODELS.items():
        for filename in filenames:
            path = sample_root / folder / filename
            if not path.is_file():
                raise ValueError(f"Missing sample model image: {folder}/{filename}")
            item = {"name": f"sample_models/{gender}/{filename}",
                    "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"}
            verified.append((item, path, _sha256(path)))
    return _upload_verified(verified, bucket, client)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--stage-dir", required=True, type=Path)
    parser.add_argument("--bucket", default=os.getenv("OSS_PRODUCT_BUCKET", ""))
    parser.add_argument("--region", default=os.getenv("OSS_REGION", ""))
    parser.add_argument("--endpoint", default=os.getenv("OSS_ENDPOINT", ""))
    parser.add_argument("--sample-models-dir", type=Path, default=ROOT / "main-app/frontend/public/sample-models")
    parser.add_argument("--skip-sample-models", action="store_true")
    args = parser.parse_args()
    client = OSSClient(args.region, args.endpoint)._client()
    result = {"products": upload_manifest(args.manifest, args.stage_dir, args.bucket, client)}
    if not args.skip_sample_models:
        result["sample_models"] = upload_sample_models(args.sample_models_dir, args.bucket, client)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

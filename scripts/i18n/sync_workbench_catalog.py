"""Build the workbench catalog from the main service read model.

The workbench image is intentionally self-contained. This script is the only
supported bridge for copying the canonical product/read-model artifact and its
validated locale assets into that image context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

GENERATOR_VERSION = "workbench-catalog-i18n-v1"
LOCALES = ["zh-CN", "en", "ja"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paths(repo_root: Path) -> tuple[Path, Path, Path, Path]:
    app_root = repo_root / "main-app"
    source = app_root / "backend" / "read-model" / "catalog.json"
    en = app_root / "backend" / "app" / "i18n" / "catalog-translations" / "en.json"
    ja = app_root / "backend" / "app" / "i18n" / "catalog-translations" / "ja.json"
    out = repo_root / "tryon-workbench" / "read-model"
    return source, en, ja, out


def build(repo_root: Path) -> tuple[Path, Path]:
    source, en_path, ja_path, out_dir = paths(repo_root)
    for required in (source, en_path, ja_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    read_model = json.loads(source.read_text(encoding="utf-8"))
    translations = {
        "en": json.loads(en_path.read_text(encoding="utf-8")).get("items", {}),
        "ja": json.loads(ja_path.read_text(encoding="utf-8")).get("items", {}),
    }
    source_items = read_model.get("items", [])
    if not source_items or read_model.get("product_count") != len(source_items):
        raise RuntimeError("main read-model product count does not match its catalog")
    translation_keys = {locale: set(translations[locale]) for locale in ("en", "ja")}
    expected_keys = {str(item["product_key"]) for item in source_items}
    for locale, keys in translation_keys.items():
        if keys != expected_keys:
            raise RuntimeError(f"{locale} translation keys do not match the main read model")

    items = []
    for item in source_items:
        key = str(item["product_key"])
        display = dict(item.get("display") or {})
        for locale in ("en", "ja"):
            asset = translations[locale][key]
            display[locale] = {
                "title": asset.get("title", ""),
                "styleType": asset.get("styleType", asset.get("style_type", "")),
                "colorFamily": asset.get("colorFamily", asset.get("color_family", "")),
                "bodyFit": asset.get("bodyFit", asset.get("body_fit", "")),
                "styleFeatures": asset.get("styleFeatures", asset.get("style_features", [])),
                "functionFeatures": asset.get("functionFeatures", asset.get("function_features", [])),
                "sizeNotes": asset.get("sizeNotes", asset.get("size_notes", "")),
            }
        items.append({
            "id": item.get("id"),
            "product_key": key,
            "price": item.get("price"),
            "image_path": item.get("image_path", ""),
            "product_url": item.get("product_url"),
            "canonical": item.get("canonical", {}),
            "display": display,
            "search_text": item.get("search_text", ""),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "catalog.i18n.json"
    manifest = out_dir / "catalog.i18n.manifest.json"
    artifact.write_text(json.dumps({
        "kind": "workbench-catalog-i18n",
        "version": 1,
        "generator": GENERATOR_VERSION,
        "locales": LOCALES,
        "product_count": len(items),
        "source_sha256": sha256(source),
        "translation_asset_sha256": {"en": sha256(en_path), "ja": sha256(ja_path)},
        "items": items,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    manifest.write_text(json.dumps({
        "generator": GENERATOR_VERSION,
        "source_sha256": sha256(source),
        "translation_asset_sha256": {"en": sha256(en_path), "ja": sha256(ja_path)},
        "record_count": len(items),
        "locales": LOCALES,
        "artifact_sha256": sha256(artifact),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact, manifest


def verify(repo_root: Path) -> None:
    source, en_path, ja_path, out_dir = paths(repo_root)
    manifest_path = out_dir / "catalog.i18n.manifest.json"
    artifact_path = out_dir / "catalog.i18n.json"
    if not manifest_path.is_file() or not artifact_path.is_file():
        raise RuntimeError("workbench catalog read model is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    read_model = json.loads(source.read_text(encoding="utf-8"))
    expected = {
        "generator": GENERATOR_VERSION,
        "source_sha256": sha256(source),
        "translation_asset_sha256": {"en": sha256(en_path), "ja": sha256(ja_path)},
        "record_count": read_model["product_count"],
        "locales": LOCALES,
        "artifact_sha256": sha256(artifact_path),
    }
    if manifest != expected:
        raise RuntimeError("workbench catalog manifest differs from current main artifacts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    if args.verify:
        verify(repo_root)
        print("[workbench-catalog] PASS")
    else:
        artifact, manifest = build(repo_root)
        print(f"[workbench-catalog] wrote {artifact} and {manifest}")


if __name__ == "__main__":
    main()

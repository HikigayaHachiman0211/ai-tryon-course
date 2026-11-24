from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import shutil
from collections import defaultdict
from pathlib import Path


EXPECTED_PRODUCT_COUNT = 4721


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_source(root: Path, reference: str) -> Path | None:
    normalized = str(reference or "").replace("\\", "/").lstrip("/")
    app_root = root / "main-app"
    taobao_roots = sorted(root.glob("img羽绒服*"), key=lambda item: item.name, reverse=True)
    candidates = [root / normalized, app_root / normalized]
    if normalized.startswith("downloaded_jd_images/"):
        candidates.append(app_root / normalized)
        candidates.append(app_root / "downloaded_jd_images" / "羽绒服_png" / Path(normalized).name)
    if normalized.startswith("img羽绒服"):
        candidates.append(root / normalized)
        candidates.extend(item / Path(normalized).name for item in taobao_roots)
    candidates.extend(
        [
            app_root / "downloaded_jd_images" / "羽绒服_png" / Path(normalized).name,
            *(item / Path(normalized).name for item in taobao_roots),
        ]
    )
    allowed_roots = [
        (app_root / "downloaded_jd_images").resolve(),
        *(item.resolve() for item in taobao_roots),
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file() or resolved.stat().st_size <= 0:
            continue
        if any(resolved == allowed or allowed in resolved.parents for allowed in allowed_roots):
            return resolved
    return None


def load_catalog(root: Path) -> list[dict]:
    path = root / "main-app" / "database.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != EXPECTED_PRODUCT_COUNT:
        raise SystemExit(f"database.json must contain exactly {EXPECTED_PRODUCT_COUNT} rows; got {len(rows) if isinstance(rows, list) else 'non-list'}")
    return rows


def verify_read_model(root: Path, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if payload.get("product_count") != EXPECTED_PRODUCT_COUNT or not isinstance(items, list) or len(items) != EXPECTED_PRODUCT_COUNT:
        raise SystemExit(f"read model contract failed: {path}")


def build_manifest(root: Path, stage_dir: Path | None = None) -> dict:
    rows = load_catalog(root)
    database_path = root / "main-app" / "database.json"
    references: list[dict] = []
    sources_by_name: defaultdict[str, list[dict]] = defaultdict(list)
    for index, row in enumerate(rows):
        reference = str(row.get("图片路径") or "").strip()
        if not reference:
            raise SystemExit(f"empty image reference at catalog row {index}")
        source = resolve_source(root, reference)
        if source is None:
            raise SystemExit(f"missing or empty catalog image at row {index}: {reference}")
        digest = sha256_file(source)
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        item = {
            "catalog_row": index,
            "product_id": row.get("id") or index + 1,
            "image_reference": reference,
            "object_name": source.name,
            "source_path": str(source.relative_to(root)).replace("\\", "/"),
            "size": source.stat().st_size,
            "mime_type": mime_type,
            "sha256": digest,
        }
        references.append(item)
        sources_by_name[source.name].append(item)

    conflicts = {
        name: sorted({entry["sha256"] for entry in entries})
        for name, entries in sources_by_name.items()
        if len({entry["sha256"] for entry in entries}) > 1
    }
    if conflicts:
        details = []
        for name in sorted(conflicts):
            details.append(
                {
                    "object_name": name,
                    "sources": [
                        {"catalog_row": entry["catalog_row"], "product_id": entry["product_id"], "source_path": entry["source_path"], "sha256": entry["sha256"]}
                        for entry in sources_by_name[name]
                    ],
                }
            )
        raise SystemExit("duplicate image basenames with different content:\n" + json.dumps(details, ensure_ascii=False, indent=2))

    objects: list[dict] = []
    seen: set[str] = set()
    for name in sorted(sources_by_name):
        first = sources_by_name[name][0]
        source = root / first["source_path"]
        objects.append(
            {
                "name": name,
                "source_path": first["source_path"],
                "size": source.stat().st_size,
                "mime_type": first["mime_type"],
                "sha256": first["sha256"],
            }
        )
        if stage_dir is not None:
            stage_dir.mkdir(parents=True, exist_ok=True)
            destination = stage_dir / name
            if destination.exists() and sha256_file(destination) != first["sha256"]:
                raise SystemExit(f"staging destination collision with different content: {destination}")
            if not destination.exists():
                shutil.copyfile(source, destination)
        seen.add(name)

    main_read_model = root / "main-app/backend/read-model/catalog.json"
    workbench_read_model = root / "tryon-workbench/read-model/catalog.i18n.json"
    verify_read_model(root, main_read_model)
    verify_read_model(root, workbench_read_model)
    return {
        "dataset_version": "course-catalog-v4-4721",
        "product_count": len(rows),
        "unique_image_references": len({entry["image_reference"] for entry in references}),
        "unique_object_count": len(objects),
        "database_sha256": sha256_file(database_path),
        "references": references,
        "objects": objects,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stage-dir", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(args.root.resolve(), args.stage_dir.resolve() if args.stage_dir else None)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("dataset_version", "product_count", "unique_image_references", "unique_object_count", "database_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from catalog_assets import EXPECTED_PRODUCT_COUNT, sha256_file


EXCLUDE_DIRS = {
    ".git", ".vs", ".pytest_cache", "__pycache__", "node_modules", "dist", "build",
    "coverage", ".vite", ".mypy_cache", ".ruff_cache", ".venv", "venv", "uploads",
    "history", "assets", "downloaded_jd_images", "releases", "product-assets-staging",
}
EXCLUDE_NAMES = {".env", ".env.azure.test", "main.parameters.json", "admin_local.db", "local.db", "ai_studio_config.json"}


def excluded_directory(name: str) -> bool:
    lower = name.lower()
    return (lower in EXCLUDE_DIRS or lower.startswith(".venv-") or
            lower in {".aws", ".azure", ".ssh", "secrets"} or lower.startswith((".secrets", "secrets.")) or
            bool(re.search(r"credentials?|service[-_]?account|private[-_]?key", lower)))


def excluded_file(name: str) -> bool:
    lower = name.lower()
    if lower.startswith(".env.") and lower.endswith(".example"):
        return False
    if lower in EXCLUDE_NAMES or (lower.startswith(".env.") and not lower.endswith(".example")):
        return True
    if lower.startswith(("secrets.", ".secrets")) or ("secret" in lower and lower.endswith((".json", ".env"))):
        return True
    if re.search(r"\.(?:db|db3|sqlite|sqlite2|sqlite3|mdb|accdb)(?:-(?:wal|shm|journal))?$", lower):
        return True
    suffix = Path(lower).suffix
    if suffix in {".pem", ".key", ".p12", ".pfx", ".p8", ".jks", ".keystore"}:
        return True
    if re.search(r"(?:credentials?|service[-_]?account|private[-_]?key|id_rsa|id_ed25519)", lower):
        return True
    return False


def git_value(root: Path, args: list[str], default: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
        return result.stdout.strip() or default
    except (OSError, subprocess.CalledProcessError):
        return default


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"required source directory is missing: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for current, directory_names, file_names in os.walk(source):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        directory_names[:] = sorted(
            name for name in directory_names
            if not excluded_directory(name) and not (current_path / name).is_symlink()
        )
        target_dir = destination / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for file_name in sorted(file_names):
            if excluded_file(file_name) or (current_path / file_name).is_symlink():
                continue
            source_path = current_path / file_name
            shutil.copy2(source_path, target_dir / file_name)


def copy_file(root: Path, release: Path, relative: str) -> None:
    source = root / relative
    if not source.is_file():
        raise SystemExit(f"required release file is missing: {relative}")
    destination = release / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def populate_release(root: Path, release: Path) -> None:
    app_root = "main-app"
    copy_tree(root / app_root / "backend", release / app_root / "backend")
    copy_tree(root / app_root / "frontend", release / app_root / "frontend")
    copy_tree(root / app_root / "admin", release / app_root / "admin")
    copy_tree(root / "tryon-workbench", release / "tryon-workbench")
    copy_tree(root / "scripts", release / "scripts")
    copy_tree(root / "deploy", release / "deploy")
    for relative in (
        f"{app_root}/Dockerfile",
        f"{app_root}/database.json",
        f"{app_root}/.dockerignore",
        "tryon-workbench/Dockerfile",
        "tryon-workbench/.dockerignore",
        "PROJECT_OVERVIEW.md",
        "README.md",
        "CHANGELOG.md",
    ):
        copy_file(root, release, relative)


def validate_release(release: Path) -> None:
    for path in release.rglob("*"):
        excluded_dir = path.is_dir() and excluded_directory(path.name)
        if path.is_symlink() or excluded_dir or (path.is_file() and excluded_file(path.name)):
            raise SystemExit(f"release contains an excluded file: {path.relative_to(release)}")
    database = json.loads((release / "main-app/database.json").read_text(encoding="utf-8"))
    if not isinstance(database, list) or len(database) != EXPECTED_PRODUCT_COUNT:
        raise SystemExit("clean release database count is not 4,721")
    required = (
        "main-app/backend/read-model/catalog.json",
        "tryon-workbench/read-model/catalog.i18n.json",
        "main-app/backend/app/i18n/catalog-translations/en.json",
        "main-app/backend/app/i18n/catalog-translations/ja.json",
        "main-app/admin/backend/app/db_init_job.py",
        "tryon-workbench/Dockerfile.worker",
        "tryon-workbench/app/queue_worker.py",
        "tryon-workbench/app/task_db.py",
        "tryon-workbench/app/task_queue.py",
        "tryon-workbench/app/video_config.py",
        "tryon-workbench/app/video_gateway.py",
        "tryon-workbench/app/video_routes.py",
        "tryon-workbench/app/video_tasks.py",
        "tryon-workbench/static/css/video.css",
        "tryon-workbench/static/js/video.js",
        "tryon-workbench/static/js/video-form.js",
        "main-app/admin/backend/app/routers/video_config.py",
        "main-app/admin/frontend/src/pages/VideoSettingsTab.tsx",
        "deploy/azure/compose.yaml",
        "deploy/azure/aca/main.bicep",
        "deploy/azure/aca/main.parameters.example.json",
        "deploy/azure/aca/.env.aca.example",
        "deploy/azure/scripts/deploy-aca.ps1",
        "deploy/azure/scripts/smoke-test-aca.ps1",
        "deploy/aliyun/compose.yaml",
        "deploy/aliyun/Caddyfile",
        "deploy/aliyun/.env.aliyun.example",
        "deploy/aliyun/scripts/upload_product_assets.py",
        "deploy/azure/scripts/upload-sample-models.ps1",
        "main-app/backend/app/oss_client.py",
        "main-app/admin/backend/app/services/oss_client.py",
        "tryon-workbench/app/oss_client.py",
    )
    for relative in required:
        if not (release / relative).is_file():
            raise SystemExit(f"clean release artifact missing: {relative}")
    contexts = {
        "main": release / "main-app",
        "admin": release / "main-app",
        "workbench": release / "tryon-workbench",
    }
    for name, context in contexts.items():
        if not context.is_dir():
            raise SystemExit(f"Docker build context missing from clean release: {name}")


def archive_directory(source: Path, archive_path: Path) -> str:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                relative_name = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(relative_name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    return sha256_file(archive_path)


def write_checksums(release: Path) -> None:
    lines = []
    for path in sorted(release.rglob("*")):
        if path.is_file() and path.name not in {"SHA256SUMS"}:
            lines.append(f"{sha256_file(path)}  {path.relative_to(release).as_posix()}")
    (release / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--release-id")
    args = parser.parse_args()
    root = args.root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ai-tryon-release-") as temp_name:
        source_dir = Path(temp_name) / "source"
        source_dir.mkdir()
        populate_release(root, source_dir)
        validate_release(source_dir)
        source_archive = Path(temp_name) / "source.zip"
        source_sha = archive_directory(source_dir, source_archive)

    commit = git_value(root, ["rev-parse", "--short=12", "HEAD"], "nogit")
    dirty = bool(git_value(root, ["status", "--porcelain"], ""))
    release_id = args.release_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{commit}-{source_sha[:12]}{'-dirty' if dirty else ''}"
    release = output_root / release_id
    if release.exists():
        raise SystemExit(f"release directory already exists; refusing overwrite: {release}")
    release.mkdir(parents=True)
    populate_release(root, release)
    validate_release(release)
    manifest = {
        "release_id": release_id,
        "source_archive_sha256": source_sha,
        "git_commit": commit,
        "source_dirty": dirty,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_product_count": EXPECTED_PRODUCT_COUNT,
        "excluded": [".env* real values", "private keys", "credentials", "node_modules", "user media", "local databases"],
    }
    (release / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_checksums(release)
    archive_path = output_root / f"{release_id}.zip"
    archive_sha = archive_directory(release, archive_path)
    with tempfile.TemporaryDirectory(prefix="ai-tryon-clean-room-") as clean_name:
        clean = Path(clean_name)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(clean)
        validate_release(clean)
    print(json.dumps({"release_id": release_id, "release_directory": str(release), "archive": str(archive_path), "archive_sha256": archive_sha, "source_archive_sha256": source_sha}))


if __name__ == "__main__":
    main()

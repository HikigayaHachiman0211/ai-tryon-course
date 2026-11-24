import importlib.util
import sys
from pathlib import Path

import pytest
RELEASE_DIR = Path(__file__).resolve().parents[1] / "release"
sys.path.insert(0, str(RELEASE_DIR))
spec = importlib.util.spec_from_file_location("release_builder_test", RELEASE_DIR / "build_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_copy_excludes_sensitive_synthetic_files(tmp_path):
    source, dest = tmp_path / "source", tmp_path / "release"
    (source / "nested").mkdir(parents=True)
    excluded = ["gcp-Credentials.JSON", "service-account.json", "private.PEM", "client.KEY", "cert.P12",
                "other.sqlite", "OTHER.DB-WAL", "local.sqlite3-shm", "temp.db-journal", ".ENV.production", "credentials.json.example",
                "ai_studio_config.json", "session-secret.JSON", ".secrets.prod", "secrets.txt"]
    kept = ["main.py", "package-lock.json", "database.json", ".env.example", ".env.credentials.example", "translations.json"]
    for name in excluded + kept:
        (source / "nested" / name).write_text("synthetic", encoding="utf-8")
    (source / "nested" / "Credentials").mkdir()
    (source / "nested" / "Credentials" / "config.json").write_text("synthetic", encoding="utf-8")
    release.copy_tree(source, dest)
    assert {path.name for path in (dest / "nested").iterdir()} == set(kept)
    (dest / "nested" / "secret.pem").write_text("synthetic", encoding="utf-8")
    with pytest.raises(SystemExit, match="excluded file"):
        release.validate_release(dest)

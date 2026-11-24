import json
import time
from concurrent.futures import ThreadPoolExecutor

from app import history


def configure(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "LOCAL_HISTORY_DIR", tmp_path)
    monkeypatch.setattr(history, "LOCAL_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(history, "LOCAL_THUMBS_DIR", tmp_path / "thumbnails")
    monkeypatch.setattr(history, "LOCAL_INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(history.gcs_storage, "save_result_json", lambda *_: True)
    monkeypatch.setattr(history.gcs_storage, "save_history_index", lambda *_: True)
    monkeypatch.setattr(history.gcs_storage, "load_history_index", lambda: None)


def test_concurrent_history_saves_preserve_entries_and_truncate(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    original_read = history._read_local_index
    def slow_read():
        result = original_read()
        time.sleep(0.01)
        return result
    monkeypatch.setattr(history, "_read_local_index", slow_read)
    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(lambda _: history.save_history({"items": []}, "recommend"), range(12)))
    saved = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert {entry["id"] for entry in entries} == {entry["id"] for entry in saved}
    monkeypatch.setattr(history, "MAX_HISTORY_ENTRIES", 5)
    history.save_history({"items": []}, "recommend")
    assert len(json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))) == 5


def test_history_identifiers_cannot_escape_or_trigger_remote_lookup(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    history._ensure_local_dirs()
    (tmp_path / "results" / "legacy-1_abc.json").write_text('{"ok": true}', encoding="utf-8")
    assert history.get_history_detail("legacy-1_abc") == {"ok": True}
    calls = []
    monkeypatch.setattr(history.gcs_storage, "get_result_json", lambda key: calls.append(key))
    for key in ("../secret", "..\\secret", "/secret", "C:\\secret", "%2e%2e%2fsecret", "a%5cb"):
        assert history.get_history_detail(key) is None
        assert history.get_thumbnail_path(key) is None
    assert not calls
    assert history.get_history_detail("missing-legacy") is None
    assert calls == ["missing-legacy"]

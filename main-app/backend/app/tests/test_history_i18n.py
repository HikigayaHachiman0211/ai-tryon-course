from __future__ import annotations

import json
from pathlib import Path

from app import history
from app.history import list_history, localize_history_result, save_history
from app.i18n.catalog import product_key_from_row


def _recommendation_payload() -> dict:
    row = {"商品标题": "测试黑色羽绒服", "价格": 399, "图片路径": "test/history.png"}
    key = product_key_from_row(row)
    return {
        "locale": "zh-CN",
        "filters": {},
        "inference": {
            "resolved_size": "M",
            "resolved_style": "短款",
            "body_shape": "标准",
            "reasoning": "中文历史摘要",
        },
        "items": [{
            "id": 7,
            "product_key": key,
            "title": row["商品标题"],
            "price": 399,
            "image_url": "/static/products/test/history.png",
            "style_type": "短款",
            "color_family": "黑色",
            "body_fit": "常规版型，适合大多数标准身材",
            "style_features": ["简约"],
            "function_features": ["保暖"],
            "size_tags": ["M"],
            "size_notes": "建议参考尺码表",
            "total_score": 91.2,
            "score_breakdown": {"颜色适配度": 90},
            "radar_chart": [{"code": "color", "dimension": "颜色适配度", "score": 90}],
            "reason": "中文推荐理由",
        }],
    }


def test_history_is_localized_at_read_time_without_chinese_presentation(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(history, "LOCAL_HISTORY_DIR", tmp_path)
    monkeypatch.setattr(history, "LOCAL_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(history, "LOCAL_THUMBS_DIR", tmp_path / "thumbnails")
    monkeypatch.setattr(history, "LOCAL_INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(history.gcs_storage, "save_result_json", lambda *args, **kwargs: True)
    monkeypatch.setattr(history.gcs_storage, "save_history_index", lambda *args, **kwargs: True)
    monkeypatch.setattr(history.gcs_storage, "load_history_index", lambda: None)

    result = _recommendation_payload()
    entry = save_history(result, "recommend")
    assert entry["created_locale"] == "zh-CN"
    assert entry["summary_params"]["product_key"]

    localized_entries = list_history(locale="en")
    assert localized_entries[0]["locale"] == "en"
    assert "推荐" not in localized_entries[0]["summary"]
    assert "中文" not in localized_entries[0]["summary"]

    detail = json.loads((tmp_path / "results" / f"{entry['id']}.json").read_text(encoding="utf-8"))
    localized = localize_history_result(detail, "en")
    assert localized["locale"] == "en"
    assert "测试" not in localized["items"][0]["display"]["title"]
    assert "中文" not in localized["items"][0]["reason"]

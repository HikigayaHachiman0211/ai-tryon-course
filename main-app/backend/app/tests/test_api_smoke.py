"""Smoke tests for the main FastAPI application endpoints.

All tests use the `client` fixture from conftest.py which mocks out:
  - catalog read model (3 stub products, no DB seeding)
  - GCS / history loading on startup
  - AI provider calls (per-test where needed)

No real credentials, cloud services, or external network required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/products
# ---------------------------------------------------------------------------

def test_get_products_returns_list(client):
    resp = client.get("/api/products")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) > 0


def test_get_products_gender_filter(client):
    resp = client.get("/api/products", params={"gender": "female", "limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


def test_get_products_price_filter(client):
    resp = client.get("/api/products", params={"price_min": 100, "price_max": 500})
    assert resp.status_code == 200
    assert "items" in resp.json()


# ---------------------------------------------------------------------------
# /api/recommend  — deterministic path (AI provider mocked out)
# ---------------------------------------------------------------------------

_STUB_RECOMMEND_RESULT = {
    "filters": {
        "price_min": None,
        "price_max": None,
        "catalog_total": 3,
        "matched_after_price_filter": 3,
        "matched_after_gender_filter": 3,
        "user_gender": "female",
        "brand_preference": None,
        "gender_fallback": False,
    },
    "inference": {
        "body_shape": "标准型",
        "resolved_size": "M",
        "resolved_style": "短款",
        "reasoning": "规则推断",
        "gemini_used": False,
    },
    "items": [
        {
            "id": 1,
            "title": "测试羽绒服 1",
            "price": 350.0,
            "image_url": "/static/products/test/product_1.jpg",
            "product_url": None,
            "style_type": "短款",
            "color_family": "黑色",
            "body_fit": "修身",
            "size_tags": ["M", "L", "XL"],
            "score": 85,
            "reasons": ["颜色匹配"],
        }
    ],
    "message": "为你找到 1 件推荐商品。",
}


def test_recommend_deterministic_fallback(client):
    """POST /api/recommend with no photo and no AI key → deterministic path."""
    with patch("app.main.recommend_products", return_value=_STUB_RECOMMEND_RESULT):
        resp = client.post(
            "/api/recommend",
            data={
                "color_preference": "黑色",
                "gender": "female",
                "size": "M",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "inference" in data


def test_recommend_price_validation_error(client):
    """price_min > price_max should return 400."""
    resp = client.post(
        "/api/recommend",
        data={
            "color_preference": "黑色",
            "price_min": "800",
            "price_max": "200",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "REC-001"


def test_recommend_missing_required_field(client):
    """color_preference is required; omitting it should return 422."""
    resp = client.post("/api/recommend", data={"gender": "female"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/assistant/config/public
# ---------------------------------------------------------------------------

def test_assistant_config_public(client):
    resp = client.get("/api/assistant/config/public")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "welcome_message" in data
    assert "features" in data


# ---------------------------------------------------------------------------
# /api/assistant/chat  — rule-fallback path (LLM mocked to return None)
# ---------------------------------------------------------------------------

def test_assistant_chat_recommend_intent_rule_fallback(client):
    """Message with recommendation keywords → rule fallback → recommend intent."""
    with patch("app.assistant.orchestrator.try_llm_enhance", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/assistant/chat",
            json={
                "session_id": "test-1",
                "message": "我想要黑色的女款羽绒服，预算500以内",
                "page_context": {"view": "recommend", "current_form": {}},
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "recommend"
    assert data["reply"]
    assert data["debug"]["fallback_used"] is True


def test_assistant_chat_tryon_intent_rule_fallback(client):
    # "试穿" triggers tryon; avoid "羽绒服" which is also a recommend keyword
    with patch("app.assistant.orchestrator.try_llm_enhance", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/assistant/chat",
            json={"message": "我要去试穿", "page_context": {}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "tryon"
    assert "试穿" in data["reply"]


def test_assistant_chat_empty_message(client):
    with patch("app.assistant.orchestrator.try_llm_enhance", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/assistant/chat",
            json={"message": "", "page_context": {}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "unknown"
    assert data["reply"]


def test_assistant_chat_unknown_intent_rule_fallback(client):
    with patch("app.assistant.orchestrator.try_llm_enhance", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/assistant/chat",
            json={"message": "blahblah xyz123", "page_context": {}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"]


# ---------------------------------------------------------------------------
# /api/assistant/knowledge/search
# ---------------------------------------------------------------------------

def test_knowledge_search_returns_results(client):
    resp = client.get("/api/assistant/knowledge/search", params={"q": "尺码", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data

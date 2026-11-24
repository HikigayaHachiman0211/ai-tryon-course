"""Shared pytest fixtures for the backend test suite."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal stub products returned by the mocked catalog so the lifespan
# skips database seeding and the /api/products / /api/recommend endpoints
# have something to work with.
# ---------------------------------------------------------------------------

def _make_stub_product(pid: int) -> "Product":  # type: ignore[name-defined]
    from app.database import Product
    return Product(
        id=pid,
        title=f"测试羽绒服 {pid}",
        price=300.0 + pid * 50,
        image_path=f"test/product_{pid}.jpg",
        style_type="短款",
        color_family="黑色",
        body_fit="修身",
        style_features=["连帽"],
        function_features=["防风"],
        size_tags=["M", "L", "XL"],
        size_notes=None,
        product_url=None,
    )


_STUB_PRODUCTS = None


@pytest.fixture(autouse=True)
def _ensure_main_event_loop():
    """Keep legacy synchronous async-test helpers isolated between tests.

    A few characterization tests still call ``get_event_loop().run_until_complete``
    while other tests use ``asyncio.run``.  ``asyncio.run`` clears the policy's
    current loop when it returns, so the next legacy helper would otherwise fail
    before it ever exercises application code.  Recreate the loop at each test
    boundary without replacing an existing pytest-managed loop.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


def _get_stub_products():
    global _STUB_PRODUCTS
    if _STUB_PRODUCTS is None:
        _STUB_PRODUCTS = [_make_stub_product(i) for i in range(1, 4)]
    return _STUB_PRODUCTS


@pytest.fixture()
def client(tmp_path):
    """FastAPI TestClient with all external startup side-effects mocked out.

    Mocked:
    - catalog_repository.get_catalog_products  → returns 3 stub Products
      (so lifespan never calls ensure_database or touches SQLite/Cloud SQL)
    - gcs_storage.load_history_index           → returns [] (no GCS call)
    - history paths                            → isolated temporary directory
    - history storage and thumbnail downloads  → no external requests
    """
    with (
        patch("app.catalog_repository.get_catalog_products", return_value=_get_stub_products()),
        patch("app.main.get_catalog_products", return_value=_get_stub_products()),
        patch("app.gcs_storage.load_history_index", return_value=[]),
        patch("app.gcs_storage.save_result_json", return_value=None),
        patch("app.gcs_storage.save_history_index", return_value=None),
        patch("app.history._download_image_bytes", return_value=None),
        patch("app.history.LOCAL_HISTORY_DIR", tmp_path),
        patch("app.history.LOCAL_RESULTS_DIR", tmp_path / "results"),
        patch("app.history.LOCAL_THUMBS_DIR", tmp_path / "thumbnails"),
        patch("app.history.LOCAL_INDEX_PATH", tmp_path / "index.json"),
    ):
        from app.main import app
        with TestClient(app) as c:
            yield c

"""Shared pytest fixtures for the backend test suite."""
from __future__ import annotations

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


def _get_stub_products():
    global _STUB_PRODUCTS
    if _STUB_PRODUCTS is None:
        _STUB_PRODUCTS = [_make_stub_product(i) for i in range(1, 4)]
    return _STUB_PRODUCTS


@pytest.fixture()
def client():
    """FastAPI TestClient with all external startup side-effects mocked out.

    Mocked:
    - catalog_repository.get_catalog_products  → returns 3 stub Products
      (so lifespan never calls ensure_database or touches SQLite/Cloud SQL)
    - gcs_storage.load_history_index           → returns [] (no GCS call)
    - history._read_local_index                → returns [] (no filesystem history)
    - history._ensure_local_dirs               → no-op
    """
    with (
        patch("app.catalog_repository.get_catalog_products", return_value=_get_stub_products()),
        patch("app.gcs_storage.load_history_index", return_value=[]),
        patch("app.history._read_local_index", return_value=[]),
        patch("app.history._ensure_local_dirs", return_value=None),
    ):
        from app.main import app
        with TestClient(app) as c:
            yield c

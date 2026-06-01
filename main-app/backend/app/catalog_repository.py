from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.database import Product, build_product, load_seed_rows, resolve_database_json_path

logger = logging.getLogger(__name__)

CATALOG_READ_MODEL_PATH_ENV = "CATALOG_READ_MODEL_PATH"

_catalog_products: list[Product] | None = None
_catalog_products_by_id: dict[int, Product] | None = None
_catalog_source_label: str | None = None
_catalog_load_failed = False


def _resolve_catalog_read_model_path() -> Path | None:
    raw_path = os.getenv(CATALOG_READ_MODEL_PATH_ENV, "").strip()
    if not raw_path:
        return None
    return Path(raw_path)


def _load_catalog_rows() -> tuple[list[dict], str]:
    catalog_path = _resolve_catalog_read_model_path()
    if catalog_path is None:
        catalog_path = resolve_database_json_path()
    return load_seed_rows(catalog_path), catalog_path.as_posix()


def _build_catalog_products_from_read_model(items: list[dict[str, Any]]) -> list[Product]:
    products: list[Product] = []
    for fallback_id, item in enumerate(items, start=1):
        product = Product(
            id=int(item.get("id") or fallback_id),
            title=str(item["title"]).strip(),
            price=float(item["price"]),
            image_path=str(item["image_path"]).replace("\\", "/"),
            style_type=str(item["style_type"]),
            color_family=str(item["color_family"]),
            body_fit=str(item["body_fit"]),
            style_features=list(item.get("style_features") or []),
            function_features=list(item.get("function_features") or []),
            size_tags=list(item.get("size_tags") or []),
            size_notes=item.get("size_notes"),
            product_url=item.get("product_url"),
        )
        products.append(product)
    return products


def _build_catalog_products(rows: list[dict]) -> list[Product]:
    products: list[Product] = []
    for product_id, row in enumerate(rows, start=1):
        product = build_product(row)
        product.id = product_id
        products.append(product)
    return products


def _load_catalog_products() -> tuple[list[Product], str]:
    catalog_path = _resolve_catalog_read_model_path()
    if catalog_path is not None and catalog_path.suffix.lower() == ".json" and catalog_path.exists():
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return _build_catalog_products_from_read_model(payload["items"]), f"{catalog_path.as_posix()}#read-model"

    rows, source_label = _load_catalog_rows()
    return _build_catalog_products(rows), source_label


def get_catalog_products() -> list[Product] | None:
    global _catalog_products, _catalog_products_by_id, _catalog_source_label, _catalog_load_failed  # noqa: PLW0603

    if _catalog_products is not None:
        return _catalog_products
    if _catalog_load_failed:
        return None

    try:
        products, source_label = _load_catalog_products()
    except Exception as exc:
        _catalog_load_failed = True
        logger.warning("Catalog read model load failed; product reads will fall back to database: %s", exc)
        return None

    _catalog_products = products
    _catalog_products_by_id = {product.id: product for product in products}
    _catalog_source_label = source_label
    logger.info("Loaded %d catalog read-model products from %s", len(products), source_label)
    return _catalog_products


def get_catalog_product(product_id: int) -> Product | None:
    products = get_catalog_products()
    if not products or _catalog_products_by_id is None:
        return None
    return _catalog_products_by_id.get(product_id)


def get_catalog_source_label() -> str | None:
    if _catalog_products is None and not _catalog_load_failed:
        get_catalog_products()
    return _catalog_source_label
"""Standalone reentrant DB migration and initial seed job for Azure Container Apps Jobs."""

from __future__ import annotations

import json
import sys
from typing import Any

from app.database import (
    AIAPIProvider,
    AnnotationTask,
    Product,
    PromptConfig,
    SampleModel,
    _backfill_product_metadata,
    get_session_factory,
    init_db,
)


def run_db_init_job() -> dict[str, Any]:
    """Execute idempotent DB schema creation, seeding, and backfill under DB lock."""
    init_db(seed=True)
    factory = get_session_factory()
    with factory() as session:
        backfilled = _backfill_product_metadata(session)
        summary = {
            "ok": True,
            "products": session.query(Product).count(),
            "products_with_url": session.query(Product).filter(Product.product_url.isnot(None)).count(),
            "annotation_tasks": session.query(AnnotationTask).count(),
            "prompt_configs": session.query(PromptConfig).count(),
            "sample_models": session.query(SampleModel).count(),
            "ai_api_providers": session.query(AIAPIProvider).count(),
            "backfilled_products": backfilled,
        }
    return summary


def main() -> int:
    summary = run_db_init_job()
    print(json.dumps(summary, ensure_ascii=False))
    if summary["products"] <= 0:
        print("[db_init_job] ERROR: products table is still empty after init_db", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

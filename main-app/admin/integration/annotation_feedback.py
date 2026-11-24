"""
Annotation feedback integration.
Call when user interactions suggest annotation correctness.

Usage:
    from admin.integration.annotation_feedback import record_feedback
    record_feedback(product_id, "color_family", "positive")
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def record_feedback(product_id: int, field_name: str, feedback_type: str = "positive") -> bool:
    """Record implicit feedback about annotation quality.
    feedback_type: 'positive' (user accepted), 'negative' (user rejected/changed)
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return False
    try:
        engine = create_engine(url)
        from admin.backend.app.database import AnnotationRecord
        with Session(engine) as db:
            record = AnnotationRecord(
                product_id=product_id,
                field_name=field_name,
                old_value=feedback_type,
                new_value=feedback_type,
                source="user_feedback",
                annotator="system",
            )
            db.add(record)
            db.commit()
        return True
    except Exception:
        return False

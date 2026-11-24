"""
Migration script: import existing sample model images from GCS into admin database.

Usage:
    python -m admin.integration.migrate_sample_models
"""
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def migrate():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set")
        sys.exit(1)

    try:
        from google.cloud import storage as gcs_storage
    except ImportError:
        print("google-cloud-storage not installed")
        sys.exit(1)

    bucket_name = os.environ.get("GCS_BUCKET_NAME", "").strip()
    if not bucket_name:
        raise SystemExit("Set GCS_BUCKET_NAME before migrating sample images.")
    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)

    engine = create_engine(url)
    from admin.backend.app.database import SampleModel, Base
    Base.metadata.create_all(engine, checkfirst=True)

    with Session(engine) as db:
        for gender in ["男性模特", "女性模特"]:
            prefix = f"sample_models/{gender}/"
            blobs = list(bucket.list_blobs(prefix=prefix))
            g = "男" if "男" in gender else "女"
            for i, blob in enumerate(blobs):
                if blob.name.endswith("/"):
                    continue
                filename = blob.name.split("/")[-1]
                existing = db.query(SampleModel).filter_by(image_filename=filename, gender=g).first()
                if existing:
                    print(f"  Skip existing: {filename}")
                    continue
                url = f"https://storage.googleapis.com/{bucket_name}/{blob.name}"
                m = SampleModel(
                    name=filename.rsplit(".", 1)[0],
                    gender=g,
                    image_filename=filename,
                    gcs_url=url,
                    display_order=i,
                    uploaded_by="migration",
                    file_size=blob.size,
                )
                db.add(m)
                print(f"  Added: {filename}")
        db.commit()
        print("Migration complete.")


if __name__ == "__main__":
    migrate()

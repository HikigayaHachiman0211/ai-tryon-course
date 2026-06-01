"""Temporary file cleanup utilities."""

import os
import time
import glob
import asyncio
from app.config import (
    UPLOAD_DIR, ASSET_DIR, HISTORY_FILES_DIR,
    TEMP_FILE_MAX_AGE_SECONDS,
)


def cleanup_old_files(directory: str, max_age_seconds: int) -> int:
    """Remove files older than max_age_seconds. Returns count of removed files."""
    removed = 0
    now = time.time()
    try:
        for filepath in glob.glob(os.path.join(directory, "*")):
            if not os.path.isfile(filepath):
                continue
            try:
                age = now - os.path.getmtime(filepath)
                if age > max_age_seconds:
                    os.unlink(filepath)
                    removed += 1
            except OSError:
                pass
    except Exception as e:
        print(f"[Cleanup] error scanning {directory}: {e}")
    return removed


def run_cleanup() -> dict:
    """Run cleanup on all temp directories."""
    results = {}
    for name, directory in [("uploads", UPLOAD_DIR), ("assets", ASSET_DIR), ("history_files", HISTORY_FILES_DIR)]:
        count = cleanup_old_files(directory, TEMP_FILE_MAX_AGE_SECONDS)
        results[name] = count
        if count > 0:
            print(f"[Cleanup] removed {count} old files from {name}")
    return results


async def periodic_cleanup(interval_seconds: int = 3600):
    """Background task that runs cleanup periodically."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            run_cleanup()
        except Exception as e:
            print(f"[Cleanup] periodic cleanup error: {e}")

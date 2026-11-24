from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def check(url: str, retries: int) -> tuple[str, int, str]:
    last_error = ""
    for attempt in range(retries):
        try:
            request = Request(url, method="GET", headers={"Range": "bytes=0-32", "User-Agent": "ai-tryon-catalog-gate/1"})
            with urlopen(request, timeout=20) as response:
                status = int(response.status)
                content_type = response.headers.get("Content-Type", "")
                body = response.read(33)
                if status < 200 or status >= 300 or not body or not content_type.startswith("image/"):
                    raise RuntimeError(f"status={status} content_type={content_type!r} body={len(body)}")
                return url, status, content_type
        except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt + 1 < retries:
                time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"{url}: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = args.base_url.rstrip("/")
    references = manifest.get("references") or []
    if int(manifest.get("product_count", 0)) != len(references):
        raise SystemExit("manifest reference count does not equal product_count")
    object_names = {str(item["name"]) for item in manifest.get("objects", [])}
    missing_objects = sorted({str(item["object_name"]) for item in references} - object_names)
    if missing_objects:
        raise SystemExit("manifest references point to missing objects: " + ", ".join(missing_objects[:20]))
    urls = [f"{base}/{quote(str(item['name']).lstrip('/'), safe='/')}" for item in manifest["objects"]]
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 16))) as pool:
        futures = [pool.submit(check, url, args.retries) for url in urls]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append(str(exc))
    if failures:
        raise SystemExit("public image URL gate failed:\n" + "\n".join(sorted(failures)[:50]))
    print(json.dumps({
        "checked_unique_objects": len(urls),
        "covered_catalog_references": len(references),
        "failures": 0,
        "base_url": base,
    }))


if __name__ == "__main__":
    main()

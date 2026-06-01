from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path

from google.cloud import storage

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_JD_IMAGE_DIR = PROJECT_ROOT / "downloaded_jd_images" / "\u7fbd\u7ed2\u670d_png"
DEFAULT_OUTPUT_PATH = BACKEND_ROOT / "gcs_public_urls.json"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def find_taobao_image_dir() -> Path | None:
    import re
    candidates = [p for p in WORKSPACE_ROOT.glob("img\u7fbd\u7ed2\u670d*") if p.is_dir()]
    if not candidates:
        return None

    def sort_key(path: Path) -> tuple[int, float]:
        match = re.search(r"(\d+)$", path.name)
        return (int(match.group(1)) if match else 0, path.stat().st_mtime)

    return sorted(candidates, key=sort_key, reverse=True)[0]


def guess_content_type(path: Path) -> str:
    ct = mimetypes.guess_type(path.name)[0]
    if ct:
        return ct
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")


def collect_image_files(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def upload_images(
    bucket: storage.Bucket,
    image_files: list[Path],
    prefix: str,
    public_urls: dict[str, str],
) -> int:
    count = 0
    for image_path in image_files:
        blob_name = prefix + "/" + image_path.name
        blob = bucket.blob(blob_name)
        if blob.exists():
            public_urls[image_path.name] = blob.public_url
            count += 1
            continue
        blob.upload_from_filename(str(image_path), content_type=guess_content_type(image_path))
        blob.make_public()
        public_urls[image_path.name] = blob.public_url
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload product images (JD + Taobao) to GCS")
    parser.add_argument("--bucket", required=True, help="Target GCS bucket name")
    parser.add_argument("--prefix", default="product-images", help="GCS object prefix (flat namespace)")
    parser.add_argument("--jd-dir", default=str(DEFAULT_JD_IMAGE_DIR), help="Local JD PNG directory")
    parser.add_argument("--taobao-dir", default=None, help="Local Taobao image directory (auto-detect if omitted)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON for public URLs")
    args = parser.parse_args()

    jd_dir = Path(args.jd_dir).resolve()
    taobao_dir = Path(args.taobao_dir).resolve() if args.taobao_dir else find_taobao_image_dir()
    output_path = Path(args.output).resolve()
    prefix = args.prefix.strip("/")

    client = storage.Client()
    bucket = client.bucket(args.bucket)
    public_urls: dict[str, str] = {}

    jd_count = 0
    if jd_dir.exists():
        jd_files = collect_image_files(jd_dir)
        print("Uploading " + str(len(jd_files)) + " JD images from " + str(jd_dir) + " ...")
        jd_count = upload_images(bucket, jd_files, prefix, public_urls)
        print("  JD uploaded: " + str(jd_count))
    else:
        print("WARNING: JD image directory not found: " + str(jd_dir))

    taobao_count = 0
    if taobao_dir and taobao_dir.exists():
        taobao_files = collect_image_files(taobao_dir)
        print("Uploading " + str(len(taobao_files)) + " Taobao images from " + str(taobao_dir) + " ...")
        taobao_count = upload_images(bucket, taobao_files, prefix, public_urls)
        print("  Taobao uploaded: " + str(taobao_count))
    else:
        print("WARNING: Taobao image directory not found: " + str(taobao_dir))

    total = jd_count + taobao_count
    output_path.write_text(json.dumps(public_urls, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Total uploaded: " + str(total) + " (JD: " + str(jd_count) + ", Taobao: " + str(taobao_count) + ")")
    print("Public URL mapping saved to: " + str(output_path))
    suggested = "https://storage.googleapis.com/" + args.bucket + "/" + prefix
    print("Suggested PUBLIC_IMAGE_BASE_URL: " + suggested)


if __name__ == "__main__":
    main()

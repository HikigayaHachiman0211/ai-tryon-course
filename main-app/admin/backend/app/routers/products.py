from __future__ import annotations

import asyncio
import io
import json
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func, or_

from app.auth import get_current_admin
from app.config import get_settings
from app.database import Product, get_db
from app.services import gcs

router = APIRouter(prefix="/api/admin/products", tags=["products"])


class ProductUpdate(BaseModel):
    title: str | None = None
    price: float | None = None
    product_url: str | None = None
    style_type: str | None = None
    color_family: str | None = None
    body_fit: str | None = None
    style_features: list[str] | None = None
    function_features: list[str] | None = None
    size_tags: list[str] | None = None
    size_notes: str | None = None


class ProductCreate(BaseModel):
    title: str
    price: float
    image_path: str
    style_type: str
    color_family: str
    body_fit: str
    style_features: list[str] = []
    function_features: list[str] = []
    size_tags: list[str] = []
    size_notes: str | None = None
    product_url: str | None = None


class BatchDeleteRequest(BaseModel):
    ids: list[int]


def _validate_url(url: str | None):
    if url and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="链接必须以 https:// 开头")


@router.get("")
def list_products(
    page: int = 1,
    size: int = 20,
    keyword: str = "",
    platform: str = "",
    style_type: str = "",
    color_family: str = "",
    price_min: float | None = None,
    price_max: float | None = None,
    link_status: str = "",
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    q = db.query(Product)
    if keyword:
        q = q.filter(Product.title.ilike(f"%{keyword}%"))
    if platform == "jd":
        q = q.filter(Product.image_path.like("%downloaded_jd_images%"))
    elif platform == "taobao":
        q = q.filter(~Product.image_path.like("%downloaded_jd_images%"))
    if style_type:
        q = q.filter(Product.style_type == style_type)
    if color_family:
        q = q.filter(Product.color_family == color_family)
    if price_min is not None:
        q = q.filter(Product.price >= price_min)
    if price_max is not None:
        q = q.filter(Product.price <= price_max)
    if link_status == "has_link":
        q = q.filter(Product.product_url.isnot(None), Product.product_url != "")
    elif link_status == "no_link":
        q = q.filter(or_(Product.product_url.is_(None), Product.product_url == ""))

    total = q.count()
    items = q.order_by(Product.id.desc()).offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_serialize(p) for p in items],
    }


@router.get("/missing-links")
def missing_links(
    page: int = 1, size: int = 50,
    admin=Depends(get_current_admin), db=Depends(get_db),
):
    q = db.query(Product).filter(or_(Product.product_url.is_(None), Product.product_url == ""))
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [_serialize(p) for p in items]}


@router.get("/{product_id}")
def get_product(product_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    return _serialize(p)


@router.put("/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    _validate_url(body.product_url)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.post("")
def create_product(body: ProductCreate, admin=Depends(get_current_admin), db=Depends(get_db)):
    _validate_url(body.product_url)
    p = Product(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.delete("/{product_id}")
def delete_product(product_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    db.delete(p)
    db.commit()
    return {"detail": "已删除"}


@router.post("/batch-delete")
def batch_delete(body: BatchDeleteRequest, admin=Depends(get_current_admin), db=Depends(get_db)):
    deleted = db.query(Product).filter(Product.id.in_(body.ids)).delete(synchronize_session="fetch")
    db.commit()
    return {"deleted": deleted}


@router.post("/import")
async def import_products(file: UploadFile = File(...), admin=Depends(get_current_admin), db=Depends(get_db)):
    content = await file.read()
    try:
        rows = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON 格式错误")
    if not isinstance(rows, list):
        raise HTTPException(400, "JSON 必须是数组")

    count = 0
    for row in rows:
        p = Product(
            title=row.get("商品标题", row.get("title", "")),
            price=float(row.get("价格", row.get("price", 0))),
            image_path=row.get("图片路径", row.get("image_path", "")),
            style_type=row.get("款式类型", row.get("style_type", "")),
            color_family=row.get("精准颜色色系", row.get("color_family", "")),
            body_fit=row.get("版型与身材适配度", row.get("body_fit", "")),
            style_features=row.get("风格特征", row.get("style_features", [])),
            function_features=row.get("功能属性", row.get("function_features", [])),
            size_tags=row.get("size_tags", []),
            size_notes=row.get("size_notes"),
            product_url=row.get("商品链接", row.get("product_url")),
        )
        db.add(p)
        count += 1
    db.commit()
    return {"imported": count}


def _import_rows(rows: list, db) -> int:
    count = 0
    for row in rows:
        p = Product(
            title=row.get("商品标题", row.get("title", "")),
            price=float(row.get("价格", row.get("price", 0))),
            image_path=row.get("图片路径", row.get("image_path", "")),
            style_type=row.get("款式类型", row.get("style_type", "")),
            color_family=row.get("精准颜色色系", row.get("color_family", "")),
            body_fit=row.get("版型与身材适配度", row.get("body_fit", "")),
            style_features=row.get("风格特征", row.get("style_features", [])),
            function_features=row.get("功能属性", row.get("function_features", [])),
            size_tags=row.get("size_tags", []),
            size_notes=row.get("size_notes"),
            product_url=row.get("商品链接", row.get("product_url")),
        )
        db.add(p)
        count += 1
    db.commit()
    return count


@router.post("/import-json")
def import_products_json(rows: list, admin=Depends(get_current_admin), db=Depends(get_db)):
    if not isinstance(rows, list):
        raise HTTPException(400, "JSON 必须是数组")
    return {"imported": _import_rows(rows, db)}


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), admin=Depends(get_current_admin)):
    data = await file.read()
    filename = file.filename or "upload.png"
    dest = f"羽绒服_png/{filename}"
    url = gcs.upload_blob(dest, data, content_type=file.content_type or "image/png")
    return {"image_url": url, "image_path": dest}


@router.post("/import-links")
async def import_links(file: UploadFile = File(...), admin=Depends(get_current_admin), db=Depends(get_db)):
    content = await file.read()
    filename = (file.filename or "").lower()
    rows_updated = 0

    if filename.endswith(".csv"):
        import csv
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
        for row in reader:
            if len(row) < 2:
                continue
            identifier, url = row[0].strip(), row[1].strip()
            if not url.startswith("https://"):
                continue
            # Try match by ID first, then by title
            product = None
            if identifier.isdigit():
                product = db.get(Product, int(identifier))
            if not product:
                product = db.query(Product).filter(Product.title.ilike(f"%{identifier}%")).first()
            if product:
                product.product_url = url
                rows_updated += 1
        db.commit()
    elif filename.endswith((".xlsx", ".xls")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or len(row) < 2:
                continue
            identifier, url = str(row[0]).strip(), str(row[1]).strip()
            if not url.startswith("https://"):
                continue
            product = None
            if identifier.isdigit():
                product = db.get(Product, int(identifier))
            if not product:
                product = db.query(Product).filter(Product.title.ilike(f"%{identifier}%")).first()
            if product:
                product.product_url = url
                rows_updated += 1
        db.commit()
    else:
        raise HTTPException(400, "仅支持 CSV 或 Excel 文件")

    return {"updated": rows_updated}


@router.post("/validate-links")
async def validate_links(admin=Depends(get_current_admin), db=Depends(get_db)):
    products = db.query(Product).filter(
        Product.product_url.isnot(None), Product.product_url != ""
    ).all()

    results = []
    sem = asyncio.Semaphore(5)

    async def check(p: Product):
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.head(p.product_url, follow_redirects=True)
                    return {"id": p.id, "title": p.title, "url": p.product_url, "status": resp.status_code}
            except Exception as e:
                return {"id": p.id, "title": p.title, "url": p.product_url, "status": 0, "error": str(e)}

    tasks = [check(p) for p in products[:200]]  # Limit to first 200
    results = await asyncio.gather(*tasks)
    return {"total": len(results), "results": list(results)}


@router.post("/{product_id}/test-link")
async def test_link(product_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    if not p.product_url:
        raise HTTPException(400, "商品无链接")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.head(p.product_url, follow_redirects=True)
            return {"url": p.product_url, "status_code": resp.status_code, "accessible": resp.status_code < 400}
    except Exception as e:
        return {"url": p.product_url, "status_code": 0, "accessible": False, "error": str(e)}


@router.post("/auto-fill-links")
def auto_fill_links(admin=Depends(get_current_admin), db=Depends(get_db)):
    products = db.query(Product).filter(
        or_(Product.product_url.is_(None), Product.product_url == "")
    ).all()
    filled = 0
    for p in products:
        url = _generate_search_url(p.title)
        if url:
            p.product_url = url
            filled += 1
    db.commit()
    return {"filled": filled}


def _generate_search_url(title: str) -> str | None:
    if not title:
        return None
    import urllib.parse
    query = urllib.parse.quote(title[:50])
    return f"https://search.jd.com/Search?keyword={query}"


def _build_image_url(image_path: str | None, base_url: str) -> str | None:
    if not image_path:
        return None
    from urllib.parse import quote
    filename = image_path.replace("\\", "/").split("/")[-1]
    return f"{base_url.rstrip('/')}/{quote(filename)}"


def _serialize(p: Product) -> dict:
    settings = get_settings()
    return {
        "id": p.id,
        "title": p.title,
        "price": p.price,
        "image_path": p.image_path,
        "image_url": _build_image_url(p.image_path, settings.PUBLIC_IMAGE_BASE_URL),
        "style_type": p.style_type,
        "color_family": p.color_family,
        "body_fit": p.body_fit,
        "style_features": p.style_features,
        "function_features": p.function_features,
        "size_tags": p.size_tags,
        "size_notes": p.size_notes,
        "product_url": p.product_url,
        "annotation_status": getattr(p, "annotation_status", None),
        "annotation_confidence": getattr(p, "annotation_confidence", None),
    }

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from sqlalchemy import Float, Integer, String, create_engine, delete, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from app.catalog_seed import ensure_brand_tag, extract_brand_tag, find_taobao_workbook, load_catalog_seed_rows, normalize_brand_name, resolve_seed_source

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_SQLITE_PATH = BACKEND_ROOT / "local.db"
DEFAULT_DATABASE_JSON = PROJECT_ROOT / "database.json"

SIZE_PATTERN = re.compile(
    r"(?:(?<=^)|(?<=[\s/_(（【\[-]))(7XL|6XL|5XL|4XL|3XL|2XL|XXXL|XXL|XL|XS|S|M|L)(?=(?:\s|$|码|[)\]_/）】,\-]))",
    re.IGNORECASE,
)
SIZE_NOTE_PATTERN = re.compile(r"(建议体重[^ ]+|体重约\d+(?:-\d+)?斤|[12]\d{2}/\d{2,3}A)")
SIZE_ALIASES = {
    "XXL": "2XL",
    "XXXL": "3XL",
}
SIZE_ORDER = {
    "XS": 1,
    "S": 2,
    "M": 3,
    "L": 4,
    "XL": 5,
    "2XL": 6,
    "3XL": 7,
    "4XL": 8,
    "5XL": 9,
    "6XL": 10,
    "7XL": 11,
}


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    style_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    color_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    body_fit: Mapped[str] = mapped_column(String(255), nullable=False)
    style_features: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    function_features: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    size_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    size_notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)


def normalize_size(value: str | None) -> str | None:
    if not value:
        return None

    text = value.upper().replace(" ", "")
    match = re.search(r"(7XL|6XL|5XL|4XL|3XL|2XL|XXXL|XXL|XL|XS|S|M|L)", text)
    if match:
        detected = match.group(1)
        return SIZE_ALIASES.get(detected, detected)

    height_match = re.search(r"(1[5-9]\d)", text)
    if not height_match:
        return None

    height = int(height_match.group(1))
    if height <= 160:
        return "S"
    if height <= 170:
        return "M"
    if height <= 175:
        return "L"
    if height <= 180:
        return "XL"
    if height <= 185:
        return "2XL"
    if height <= 190:
        return "3XL"
    return "4XL"


def extract_size_tags(title: str) -> list[str]:
    tags: list[str] = []
    for match in SIZE_PATTERN.finditer(title.upper()):
        normalized = normalize_size(match.group(1))
        if normalized and normalized not in tags:
            tags.append(normalized)
    return tags


def extract_size_notes(title: str) -> str | None:
    notes = []
    cleaned_title = title.replace("_", "/")
    for match in SIZE_NOTE_PATTERN.findall(cleaned_title):
        note = match.strip()
        if note and note not in notes:
            notes.append(note)
    if not notes:
        return None
    return "; ".join(notes)


def resolve_database_json_path(database_json_path: Path | None = None) -> Path:
    if database_json_path:
        return database_json_path

    env_path = os.getenv("DATABASE_JSON_PATH")
    if env_path:
        return Path(env_path)

    return DEFAULT_DATABASE_JSON


def build_database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    driver = os.getenv("DB_DRIVER", "sqlite").lower()
    if driver == "sqlite":
        sqlite_path = Path(os.getenv("SQLITE_PATH", DEFAULT_SQLITE_PATH))
        return f"sqlite+pysqlite:///{sqlite_path.as_posix()}"

    username = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")
    if not all([username, password, database]):
        raise RuntimeError("Missing DB_USER, DB_PASSWORD or DB_NAME for Cloud SQL connection")

    instance_name = os.getenv("INSTANCE_CONNECTION_NAME")
    unix_socket = os.getenv("INSTANCE_UNIX_SOCKET")
    if instance_name and not unix_socket:
        unix_socket = f"/cloudsql/{instance_name}"

    if driver in {"postgres", "postgresql"}:
        if unix_socket:
            return str(
                URL.create(
                    "postgresql+psycopg",
                    username=username,
                    password=password,
                    database=database,
                    query={"host": unix_socket},
                )
            )

        return str(
            URL.create(
                "postgresql+psycopg",
                username=username,
                password=password,
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=database,
            )
        )

    if driver == "mysql":
        if unix_socket:
            return str(
                URL.create(
                    "mysql+pymysql",
                    username=username,
                    password=password,
                    database=database,
                    query={"unix_socket": unix_socket},
                )
            )

        return str(
            URL.create(
                "mysql+pymysql",
                username=username,
                password=password,
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("DB_PORT", "3306")),
                database=database,
            )
        )

    raise RuntimeError(f"Unsupported DB_DRIVER: {driver}")


DATABASE_URL = build_database_url()
ENGINE = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def load_seed_rows(database_json_path: Path | None = None) -> list[dict]:
    if database_json_path:
        return load_catalog_seed_rows(DEFAULT_DATABASE_JSON, database_json_path)

    rows = load_catalog_seed_rows(DEFAULT_DATABASE_JSON, DEFAULT_DATABASE_JSON)
    taobao_workbook = find_taobao_workbook()
    if taobao_workbook is not None:
        rows.extend(load_catalog_seed_rows(DEFAULT_DATABASE_JSON, taobao_workbook))
    return rows


def build_product(row: dict) -> Product:
    title = row["商品标题"].strip()
    brand = normalize_brand_name(str(row.get("品牌") or "")) or extract_brand_tag(row.get("风格特征") or [])
    style_features = ensure_brand_tag(row.get("风格特征") or [], brand)
    return Product(
        title=title,
        price=float(row["价格"]),
        image_path=row["图片路径"].replace("\\", "/"),
        style_type=row["款式类型"],
        color_family=row["精准颜色色系"],
        body_fit=row["版型与身材适配度"],
        style_features=style_features,
        function_features=row.get("功能属性") or [],
        size_tags=extract_size_tags(title),
        size_notes=extract_size_notes(title),
        product_url=(row.get("商品链接") or "").strip() or None,
    )


def ensure_database(
    *,
    seed_if_empty: bool,
    replace: bool = False,
    database_json_path: Path | None = None,
) -> int:
    Base.metadata.create_all(bind=ENGINE)
    force_reseed = os.getenv("FORCE_RESEED", "").strip().lower() in ("1", "true", "yes")
    source_type, source_path = resolve_seed_source(DEFAULT_DATABASE_JSON, database_json_path)
    taobao_workbook = find_taobao_workbook() if database_json_path is None else None
    source_prefix = source_path.parent.name if source_type == "taobao" else None
    should_replace = replace or force_reseed or ((source_type == "taobao" or taobao_workbook is not None) and DATABASE_URL.startswith("sqlite"))
    if not seed_if_empty and not should_replace:
        return 0

    with SessionLocal() as session:
        existing_count = session.scalar(select(func.count()).select_from(Product)) or 0

        # Auto-detect stale data: if the seed source has significantly more rows
        # than the DB (e.g. Taobao data was added to database.json), trigger reseed.
        if existing_count and not should_replace and not replace:
            rows = load_seed_rows(database_json_path)
            if len(rows) > existing_count * 1.1:
                should_replace = True
            else:
                rows = None  # avoid reloading later
        else:
            rows = None

        if should_replace and existing_count and taobao_workbook is not None and not replace and not force_reseed:
            jd_count = session.scalar(
                select(func.count()).select_from(Product).where(Product.image_path.like("downloaded_jd_images/%"))
            ) or 0
            taobao_count = session.scalar(
                select(func.count()).select_from(Product).where(Product.image_path.like(f"{taobao_workbook.parent.name}/%"))
            ) or 0
            if jd_count and taobao_count:
                should_replace = False
        elif should_replace and existing_count and source_prefix and not replace and not force_reseed:
            first_product = session.scalars(select(Product).limit(1)).first()
            if first_product and first_product.image_path.startswith(f"{source_prefix}/"):
                should_replace = False
        if existing_count and not should_replace:
            return 0

        if should_replace and existing_count:
            session.execute(delete(Product))
            session.commit()

        if rows is None:
            rows = load_seed_rows(database_json_path)
        session.add_all(build_product(row) for row in rows)
        session.commit()
        return len(rows)


def count_products(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Product)) or 0

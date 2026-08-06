"""Issue #7: Load transformed sales data into PostgreSQL.

Idempotent: re-running on the same input does not create duplicates.
Uses INSERT ... ON CONFLICT (order_id) DO UPDATE so the last-known-good
version of each row wins.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Iterable

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # rows per INSERT statement


class LoadError(Exception):
    """Raised when the load stage cannot complete."""


# ─────────────────────────────────────────────────────────────────────
# Engine construction
# ─────────────────────────────────────────────────────────────────────
def _build_db_url() -> str:
    """Read DB credentials from .env and build a SQLAlchemy URL.

    Fails fast if any credential is missing — better to blow up at startup
    than to have the loader hang trying to connect to nowhere.
    """
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    required = {
        "DB_HOST":     os.getenv("DB_HOST"),
        "DB_PORT":     os.getenv("DB_PORT", "5432"),
        "DB_NAME":     os.getenv("DB_NAME"),
        "DB_USER":     os.getenv("DB_USER"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise LoadError(f"Missing DB credentials in .env: {missing}")

    return (
        f"postgresql+psycopg2://{required['DB_USER']}:{required['DB_PASSWORD']}"
        f"@{required['DB_HOST']}:{required['DB_PORT']}/{required['DB_NAME']}"
    )


def get_engine() -> Engine:
    """Build a pooled SQLAlchemy engine.

    pool_pre_ping=True: silently reconnects if the DB dropped the connection
    (common with cloud DBs after idle). One-line fix for a class of production
    bugs that took me an embarrassingly long time to learn about.
    """
    return create_engine(
        _build_db_url(),
        pool_pre_ping=True,
        pool_size=5,
        future=True,
    )


# ─────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────
def apply_schema(engine: Engine) -> None:
    """Apply sql/schema.sql. Idempotent — safe to run every time."""
    schema_file = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
    if not schema_file.exists():
        raise LoadError(f"Schema file not found: {schema_file}")

    ddl = schema_file.read_text(encoding="utf-8")
    logger.info("Applying schema from %s", schema_file)

    try:
        with engine.begin() as conn:  # begin() = auto-commit on success, rollback on error
            conn.execute(text(ddl))
    except SQLAlchemyError as e:
        raise LoadError(f"Failed to apply schema: {e}") from e

    logger.info("Schema applied")


# ─────────────────────────────────────────────────────────────────────
# Batching helper
# ─────────────────────────────────────────────────────────────────────
def _chunked(records: list[dict], size: int) -> Iterable[list[dict]]:
    """Yield successive slices of `size` from `records`."""
    for i in range(0, len(records), size):
        yield records[i : i + size]


# ─────────────────────────────────────────────────────────────────────
# The load
# ─────────────────────────────────────────────────────────────────────
UPSERT_SQL = text("""
    INSERT INTO sales_orders (
        order_id, order_date, customer_id, sku, product_name, category,
        region, channel, quantity, unit_price, total_amount, load_run_id
    ) VALUES (
        :order_id, :order_date, :customer_id, :sku, :product_name, :category,
        :region, :channel, :quantity, :unit_price, :total_amount, :load_run_id
    )
    ON CONFLICT (order_id) DO UPDATE SET
        order_date   = EXCLUDED.order_date,
        customer_id  = EXCLUDED.customer_id,
        sku          = EXCLUDED.sku,
        product_name = EXCLUDED.product_name,
        category     = EXCLUDED.category,
        region       = EXCLUDED.region,
        channel      = EXCLUDED.channel,
        quantity     = EXCLUDED.quantity,
        unit_price   = EXCLUDED.unit_price,
        total_amount = EXCLUDED.total_amount,
        load_run_id  = EXCLUDED.load_run_id,
        loaded_at    = NOW();
""")


def load_sales_data(df: pd.DataFrame, engine: Engine, run_id: str | None = None) -> dict:
    """UPSERT the transformed DataFrame into sales_orders.

    Returns a dict with row counts so the orchestrator can log/report.
    """
    if df.empty:
        raise LoadError("Refusing to load an empty DataFrame")

    run_id = run_id or uuid.uuid4().hex[:12]
    logger.info("load_sales_data: %d rows, run_id=%s", len(df), run_id)

    # Convert DataFrame to list of dicts once. Pandas' `.to_dict` is fine
    # at this scale (~500 rows). For 10M+ rows we'd stream via itertuples.
    records = df.assign(load_run_id=run_id).to_dict(orient="records")

    inserted = 0
    try:
        with engine.begin() as conn:
            for batch in _chunked(records, BATCH_SIZE):
                conn.execute(UPSERT_SQL, batch)
                inserted += len(batch)
                logger.info("  batch committed: %d / %d rows", inserted, len(records))
    except SQLAlchemyError as e:
        raise LoadError(f"Load failed after {inserted} rows: {e}") from e

    logger.info("load_sales_data: done, %d rows upserted (run_id=%s)", inserted, run_id)
    return {"rows_upserted": inserted, "run_id": run_id}


# ─────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from extract import extract_sales_data
    from transform import transform_sales_data

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    project_root = Path(__file__).resolve().parent.parent
    csv_file = project_root / "data" / "raw" / "sales.csv"

    engine = get_engine()
    apply_schema(engine)

    raw   = extract_sales_data(csv_file)
    clean = transform_sales_data(raw)
    result = load_sales_data(clean, engine)

    print(f"\n✅ Loaded {result['rows_upserted']} rows. run_id={result['run_id']}")
"""Issue #12: End-to-end pipeline test.

Runs extract -> transform -> load against the sample CSV and verifies the
database ends up in the expected state.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract import extract_sales_data
from load import apply_schema, get_engine, load_sales_data
from transform import transform_sales_data


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "raw" / "sales.csv"


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    apply_schema(eng)
    yield eng
    eng.dispose()


def test_extract_returns_nonempty_dataframe():
    df = extract_sales_data(CSV_PATH)
    assert not df.empty
    assert "order_id" in df.columns


def test_transform_drops_bad_rows_and_dedupes():
    raw = extract_sales_data(CSV_PATH)
    clean = transform_sales_data(raw)

    assert len(clean) < len(raw)
    assert clean["order_id"].is_unique
    assert clean["order_date"].isna().sum() == 0
    assert (clean["quantity"] > 0).all()


def test_load_is_idempotent(engine):
    raw = extract_sales_data(CSV_PATH)
    clean = transform_sales_data(raw)

    load_sales_data(clean, engine, run_id="test-run-1")
    with engine.connect() as conn:
        count_1 = conn.execute(text("SELECT COUNT(*) FROM sales_orders")).scalar()

    load_sales_data(clean, engine, run_id="test-run-2")
    with engine.connect() as conn:
        count_2 = conn.execute(text("SELECT COUNT(*) FROM sales_orders")).scalar()

    assert count_1 == count_2


def test_no_nulls_in_key_columns(engine):
    with engine.connect() as conn:
        nulls = conn.execute(text("""
            SELECT COUNT(*) FROM sales_orders
            WHERE order_id IS NULL
               OR order_date IS NULL
               OR customer_id IS NULL
               OR quantity IS NULL
               OR unit_price IS NULL
        """)).scalar()
    assert nulls == 0
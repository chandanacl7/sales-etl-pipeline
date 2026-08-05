"""Issues #4, #5, #6: Transform raw sales data.

Pipeline:
    clean_missing_values  →  remove_duplicates  →  standardize_dates  →  coerce_numeric_types

Each function is a pure transformation: DataFrame in, new DataFrame out.
No side effects, no shared state — makes unit testing trivial and lets
main.py chain them in one line.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import pandas as pd

logger = logging.getLogger(__name__)

# Columns that must be present and non-null for a row to be usable.
# Missing any of these makes the row unfixable — drop it.
CRITICAL_COLUMNS: tuple[str, ...] = (
    "order_id", "order_date", "customer_id", "sku", "quantity", "unit_price",
)

# Accepted date formats in the raw file. Order matters for tie-breaks
# (though these are unambiguous once anchored to the year position).
DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",    # 2026-01-07
    "%d/%m/%Y",    # 24/05/2026
    "%m-%d-%Y",    # 06-01-2026
)


# ─────────────────────────────────────────────────────────────────────
# Issue #4: Clean missing values
# ─────────────────────────────────────────────────────────────────────
def clean_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Remove rows with missing critical values; impute non-critical ones.

    Strategy:
      - Critical columns (order_id, date, customer, sku, qty, price) missing
        → row is unusable → drop it.
      - Non-critical missing values (e.g. region) → impute with 'UNKNOWN'
        so we keep the sale record but flag the gap for BI.

    Rationale for split policy:
      Blindly dropping any row with any null loses too much data. Blindly
      imputing everything hides real problems. Splitting by criticality
      preserves as much data as possible while keeping analytics honest.
    """
    before = len(df)
    logger.info("clean_missing_values: input rows=%d", before)

    # Log null counts before cleaning so we can trace data quality over time
    null_counts = df.isna().sum()
    non_zero_nulls = null_counts[null_counts > 0]
    if not non_zero_nulls.empty:
        logger.info("Null counts by column:\n%s", non_zero_nulls.to_string())

    # 1. Drop rows missing any critical column
    cleaned = df.dropna(subset=list(CRITICAL_COLUMNS)).copy()
    dropped = before - len(cleaned)
    if dropped > 0:
        logger.warning("Dropped %d rows with missing critical fields", dropped)

    # 2. Impute non-critical fields
    cleaned["region"] = cleaned["region"].fillna("UNKNOWN")

    logger.info("clean_missing_values: output rows=%d (dropped %d, imputed region for missing)",
                len(cleaned), dropped)
    return cleaned


# ─────────────────────────────────────────────────────────────────────
# Issue #5: Remove duplicate records
# ─────────────────────────────────────────────────────────────────────
def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate order rows using order_id as the business key.

    We dedup on order_id (not on the full row) because:
      - order_id IS the business key — same ID means same order
      - Two rows with the same order_id but slightly different values are
        a data quality issue upstream; keeping the first occurrence is
        the least surprising default
      - Full-row dedup would miss cases where the same order was ingested
        twice with a whitespace difference
    """
    before = len(df)
    logger.info("remove_duplicates: input rows=%d", before)

    dup_mask = df.duplicated(subset=["order_id"], keep="first")
    dup_count = int(dup_mask.sum())

    if dup_count > 0:
        # Log a sample of dup order_ids for traceability
        dup_ids = df.loc[dup_mask, "order_id"].unique()[:5]
        logger.warning("Found %d duplicate order_ids. Sample: %s",
                       dup_count, list(dup_ids))

    deduped = df.drop_duplicates(subset=["order_id"], keep="first").copy()
    logger.info("remove_duplicates: output rows=%d (removed %d duplicates)",
                len(deduped), dup_count)
    return deduped


# ─────────────────────────────────────────────────────────────────────
# Issue #6: Standardize date columns
# ─────────────────────────────────────────────────────────────────────
def _parse_date_multi_format(value: str) -> pd.Timestamp | pd.NaT:
    """Try each known format; return NaT if none match.

    Kept as a helper so standardize_dates stays declarative.
    """
    if pd.isna(value):
        return pd.NaT
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(value, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.NaT


def standardize_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Parse order_date into a real datetime, dropping unparseable rows.

    Raw file mixes three formats: ISO, DMY-slash, MDY-dash. We try each
    and drop rows where none work — they represent genuinely bad data.

    Why not `pd.to_datetime(..., errors='coerce')` alone?
      Because it can't handle multiple formats at once, and with
      `dayfirst=True` it silently misparses ambiguous dates (e.g. 06/01/2026
      as June 1 vs Jan 6). Explicit format list = explicit contract.
    """
    before = len(df)
    logger.info("standardize_dates: input rows=%d", before)

    parsed = df.copy()
    parsed["order_date"] = parsed["order_date"].apply(_parse_date_multi_format)

    invalid = parsed["order_date"].isna()
    invalid_count = int(invalid.sum())
    if invalid_count > 0:
        bad_samples = df.loc[invalid, "order_date"].unique()[:5]
        logger.warning("Dropping %d rows with unparseable dates. Samples: %s",
                       invalid_count, list(bad_samples))
        parsed = parsed.loc[~invalid].copy()

    logger.info("standardize_dates: output rows=%d (dropped %d unparseable)",
                len(parsed), invalid_count)
    return parsed


# ─────────────────────────────────────────────────────────────────────
# Supporting: coerce numeric types
# ─────────────────────────────────────────────────────────────────────
def coerce_numeric_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert quantity → int and unit_price → Decimal.

    Why Decimal for money? Floats can't represent 0.10 exactly, and money
    math (tax, discount, total) accumulates float error fast. Postgres will
    store this as NUMERIC(10,2). This is the same reason Java code uses
    BigDecimal for currency instead of double.
    """
    before = len(df)
    result = df.copy()

    # quantity → int, drop rows where conversion fails or value <= 0
    result["quantity"] = pd.to_numeric(result["quantity"], errors="coerce")
    bad_qty = result["quantity"].isna() | (result["quantity"] <= 0)
    if bad_qty.any():
        logger.warning("Dropping %d rows with invalid quantity", int(bad_qty.sum()))
        result = result.loc[~bad_qty].copy()
    result["quantity"] = result["quantity"].astype(int)

    # unit_price → Decimal, drop rows where conversion fails
    def _to_decimal(v: str) -> Decimal | None:
        try:
            return Decimal(str(v))
        except (InvalidOperation, TypeError):
            return None

    result["unit_price"] = result["unit_price"].apply(_to_decimal)
    bad_price = result["unit_price"].isna()
    if bad_price.any():
        logger.warning("Dropping %d rows with invalid unit_price", int(bad_price.sum()))
        result = result.loc[~bad_price].copy()

    logger.info("coerce_numeric_types: %d rows in, %d rows out", before, len(result))
    return result


# ─────────────────────────────────────────────────────────────────────
# Orchestrator — chains all transforms
# ─────────────────────────────────────────────────────────────────────
def transform_sales_data(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full transform pipeline. This is what main.py calls."""
    logger.info("=== Transform pipeline start (input: %d rows) ===", len(df))
    df = clean_missing_values(df)
    df = remove_duplicates(df)
    df = standardize_dates(df)
    df = coerce_numeric_types(df)

    # Compute a derived column that Postgres will store
    df["total_amount"] = df.apply(
        lambda r: (r["unit_price"] * r["quantity"]), axis=1
    )

    logger.info("=== Transform pipeline done (output: %d rows) ===", len(df))
    return df


if __name__ == "__main__":
    # Smoke test: run extract → transform end-to-end
    from pathlib import Path

    from extract import extract_sales_data

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    project_root = Path(__file__).resolve().parent.parent
    csv_file = project_root / "data" / "raw" / "sales.csv"

    raw = extract_sales_data(csv_file)
    clean = transform_sales_data(raw)

    print("\n=== First 5 transformed rows ===")
    print(clean.head())
    print(f"\nShape: {clean.shape}")
    print(f"\nDtypes:\n{clean.dtypes}")
    print(f"\nDate range: {clean['order_date'].min()} → {clean['order_date'].max()}")
    print(f"Total revenue: {clean['total_amount'].sum():.2f}")
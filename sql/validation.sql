-- Issue #8: Data quality validation queries.
-- Run these after every pipeline execution to confirm data is loaded correctly.
-- Each query includes the expected result / pass criterion.

-- ────────────────────────────────────────────────────────────────────
-- 1. Row count sanity: table should have data
-- ────────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS total_rows FROM sales_orders;
-- Expect: > 0 (around 480-490 given our sample generator)

-- ────────────────────────────────────────────────────────────────────
-- 2. Null check: NOT NULL columns should never contain nulls
--    (belt-and-braces — schema already enforces this, but we verify)
-- ────────────────────────────────────────────────────────────────────
SELECT
    SUM(CASE WHEN order_id     IS NULL THEN 1 ELSE 0 END) AS null_order_id,
    SUM(CASE WHEN order_date   IS NULL THEN 1 ELSE 0 END) AS null_order_date,
    SUM(CASE WHEN customer_id  IS NULL THEN 1 ELSE 0 END) AS null_customer_id,
    SUM(CASE WHEN quantity     IS NULL THEN 1 ELSE 0 END) AS null_quantity,
    SUM(CASE WHEN unit_price   IS NULL THEN 1 ELSE 0 END) AS null_unit_price
FROM sales_orders;
-- Expect: all zeros

-- ────────────────────────────────────────────────────────────────────
-- 3. Duplicate check: order_id is PK, so this should be zero
-- ────────────────────────────────────────────────────────────────────
SELECT order_id, COUNT(*) AS occurrences
FROM sales_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
-- Expect: no rows returned

-- ────────────────────────────────────────────────────────────────────
-- 4. Business rule: quantity and price must be positive
--    (redundant with CHECK constraints, but useful for sampling drift)
-- ────────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS bad_quantity_rows FROM sales_orders WHERE quantity <= 0;
SELECT COUNT(*) AS bad_price_rows    FROM sales_orders WHERE unit_price < 0;
-- Expect: both zero

-- ────────────────────────────────────────────────────────────────────
-- 5. Derived-column integrity: total_amount = quantity * unit_price
-- ────────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS total_amount_mismatches
FROM sales_orders
WHERE ABS(total_amount - (quantity * unit_price)) > 0.01;
-- Expect: zero

-- ────────────────────────────────────────────────────────────────────
-- 6. Date range: sanity check the min/max order dates
-- ────────────────────────────────────────────────────────────────────
SELECT MIN(order_date) AS earliest, MAX(order_date) AS latest FROM sales_orders;
-- Expect: within 2026 (our sample data range)

-- ────────────────────────────────────────────────────────────────────
-- 7. Distribution: which regions and categories are represented?
--    Helps catch upstream ingestion bugs (e.g. only one region loaded)
-- ────────────────────────────────────────────────────────────────────
SELECT region, COUNT(*) AS row_count
FROM sales_orders
GROUP BY region
ORDER BY row_count DESC;

SELECT category, COUNT(*) AS row_count, SUM(total_amount) AS revenue
FROM sales_orders
GROUP BY category
ORDER BY revenue DESC;

-- ────────────────────────────────────────────────────────────────────
-- 8. Source vs destination count comparison (Issue #8 acceptance criterion)
--    Run this manually: compare the number below with `wc -l data/raw/sales.csv`
--    Note: DB count will be lower because bad rows were dropped in transform.
-- ────────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS loaded_rows FROM sales_orders;
-- Also run in shell: wc -l data/raw/sales.csv   → subtract 1 for the header

-- ────────────────────────────────────────────────────────────────────
-- 9. Pipeline runs: how many distinct load runs contributed to this table?
--    Useful for auditing "when was this data last touched?"
-- ────────────────────────────────────────────────────────────────────
SELECT
    load_run_id,
    COUNT(*)         AS rows_in_run,
    MIN(loaded_at)   AS run_started,
    MAX(loaded_at)   AS run_ended
FROM sales_orders
GROUP BY load_run_id
ORDER BY run_ended DESC;
-- Expect: one row per pipeline run
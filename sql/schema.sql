-- Issue #7: Sales orders schema
-- Idempotent DDL — safe to run on every pipeline start.
-- Types chosen for storage efficiency and correctness:
--   - order_id, sku, region etc. are VARCHAR with realistic max lengths
--   - order_date is DATE (not TIMESTAMP — we don't care about time-of-day)
--   - unit_price/total_amount are NUMERIC(10,2) — money must never be a float
--   - load_run_id lets us trace every row back to the pipeline run that wrote it

CREATE TABLE IF NOT EXISTS sales_orders (
    order_id        VARCHAR(20)     PRIMARY KEY,
    order_date      DATE            NOT NULL,
    customer_id     VARCHAR(20)     NOT NULL,
    sku             VARCHAR(20)     NOT NULL,
    product_name    VARCHAR(100)    NOT NULL,
    category        VARCHAR(50)     NOT NULL,
    region          VARCHAR(20)     NOT NULL,
    channel         VARCHAR(20)     NOT NULL,
    quantity        INTEGER         NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10, 2)  NOT NULL CHECK (unit_price >= 0),
    total_amount    NUMERIC(12, 2)  NOT NULL CHECK (total_amount >= 0),

    -- Pipeline observability
    load_run_id     VARCHAR(32)     NOT NULL,
    loaded_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Indexes for the queries analytics people will actually write.
-- Skipping the ones we don't need saves write throughput.
CREATE INDEX IF NOT EXISTS idx_sales_orders_order_date ON sales_orders (order_date);
CREATE INDEX IF NOT EXISTS idx_sales_orders_customer   ON sales_orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_orders_region     ON sales_orders (region);
CREATE INDEX IF NOT EXISTS idx_sales_orders_load_run   ON sales_orders (load_run_id);
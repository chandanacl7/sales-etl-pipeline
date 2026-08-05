"""One-off helper to create a realistic sales.csv for development.

Not part of the ETL pipeline — just seeds data/raw/sales.csv so the
Extract/Transform/Load scripts have something to work on.

Deliberately injects messy data so later ETL stages have real work:
  - ~5% rows with missing dates or regions  (tests Issue #4: cleaning)
  - ~2% duplicate rows                      (tests Issue #5: dedup)
  - mixed date formats across rows          (tests Issue #6: date transform)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT = RAW_DIR / "sales.csv"

PRODUCTS = [
    ("SKU-001", "Wireless Mouse", "Electronics", 29.99),
    ("SKU-002", "Mechanical Keyboard", "Electronics", 129.00),
    ("SKU-003", "USB-C Hub", "Electronics", 45.50),
    ("SKU-004", "Standing Desk", "Furniture", 399.00),
    ("SKU-005", "Ergonomic Chair", "Furniture", 249.00),
    ("SKU-006", "Notebook A5", "Stationery", 6.75),
    ("SKU-007", "Gel Pen Pack", "Stationery", 3.20),
    ("SKU-008", "Coffee Beans 1kg", "Grocery", 18.90),
]
REGIONS = ["APAC", "EMEA", "AMER", "LATAM"]
CHANNELS = ["online", "retail", "wholesale"]


def main(n_rows: int = 500, seed: int = 42) -> None:
    random.seed(seed)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)

    rows = []
    for i in range(1, n_rows + 1):
        sku, name, category, price = random.choice(PRODUCTS)
        order_date = start + timedelta(days=random.randint(0, 210))

        # Rotate date formats so Issue #6 (date transform) has real work
        if i % 3 == 0:
            date_str = order_date.strftime("%d/%m/%Y")
        elif i % 3 == 1:
            date_str = order_date.strftime("%Y-%m-%d")
        else:
            date_str = order_date.strftime("%m-%d-%Y")

        dirty = random.random() < 0.05
        rows.append({
            "order_id":     f"ORD-{i:05d}",
            "order_date":   date_str if not dirty else "",   # missing date
            "customer_id":  f"CUST-{random.randint(1, 80):04d}",
            "sku":          sku,
            "product_name": name,
            "category":     category,
            "region":       random.choice(REGIONS) if not dirty else "",  # missing region
            "channel":      random.choice(CHANNELS),
            "quantity":     random.randint(1, 10),
            "unit_price":   f"{price:.2f}",
        })

    # Inject duplicates (~2%) to test Issue #5
    for _ in range(int(n_rows * 0.02)):
        rows.append(random.choice(rows).copy())

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
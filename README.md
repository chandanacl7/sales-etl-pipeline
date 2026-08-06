cat > README.md << 'EOF'
# Sales ETL Pipeline

A production-shaped ETL pipeline that ingests raw sales data from CSV,
cleans and normalizes it, and loads it into PostgreSQL for analytics.

## Tech stack

| Layer          | Choice                    | Why                                            |
|----------------|---------------------------|------------------------------------------------|
| Language       | Python 3.11+              | Ecosystem for data work                        |
| Data handling  | pandas                    | DataFrame primitives, mature ecosystem         |
| Database       | PostgreSQL 16             | ACID, NUMERIC for money, ON CONFLICT UPSERT    |
| DB driver      | SQLAlchemy + psycopg2     | Connection pooling, DB-agnostic SQL            |
| Config         | python-dotenv             | Credentials via .env, never in code            |
| Logging        | stdlib logging + rotate   | File + console, per-run traceability           |
| Testing        | pytest                    | Idiomatic Python testing                       |

## Architecture

\`\`\`
data/raw/sales.csv
        |
        v
+-------------------+
| extract.py        |  Read CSV, validate schema
+-------------------+
        |  DataFrame (all strings)
        v
+-------------------+
| transform.py      |  Clean nulls, dedup, parse dates, coerce types
+-------------------+
        |  DataFrame (typed, validated)
        v
+-------------------+
| load.py           |  UPSERT into PostgreSQL (idempotent)
+-------------------+
        |
        v
   sales_orders table
        |
        v
   sql/validation.sql  <- run to verify data quality
\`\`\`

Orchestrated by main.py with structured error handling and per-run logging.

## Folder structure

\`\`\`
sales-etl-pipeline/
├── data/
│   ├── raw/                     Source CSVs land here
│   └── processed/               (reserved for future intermediate outputs)
├── scripts/
│   ├── extract.py               Issue #3
│   ├── transform.py             Issues #4, #5, #6
│   ├── load.py                  Issue #7
│   ├── logger_config.py         Issue #9
│   ├── main.py                  Issues #10, #12 (orchestrator)
│   └── generate_sample_data.py  Dev helper — creates a realistic CSV
├── sql/
│   ├── schema.sql               DDL for sales_orders
│   └── validation.sql           Issue #8 data quality checks
├── logs/                        Runtime logs (gitignored)
├── tests/                       pytest tests
├── .env                         DB credentials (gitignored — see .env.example)
├── requirements.txt             Pinned dependencies
└── README.md
\`\`\`

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 16 (\`brew install postgresql@16\`)
- Git

### Setup

\`\`\`bash
# 1. Clone and enter
git clone https://github.com/chandanacl7/sales-etl-pipeline.git
cd sales-etl-pipeline

# 2. Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Start PostgreSQL
brew services start postgresql@16

# 4. Create database and user
psql postgres <<SQL
CREATE USER sales_user WITH PASSWORD 'sales_pass';
CREATE DATABASE sales OWNER sales_user;
GRANT ALL PRIVILEGES ON DATABASE sales TO sales_user;
SQL

# 5. Configure environment
cp .env.example .env

# 6. Generate sample data
python scripts/generate_sample_data.py
\`\`\`

## Usage

Run the full pipeline:

\`\`\`bash
python scripts/main.py
\`\`\`

With options:

\`\`\`bash
python scripts/main.py --csv data/raw/sales.csv --log-level DEBUG
\`\`\`

Run stages individually:

\`\`\`bash
python scripts/extract.py
python scripts/transform.py
python scripts/load.py
\`\`\`

Validate loaded data:

\`\`\`bash
psql -U sales_user -d sales -h localhost -f sql/validation.sql
\`\`\`

## Exit codes

| Code | Meaning              |
|------|----------------------|
| 0    | Success              |
| 10   | Extract failure      |
| 20   | Transform failure    |
| 30   | Load failure         |
| 99   | Unexpected error     |
| 130  | Interrupted (Ctrl-C) |

## Data model

Table: sales_orders (see sql/schema.sql)

| Column        | Type            | Notes                                |
|---------------|-----------------|--------------------------------------|
| order_id      | VARCHAR(20) PK  | Business key, idempotency target     |
| order_date    | DATE            | Parsed from mixed formats            |
| customer_id   | VARCHAR(20)     |                                      |
| sku           | VARCHAR(20)     |                                      |
| product_name  | VARCHAR(100)    |                                      |
| category      | VARCHAR(50)     |                                      |
| region        | VARCHAR(20)     | Missing values imputed as 'UNKNOWN'  |
| channel       | VARCHAR(20)     |                                      |
| quantity      | INTEGER         | CHECK > 0                            |
| unit_price    | NUMERIC(10, 2)  | CHECK >= 0                           |
| total_amount  | NUMERIC(12, 2)  | Derived: quantity × unit_price       |
| load_run_id   | VARCHAR(32)     | Traces row to a pipeline run         |
| loaded_at     | TIMESTAMPTZ     | When this row was upserted           |

## Idempotency

The pipeline is safe to re-run on the same input. Loads use
\`INSERT ... ON CONFLICT (order_id) DO UPDATE\`, so repeated runs
converge on the same table state.

## Testing

\`\`\`bash
pytest -v
\`\`\`

## Roadmap

- Structured JSON logs for log aggregators
- Airflow / Prefect DAG instead of ad-hoc cron
- Quarantine table for rejected rows instead of dropping
- dbt models on top of sales_orders
- GitHub Actions CI: lint + tests on every PR
EOF
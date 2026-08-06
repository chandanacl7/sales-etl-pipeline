"""Issues #10, #12: ETL pipeline entry point.

Orchestrates extract → transform → load with structured error handling.
Each stage's exception type maps to a distinct exit code so schedulers
and alerting systems can react appropriately.

Exit codes:
    0   success
    10  extract failure (source file missing, malformed)
    20  transform failure (unexpected data quality issue)
    30  load failure (DB unavailable, schema mismatch)
    99  unknown error (bug — investigate)
    130 interrupted (Ctrl-C)

Usage:
    python scripts/main.py
    python scripts/main.py --csv data/raw/sales.csv --log-level DEBUG
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from extract import extract_sales_data
from load import LoadError, apply_schema, get_engine, load_sales_data
from logger_config import configure_logging
from transform import transform_sales_data


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    project_root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Sales ETL pipeline")
    p.add_argument(
        "--csv",
        type=Path,
        default=project_root / "data" / "raw" / "sales.csv",
        help="Path to the raw sales CSV",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level",
    )
    return p.parse_args()


def run_pipeline(csv_path: Path, run_id: str) -> None:
    """Run the ETL end-to-end. Raises on failure; success is silent."""
    log = logging.getLogger("main")
    start = time.perf_counter()

    log.info("=" * 60)
    log.info("Pipeline start | run_id=%s | csv=%s", run_id, csv_path)
    log.info("=" * 60)

    # --- Extract ---
    t0 = time.perf_counter()
    raw = extract_sales_data(csv_path)
    log.info(
        "Stage: extract done in %.2fs (%d rows)",
        time.perf_counter() - t0,
        len(raw),
    )

    # --- Transform ---
    t0 = time.perf_counter()
    clean = transform_sales_data(raw)
    log.info(
        "Stage: transform done in %.2fs (%d rows)",
        time.perf_counter() - t0,
        len(clean),
    )

    # --- Load ---
    t0 = time.perf_counter()
    engine = get_engine()
    apply_schema(engine)
    result = load_sales_data(clean, engine, run_id=run_id)
    log.info(
        "Stage: load done in %.2fs (%d rows upserted)",
        time.perf_counter() - t0,
        result["rows_upserted"],
    )

    elapsed = time.perf_counter() - start
    log.info("=" * 60)
    log.info("Pipeline success | run_id=%s | %.2fs total", run_id, elapsed)
    log.info("=" * 60)


def main() -> int:
    """Entry point. Maps exception types to exit codes."""
    args = parse_args()
    run_id = configure_logging(args.log_level)
    log = logging.getLogger("main")

    try:
        run_pipeline(args.csv, run_id)
        return 0

    except FileNotFoundError as e:
        log.error("EXTRACT FAILED — source not found: %s", e)
        return 10
    except ValueError as e:
        # ValueError is what extract raises for empty/malformed CSV
        log.error("EXTRACT FAILED — bad input data: %s", e)
        return 10

    except LoadError as e:
        log.error("LOAD FAILED: %s", e)
        return 30

    except KeyboardInterrupt:
        log.warning("Pipeline interrupted by user")
        return 130

    except Exception as e:  # pylint: disable=broad-except
        # Anything we didn't anticipate. Log with traceback for debugging.
        log.exception("PIPELINE FAILED with unexpected error: %s", e)
        return 99


if __name__ == "__main__":
    sys.exit(main())
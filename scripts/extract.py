"""Issue #3: Extract sales data from CSV file.

Reads the raw sales CSV into a pandas DataFrame with proper error handling.
Kept intentionally "dumb": no type conversion or cleaning here — that's the
transform stage's job. Extract's only responsibility is:
  1. Verify the file exists
  2. Read it safely
  3. Confirm it has content
  4. Return a DataFrame
"""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def extract_sales_data(csv_path: Path) -> pd.DataFrame:
    """Read the sales CSV and return a DataFrame.

    Args:
        csv_path: Path to the raw CSV file.

    Returns:
        DataFrame with the raw sales rows (all columns as strings).

    Raises:
        FileNotFoundError: The CSV file does not exist at the given path.
        ValueError:        The file exists but is empty or unparseable.
    """
    logger.info("Extracting data from %s", csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        # dtype=str: keep everything as strings for now.
        # Pandas type inference silently turns bad rows into NaN — reading as
        # str means bad values survive to the transform stage where they're
        # validated explicitly.
        df = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            na_values=[""],
        )
    except pd.errors.EmptyDataError as e:
        raise ValueError(f"CSV file is empty: {csv_path}") from e
    except pd.errors.ParserError as e:
        raise ValueError(f"Could not parse CSV {csv_path}: {e}") from e

    if df.empty:
        raise ValueError(f"CSV has header but no data rows: {csv_path}")

    logger.info("Extracted %d rows across %d columns", len(df), len(df.columns))
    return df


if __name__ == "__main__":
    # Smoke test — run this file directly to confirm extract works end-to-end
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    project_root = Path(__file__).resolve().parent.parent
    csv_file = project_root / "data" / "raw" / "sales.csv"

    df = extract_sales_data(csv_file)

    print("\n=== First 5 rows ===")
    print(df.head())
    print(f"\nShape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
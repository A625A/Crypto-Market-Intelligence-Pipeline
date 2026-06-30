"""
Data ingestion module.
Raw data should be saved into data/raw/ and never modified directly.
"""

from pathlib import Path
import pandas as pd

RAW_DATA_DIR = Path("data/raw")


def load_raw_data(filename: str) -> pd.DataFrame:
    """Load a raw CSV file from data/raw/."""
    path = RAW_DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Raw data file not found: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    print("Ingestion module ready.")

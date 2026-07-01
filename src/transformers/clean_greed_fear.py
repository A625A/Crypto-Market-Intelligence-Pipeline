"""
Validate and clean raw Crypto Fear & Greed Index data.

This module prepares Alternative.me index records by normalizing timestamps,
numeric scores, and classifications before saving analysis-ready sentiment
features.
"""

import json
import logging
from pathlib import Path

import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


RAW_PATH = Path("data/raw/fear_greed_raw.json")
CLEAN_PATH = Path("data/processed/fear_greed_clean.csv")


def clean_fear_greed(raw_path=RAW_PATH, output_path=CLEAN_PATH) -> pd.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    with open(raw_path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    records = raw_data.get("data", [])

    if not records:
        raise RuntimeError("No Fear & Greed records found in raw file.")

    df = pd.DataFrame(records)
    original_rows = len(df)

    logger.info("Loaded raw Fear & Greed data: %s rows", original_rows)

    required_columns = [
        "value",
        "value_classification",
        "timestamp",
    ]

    missing_columns = set(required_columns) - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    df = df[required_columns].copy()

    df["fear_greed_value"] = pd.to_numeric(df["value"], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")

    df["date"] = pd.to_datetime(
        df["timestamp"],
        unit="s",
        utc=True,
        errors="coerce"
    ).dt.date

    df["fear_greed_classification"] = (
        df["value_classification"]
        .astype("string")
        .str.strip()
    )

    df = df.drop(columns=["value", "value_classification", "timestamp"])

    before_dropna = len(df)

    df = df.dropna(
        subset=[
            "date",
            "fear_greed_value",
            "fear_greed_classification",
        ]
    )

    logger.info(
        "Dropped %s rows with missing required values",
        before_dropna - len(df)
    )

    valid_classifications = {
        "Extreme Fear",
        "Fear",
        "Neutral",
        "Greed",
        "Extreme Greed",
    }

    valid_rows = (
        df["fear_greed_value"].between(0, 100)
        & df["fear_greed_classification"].isin(valid_classifications)
    )

    invalid_count = (~valid_rows).sum()

    if invalid_count:
        logger.warning("Dropping %s invalid Fear & Greed rows", invalid_count)

    df = df.loc[valid_rows].copy()

    if df.empty:
        raise RuntimeError("No rows left after validating Fear & Greed data.")

    duplicate_count = df.duplicated(subset=["date"]).sum()

    if duplicate_count:
        logger.warning("Dropping %s duplicate Fear & Greed date rows", duplicate_count)

    df = df.drop_duplicates(subset=["date"], keep="last")

    df = df.sort_values("date").reset_index(drop=True)

    if df.empty:
        raise RuntimeError("No rows left after cleaning Fear & Greed data.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)

    logger.info("Cleaned rows: %s -> %s", original_rows, len(df))
    logger.info("Saved cleaned Fear & Greed data to %s", output_path)
    logger.info(
        "Fear & Greed date range: %s -> %s",
        df["date"].min(),
        df["date"].max()
    )

    return df


if __name__ == "__main__":
    clean_fear_greed()
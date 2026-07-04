"""
Validate and clean raw FRED macroeconomic data.

This module pivots selected FRED series into daily macro feature columns,
forward-fills lower-frequency observations, applies lagging to delayed-release
monthly macro indicators, and saves analysis-ready macro features for merging
with crypto market data.
"""

import json
import logging
from pathlib import Path

import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


RAW_PATH = Path("data/raw/fred_macro_raw.json")
CLEAN_PATH = Path("data/processed/fred_macro_clean.csv")


LAGGED_MACRO_COLUMNS = [
    "consumer_price_index",
    "unemployment_rate",
]

LAG_DAYS = 30


def clean_fred_macro(
    raw_path=RAW_PATH,
    output_path=CLEAN_PATH,
) -> pd.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    with open(raw_path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    series_data = raw_data.get("series", {})

    if not series_data:
        raise RuntimeError("No FRED macro series found in raw file.")

    cleaned_frames = []
    output_columns = ["date"]
    feature_names = set()

    for series_id, payload in series_data.items():
        feature_name = str(payload.get("feature_name", "")).strip()

        if not feature_name:
            feature_name = str(series_id).strip().lower()

        if feature_name in feature_names:
            raise ValueError(f"Duplicate FRED feature name found: {feature_name}")

        feature_names.add(feature_name)
        output_columns.append(feature_name)

        observations = payload.get("data", {}).get("observations", [])

        if not observations:
            raise ValueError(f"Missing FRED observations for {series_id}")

        series_df = pd.DataFrame(observations)

        required_columns = [
            "date",
            "value",
        ]

        missing_columns = set(required_columns) - set(series_df.columns)

        if missing_columns:
            raise ValueError(
                "Missing required FRED observation columns "
                f"for {series_id}: {sorted(missing_columns)}"
            )

        series_df = series_df[required_columns].copy()

        series_df["date"] = pd.to_datetime(
            series_df["date"],
            utc=True,
            errors="coerce",
        ).dt.date

        series_df[feature_name] = pd.to_numeric(
            series_df["value"].replace(".", pd.NA),
            errors="coerce",
        )

        series_df = series_df[["date", feature_name]]

        before_dropna = len(series_df)

        series_df = series_df.dropna(subset=["date", feature_name])

        logger.info(
            "Dropped %s missing FRED observations for %s",
            before_dropna - len(series_df),
            series_id,
        )

        if series_df.empty:
            raise RuntimeError(f"No valid FRED observations left for {series_id}.")

        duplicate_count = series_df.duplicated(subset=["date"]).sum()

        if duplicate_count:
            logger.warning(
                "Dropping %s duplicate FRED date rows for %s",
                duplicate_count,
                series_id,
            )

        series_df = series_df.drop_duplicates(subset=["date"], keep="last")
        series_df = series_df.sort_values("date").reset_index(drop=True)

        cleaned_frames.append(series_df)

    df = cleaned_frames[0]

    for series_df in cleaned_frames[1:]:
        df = df.merge(series_df, on="date", how="outer")

    original_rows = len(df)

    logger.info("Loaded raw FRED macro data: %s observation dates", original_rows)

    today_utc = pd.Timestamp.now(tz="UTC").date()

    before_incomplete = len(df)

    df = df[df["date"] < today_utc].copy()

    logger.info(
        "Dropped %s incomplete current-day FRED rows",
        before_incomplete - len(df),
    )

    if df.empty:
        raise RuntimeError("No FRED rows left after dropping incomplete dates.")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.sort_values("date")

    daily_index = pd.date_range(
        start=df["date"].min(),
        end=df["date"].max(),
        freq="D",
    )

    df = df.set_index("date").reindex(daily_index).ffill()
    df.index.name = "date"
    df = df.reset_index()

    for column in LAGGED_MACRO_COLUMNS:
        if column in df.columns:
            df[column] = df[column].shift(LAG_DAYS)
            logger.info(
                "Applied %s-day lag to delayed macro feature: %s",
                LAG_DAYS,
                column,
            )

    df["date"] = df["date"].dt.date

    feature_columns = output_columns[1:]

    before_dropna = len(df)

    df = df.dropna(subset=feature_columns)

    logger.info(
        "Dropped %s rows with missing required FRED feature values",
        before_dropna - len(df),
    )

    if df.empty:
        raise RuntimeError("No rows left after cleaning FRED macro data.")

    df = df[output_columns].reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)

    logger.info("Cleaned FRED rows: %s -> %s", original_rows, len(df))
    logger.info("Saved cleaned FRED macro data to %s", output_path)
    logger.info(
        "FRED macro date range: %s -> %s",
        df["date"].min(),
        df["date"].max(),
    )
    logger.info(
        "FRED macro columns: %s",
        feature_columns,
    )

    return df


if __name__ == "__main__":
    clean_fred_macro()
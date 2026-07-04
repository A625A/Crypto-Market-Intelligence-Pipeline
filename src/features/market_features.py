"""
Create market features from cleaned CoinGecko market chart data.

This module creates market cap, volume, liquidity, and estimated supply features
from CoinGecko daily market chart data.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


INPUT_PATH = Path("data/processed/coingecko_market_chart_clean.csv")
OUTPUT_PATH = Path("data/processed/features/market_features.parquet")


def add_market_features(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("date").copy()

    price = group["coingecko_price_usd"]
    market_cap = group["coingecko_market_cap_usd"]
    total_volume = group["coingecko_total_volume_usd"]

    group["market_cap_usd"] = market_cap
    group["total_volume_usd"] = total_volume

    group["market_cap_change_1d"] = market_cap.pct_change(1)
    group["total_volume_change_1d"] = total_volume.pct_change(1)

    group["volume_to_market_cap"] = total_volume / market_cap.replace(0, pd.NA)

    group["estimated_circulating_supply"] = (
        market_cap / price.replace(0, pd.NA)
    )

    return group


def create_market_features(
    input_path=INPUT_PATH,
    output_path=OUTPUT_PATH,
) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(f"Clean CoinGecko file not found: {input_path}")

    df = pd.read_csv(input_path)
    original_rows = len(df)

    logger.info("Loaded cleaned CoinGecko data: %s rows", original_rows)

    required_columns = [
        "symbol",
        "coingecko_id",
        "date",
        "coingecko_price_usd",
        "coingecko_market_cap_usd",
        "coingecko_total_volume_usd",
    ]

    missing_columns = set(required_columns) - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    df["symbol"] = df["symbol"].astype("string").str.strip().str.upper()
    df["symbol"] = df["symbol"].replace("", pd.NA)

    df["coingecko_id"] = df["coingecko_id"].astype("string").str.strip()
    df["coingecko_id"] = df["coingecko_id"].replace("", pd.NA)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    numeric_columns = [
        "coingecko_price_usd",
        "coingecko_market_cap_usd",
        "coingecko_total_volume_usd",
    ]

    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")

    before_dropna = len(df)

    df = df.dropna(subset=required_columns)

    logger.info(
        "Dropped %s rows with missing required values",
        before_dropna - len(df),
    )

    if df.empty:
        raise RuntimeError("No rows left after loading CoinGecko data.")

    duplicate_count = df.duplicated(subset=["symbol", "date"]).sum()

    if duplicate_count:
        logger.warning(
            "Dropping %s duplicate symbol/date rows",
            duplicate_count,
        )

    df = df.drop_duplicates(subset=["symbol", "date"], keep="last")

    valid_rows = (
        (df["coingecko_price_usd"] > 0)
        & (df["coingecko_market_cap_usd"] > 0)
        & (df["coingecko_total_volume_usd"] >= 0)
    )

    invalid_count = (~valid_rows).sum()

    if invalid_count:
        logger.warning("Dropping %s invalid CoinGecko market rows", invalid_count)

    df = df.loc[valid_rows].copy()

    if df.empty:
        raise RuntimeError("No rows left after validating CoinGecko data.")

    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    feature_frames = []

    for symbol, group in df.groupby("symbol", sort=False):
        group_features = add_market_features(group)
        group_features["symbol"] = symbol
        feature_frames.append(group_features)

    feature_df = pd.concat(feature_frames, ignore_index=True)

    feature_columns = [
        "market_cap_usd",
        "market_cap_change_1d",
        "total_volume_usd",
        "total_volume_change_1d",
        "volume_to_market_cap",
        "estimated_circulating_supply",
    ]

    numeric_values = feature_df.select_dtypes(include="number").to_numpy()
    infinite_count = np.isinf(numeric_values).sum()

    if infinite_count:
        logger.warning("Replacing %s infinite market feature values", infinite_count)

    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)

    before_feature_dropna = len(feature_df)

    feature_df = feature_df.dropna(subset=feature_columns)

    logger.info(
        "Dropped %s rows with incomplete market features",
        before_feature_dropna - len(feature_df),
    )

    if feature_df.empty:
        raise RuntimeError("No rows left after creating market features.")

    output_columns = [
        "symbol",
        "coingecko_id",
        "date",
    ] + feature_columns

    feature_df = feature_df[output_columns].reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    feature_df.to_parquet(output_path, index=False)

    logger.info(
        "Created market features: %s -> %s rows",
        original_rows,
        len(feature_df),
    )
    logger.info("Saved market features to %s", output_path)
    logger.info(
        "Market feature rows per symbol:\n%s",
        feature_df.groupby("symbol")["date"].agg(["min", "max", "count"]),
    )

    return feature_df


if __name__ == "__main__":
    create_market_features()

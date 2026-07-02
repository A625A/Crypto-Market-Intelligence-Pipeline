"""
Validate and clean raw CoinGecko market chart data.

This module aligns daily price, market cap, and total volume records by
timestamp before saving analysis-ready market features.
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


RAW_PATH = Path("data/raw/coingecko_market_chart_raw.json")
CLEAN_PATH = Path("data/processed/coingecko_market_chart_clean.csv")

METRIC_COLUMNS = {
    "prices": "coingecko_price_usd",
    "market_caps": "coingecko_market_cap_usd",
    "total_volumes": "coingecko_total_volume_usd",
}


def clean_coingecko_market_chart(
    raw_path=RAW_PATH,
    output_path=CLEAN_PATH,
) -> pd.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    with open(raw_path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    if not raw_data:
        raise RuntimeError("No CoinGecko market chart records found in raw file.")

    cleaned_frames = []

    for symbol, payload in raw_data.items():
        coingecko_id = str(payload.get("coingecko_id", "")).strip()
        market_data = payload.get("data", {})

        missing_metrics = set(METRIC_COLUMNS) - set(market_data)

        if missing_metrics:
            raise ValueError(
                "Missing required CoinGecko metrics "
                f"for {symbol}: {sorted(missing_metrics)}"
            )

        metric_frames = []

        for metric_name, output_column in METRIC_COLUMNS.items():
            metric_frame = pd.DataFrame(
                market_data[metric_name],
                columns=["timestamp", output_column],
            )
            metric_frame["timestamp"] = pd.to_numeric(
                metric_frame["timestamp"],
                errors="coerce",
            )
            metric_frame[output_column] = pd.to_numeric(
                metric_frame[output_column],
                errors="coerce",
            )
            metric_frames.append(metric_frame)

        coin_df = metric_frames[0]

        for metric_frame in metric_frames[1:]:
            coin_df = coin_df.merge(metric_frame, on="timestamp", how="inner")

        coin_df["symbol"] = str(symbol).strip().upper()
        coin_df["coingecko_id"] = coingecko_id
        coin_df["date"] = pd.to_datetime(
            coin_df["timestamp"],
            unit="ms",
            utc=True,
            errors="coerce",
        ).dt.date

        cleaned_frames.append(coin_df)

    df = pd.concat(cleaned_frames, ignore_index=True)
    original_rows = len(df)

    logger.info("Loaded raw CoinGecko market chart data: %s rows", original_rows)

    output_columns = [
        "symbol",
        "coingecko_id",
        "date",
        "coingecko_price_usd",
        "coingecko_market_cap_usd",
        "coingecko_total_volume_usd",
    ]

    df = df[output_columns]

    today_utc = pd.Timestamp.now(tz="UTC").date()

    before_incomplete = len(df)

    df = df[df["date"] < today_utc].copy()

    logger.info(
        "Dropped %s incomplete current-day CoinGecko rows",
        before_incomplete - len(df),
    )

    before_dropna = len(df)

    df = df.dropna(subset=output_columns)

    logger.info(
        "Dropped %s rows with missing required values",
        before_dropna - len(df),
    )

    valid_rows = (
        (df["symbol"] != "")
        & (df["coingecko_id"] != "")
        & (df["coingecko_price_usd"] > 0)
        & (df["coingecko_market_cap_usd"] >= 0)
        & (df["coingecko_total_volume_usd"] >= 0)
    )

    invalid_count = (~valid_rows).sum()

    if invalid_count:
        logger.warning("Dropping %s invalid CoinGecko rows", invalid_count)

    df = df.loc[valid_rows].copy()

    if df.empty:
        raise RuntimeError("No rows left after validating CoinGecko data.")

    duplicate_count = df.duplicated(subset=["symbol", "date"]).sum()

    if duplicate_count:
        logger.warning("Dropping %s duplicate CoinGecko date rows", duplicate_count)

    df = df.drop_duplicates(subset=["symbol", "date"], keep="last")

    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    if df.empty:
        raise RuntimeError("No rows left after cleaning CoinGecko data.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)

    logger.info("Cleaned rows: %s -> %s", original_rows, len(df))
    logger.info("Saved cleaned CoinGecko data to %s", output_path)
    logger.info(
        "CoinGecko rows per symbol:\n%s",
        df.groupby("symbol")["date"].agg(["min", "max", "count"]),
    )

    return df


if __name__ == "__main__":
    clean_coingecko_market_chart()

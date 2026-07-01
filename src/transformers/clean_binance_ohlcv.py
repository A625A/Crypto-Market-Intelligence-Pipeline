"""
Clean Binance OHLCV raw data.
"""

import logging
from pathlib import Path

import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


RAW_PATH = Path("data/raw/binance_ohlcv_raw.csv")
CLEAN_PATH = Path("data/processed/binance_ohlcv_clean.csv")

def clean_binance_ohlcv(raw_path=RAW_PATH, output_path=CLEAN_PATH) -> pd.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    df = pd.read_csv(raw_path)
    original_rows = len(df)

    logger.info("Loaded raw Binance data: %s rows", original_rows)

    required_columns = [
        "symbol",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    ]

    missing_columns = set(required_columns) - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    df["symbol"] = df["symbol"].astype("string").str.strip().str.upper()
    df["symbol"] = df["symbol"].replace("", pd.NA)

    df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, errors="coerce")

    now_utc = pd.Timestamp.now(tz="UTC")

    before_incomplete = len(df)

    df = df[df["close_time"] <= now_utc].copy()

    logger.info(
        "Dropped %s incomplete candles",
        before_incomplete - len(df)
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    ]

    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")

    before_dropna = len(df)

    df = df.dropna(subset=required_columns)

    logger.info(
        "Dropped %s rows with missing required values",
        before_dropna - len(df)
    )

    if df.empty:
        raise RuntimeError("No rows left after dropping missing required values.")

    duplicate_count = df.duplicated(subset=["symbol", "open_time"]).sum()

    if duplicate_count:
        logger.warning(
            "Dropping %s duplicate symbol/open_time rows",
            duplicate_count
        )

    df = df.drop_duplicates(subset=["symbol", "open_time"], keep="last")

    price_columns = [
        "open",
        "high",
        "low",
        "close",
    ]

    non_negative_columns = [
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    ]

    valid_rows = (
        (df["close_time"] > df["open_time"])
        & (df[price_columns] > 0).all(axis=1)
        & (df[non_negative_columns] >= 0).all(axis=1)
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & (df["high"] >= df["low"])
    )

    invalid_count = (~valid_rows).sum()

    if invalid_count:
        logger.warning("Dropping %s invalid OHLCV rows", invalid_count)

    df = df.loc[valid_rows].sort_values(
        ["symbol", "open_time"]
    ).reset_index(drop=True)

    if df.empty:
        raise RuntimeError("All rows were removed during OHLCV validation.")

    gap_rows = df.assign(
        previous_open_time=df.groupby("symbol")["open_time"].shift()
    )

    gap_rows = gap_rows[
        gap_rows["previous_open_time"].notna()
        & (
            (gap_rows["open_time"] - gap_rows["previous_open_time"])
            != pd.Timedelta(days=1)
        )
    ]

    if not gap_rows.empty:
        logger.warning(
            "Found %s non-daily time gaps. Inspect before filling.",
            len(gap_rows)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)

    logger.info("Cleaned rows: %s -> %s", original_rows, len(df))
    logger.info("Saved cleaned data to %s", output_path)
    logger.info(
        "Rows per symbol:\n%s",
        df.groupby("symbol")["open_time"].agg(["min", "max", "count"])
    )

    return df


if __name__ == "__main__":
    clean_binance_ohlcv()
"""
Create daily candle features from cleaned Binance OHLCV data.

This module creates returns, volatility, moving average, candle-shape, and
volume-based features from daily OHLCV candles.
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


INPUT_PATH = Path("data/processed/binance_ohlcv_clean.csv")
OUTPUT_PATH = Path("data/processed/features/candle_features.parquet")


def add_candle_features(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("open_time").copy()

    close = group["close"]
    open_price = group["open"]
    high = group["high"]
    low = group["low"]
    volume = group["volume"]
    quote_volume = group["quote_asset_volume"]
    trades = group["number_of_trades"]
    next_close = close.shift(-1)

    # Return features
    group["return_1d"] = close.pct_change(1)
    group["return_3d"] = close.pct_change(3)
    group["return_7d"] = close.pct_change(7)
    group["return_14d"] = close.pct_change(14)
    group["return_30d"] = close.pct_change(30)

    group["log_return_1d"] = np.log(close / close.shift(1))

    # Volatility features
    group["volatility_12d"] = group["log_return_1d"].rolling(window=12).std()
    group["volatility_24d"] = group["log_return_1d"].rolling(window=24).std()
    group["volatility_72d"] = group["log_return_1d"].rolling(window=72).std()

    # Moving-average features
    group["sma_12d"] = close.rolling(window=12).mean()
    group["sma_24d"] = close.rolling(window=24).mean()
    group["sma_72d"] = close.rolling(window=72).mean()

    group["ema_12d"] = close.ewm(span=12, adjust=False).mean()
    group["ema_24d"] = close.ewm(span=24, adjust=False).mean()
    group["ema_72d"] = close.ewm(span=72, adjust=False).mean()

    # Candle-shape features
    candle_max = pd.concat([open_price, close], axis=1).max(axis=1)
    candle_min = pd.concat([open_price, close], axis=1).min(axis=1)

    group["high_low_range"] = (high - low) / close
    group["open_close_range"] = (close - open_price) / open_price
    group["body_size"] = (close - open_price).abs() / open_price
    group["upper_wick"] = (high - candle_max) / open_price
    group["lower_wick"] = (candle_min - low) / open_price

    # Volume features
    group["volume_change_1d"] = volume.pct_change(1)
    group["volume_sma_24d"] = volume.rolling(window=24).mean()

    volume_rolling_mean = volume.rolling(window=24).mean()
    volume_rolling_std = volume.rolling(window=24).std()

    group["volume_zscore_24d"] = (
        (volume - volume_rolling_mean) / volume_rolling_std.replace(0, pd.NA)
    )

    group["quote_volume_change_1d"] = quote_volume.pct_change(1)
    group["trade_count_change_1d"] = trades.pct_change(1)

    group["target_close_next_1d"] = next_close
    group["target_return_next_1d"] = (next_close / close) - 1

    return group


def create_candle_features(
    input_path=INPUT_PATH,
    output_path=OUTPUT_PATH,
) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(f"Clean Binance file not found: {input_path}")

    df = pd.read_csv(input_path)

    original_rows = len(df)

    logger.info("Loaded cleaned Binance OHLCV data: %s rows", original_rows)

    required_columns = [
        "symbol",
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
    ]

    missing_columns = set(required_columns) - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    df["symbol"] = df["symbol"].astype("string").str.strip().str.upper()
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
    ]

    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")

    before_dropna = len(df)

    df = df.dropna(subset=required_columns)

    logger.info(
        "Dropped %s rows with missing required values",
        before_dropna - len(df),
    )

    if df.empty:
        raise RuntimeError("No rows left after loading clean OHLCV data.")

    df = df.sort_values(["symbol", "open_time"]).reset_index(drop=True)

    feature_frames = []

    for symbol, group in df.groupby("symbol", sort=False):
        group_features = add_candle_features(group)
        group_features["symbol"] = symbol
        feature_frames.append(group_features)

    feature_df = pd.concat(feature_frames, ignore_index=True)

    feature_columns = [
        "return_1d",
        "return_3d",
        "return_7d",
        "return_14d",
        "return_30d",
        "log_return_1d",
        "volatility_12d",
        "volatility_24d",
        "volatility_72d",
        "sma_12d",
        "sma_24d",
        "sma_72d",
        "ema_12d",
        "ema_24d",
        "ema_72d",
        "high_low_range",
        "open_close_range",
        "body_size",
        "upper_wick",
        "lower_wick",
        "volume_change_1d",
        "volume_sma_24d",
        "volume_zscore_24d",
        "quote_volume_change_1d",
        "trade_count_change_1d",
    ]
    target_columns = [
        "target_close_next_1d",
        "target_return_next_1d",
    ]

    numeric_values = feature_df.select_dtypes(include="number").to_numpy()
    infinite_count = np.isinf(numeric_values).sum()

    if infinite_count:
        logger.warning("Replacing %s infinite candle feature values", infinite_count)

    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)

    before_feature_dropna = len(feature_df)

    feature_df = feature_df.dropna(subset=feature_columns + target_columns)

    logger.info(
        "Dropped %s rows with incomplete rolling features or targets",
        before_feature_dropna - len(feature_df),
    )

    if feature_df.empty:
        raise RuntimeError("No rows left after creating candle features.")

    output_columns = [
        "symbol",
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
    ] + feature_columns + target_columns

    feature_df = feature_df[output_columns].reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    feature_df.to_parquet(output_path, index=False)

    logger.info("Created candle features: %s -> %s rows", original_rows, len(feature_df))
    logger.info("Saved candle features to %s", output_path)
    logger.info(
        "Candle feature rows per symbol:\n%s",
        feature_df.groupby("symbol")["open_time"].agg(["min", "max", "count"]),
    )

    return feature_df


if __name__ == "__main__":
    create_candle_features()

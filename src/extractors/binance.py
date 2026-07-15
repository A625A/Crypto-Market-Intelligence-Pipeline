"""
    Fetch OHLCV candles for one Binance trading pair.

    Args:
        symbol: Trading pair such as "BTCUSDT" or "ETHUSDT".
        interval: Candle interval, such as "1d", "1h", or "15m".
        limit: Number of candles to fetch. Binance allows up to 1000.

    Returns:
        DataFrame with OHLCV candles and Binance volume/trade metadata.
"""

import logging
import time
from pathlib import Path
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data/raw/binance_ohlcv_raw.csv"


def fetch_binance_ohlcv(symbol, interval="1d", limit=730):

    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    logger.info("Fetching OHLCV data for %s", symbol)

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(
        data,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ],
    )

    df["symbol"] = symbol

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "taker_buy_base_asset_volume",
        "number_of_trades",
        "taker_buy_quote_asset_volume",
    ]

    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")

    df = df.drop(columns=["ignore"])

    return df


if __name__ == "__main__":
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    all_data = []

    for symbol in symbols:
        try:
            df = fetch_binance_ohlcv(symbol, interval="1d", limit=730)
            all_data.append(df)
            time.sleep(0.2)

        except requests.RequestException:
            logger.exception("Failed to fetch OHLCV data for %s", symbol)

    if not all_data:
        raise RuntimeError("No OHLCV data was fetched successfully")

    ohlcv_df = pd.concat(all_data, ignore_index=True)

    logger.info("Dataset shape: %s", ohlcv_df.shape)
    logger.info("Rows per symbol:\n%s", ohlcv_df["symbol"].value_counts())

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    ohlcv_df.to_csv(RAW_PATH, index=False)

    logger.info("Saved OHLCV data to %s", RAW_PATH)

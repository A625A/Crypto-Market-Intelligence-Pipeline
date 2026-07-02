"""
Fetch historical market chart data from CoinGecko.

This extracts daily price, market cap, and total volume for selected crypto
assets so they can be merged with Binance OHLCV data later.
"""

import json
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

COINGECKO_DEMO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"

RAW_PATH = Path("data/raw/coingecko_market_chart_raw.json")

COINS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
}


def get_coingecko_api_config() -> tuple[str, dict[str, str]]:
    load_dotenv(dotenv_path=ENV_PATH, override=False)

    api_plan = os.getenv("COINGECKO_API_PLAN", "demo").strip().lower()

    if api_plan == "pro":
        api_key = (
            os.getenv("COINGECKO_PRO_API_KEY", "").strip()
            or os.getenv("COINGECKO_API_KEY", "").strip()
        )

        if not api_key:
            raise RuntimeError(
                "COINGECKO_PRO_API_KEY or COINGECKO_API_KEY is required for "
                "CoinGecko Pro market chart requests."
            )

        return COINGECKO_PRO_BASE_URL, {"x-cg-pro-api-key": api_key}

    if api_plan != "demo":
        raise ValueError("COINGECKO_API_PLAN must be either 'demo' or 'pro'.")

    api_key = (
        os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
        or os.getenv("COINGECKO_API_KEY", "").strip()
    )

    if not api_key:
        raise RuntimeError(
            "COINGECKO_DEMO_API_KEY or COINGECKO_API_KEY is required for "
            "CoinGecko Demo market chart requests."
        )

    return COINGECKO_DEMO_BASE_URL, {"x-cg-demo-api-key": api_key}


def fetch_coingecko_market_chart(coin_id: str, days: int = 365) -> dict:
    """
    Fetch historical market chart data for one CoinGecko coin id.

    Args:
        coin_id: CoinGecko asset id, such as "bitcoin", "ethereum", or "solana".
        days: Number of historical days to fetch. The default is 365 because
            CoinGecko Demo API rejected 731-day market chart requests.

    Returns:
        JSON response from CoinGecko as a dictionary.
    """
    base_url, headers = get_coingecko_api_config()
    api_plan = "pro" if base_url == COINGECKO_PRO_BASE_URL else "demo"

    if api_plan == "demo" and days > 365:
        raise RuntimeError(
            "CoinGecko Demo historical market_chart data is limited to 365 days. "
            "Use COINGECKO_API_PLAN=pro for 731 days or set days=365."
        )

    url = f"{base_url}/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily",
    }

    logger.info("Fetching CoinGecko market chart data for %s", coin_id)

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=10,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        if response.status_code == 401:
            raise RuntimeError(
                "CoinGecko rejected the API key. Check COINGECKO_API_KEY and "
                "set COINGECKO_API_PLAN=demo or COINGECKO_API_PLAN=pro to "
                "match the key type."
            ) from exc
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise RuntimeError(
                "CoinGecko rate limit hit. Wait before retrying. "
                f"Suggested wait: {retry_after} seconds."
            ) from exc
        raise

    data = response.json()

    logger.info(
        "Fetched %s price points for %s",
        len(data.get("prices", [])),
        coin_id,
    )

    return data


if __name__ == "__main__":
    all_data = {}
    coin_items = list(COINS.items())

    for index, (symbol, coin_id) in enumerate(coin_items):
        try:
            data = fetch_coingecko_market_chart(coin_id=coin_id, days=365)

            all_data[symbol] = {
                "coingecko_id": coin_id,
                "data": data,
            }

        except (requests.RequestException, RuntimeError):
            logger.exception("Failed to fetch CoinGecko data for %s", coin_id)

        if index < len(coin_items) - 1:
            time.sleep(8)

    if not all_data:
        raise RuntimeError("No CoinGecko data was fetched successfully.")

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RAW_PATH, "w", encoding="utf-8") as file:
        json.dump(all_data, file, indent=2)

    logger.info("Saved raw CoinGecko market chart data to %s", RAW_PATH)

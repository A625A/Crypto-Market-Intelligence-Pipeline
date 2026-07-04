"""
Fetch macroeconomic data from FRED.

This extractor collects selected macro indicators for the last two years so
they can later be cleaned, forward-filled, and merged with daily crypto data.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
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

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

RAW_PATH = PROJECT_ROOT / "data/raw/fred_macro_raw.json"


FRED_SERIES = {
    "DGS10": {
        "feature_name": "us_10y_treasury_rate",
        "description": "10-Year Treasury Constant Maturity Rate",
    },
    "DGS2": {
        "feature_name": "us_2y_treasury_rate",
        "description": "2-Year Treasury Constant Maturity Rate",
    },
    "DFF": {
        "feature_name": "effective_federal_funds_rate",
        "description": "Effective Federal Funds Rate",
    },
    "CPIAUCSL": {
        "feature_name": "consumer_price_index",
        "description": "Consumer Price Index for All Urban Consumers",
    },
    "UNRATE": {
        "feature_name": "unemployment_rate",
        "description": "Civilian Unemployment Rate",
    },
    "VIXCLS": {
        "feature_name": "vix_close",
        "description": "CBOE Volatility Index Close",
    },
    "DTWEXBGS": {
        "feature_name": "trade_weighted_us_dollar_index",
        "description": "Trade Weighted U.S. Dollar Index",
    },
}


def get_two_year_window() -> tuple[str, str]:
    """
    Create a two-year observation window ending today in UTC.

    Returns:
        Observation start date and observation end date as YYYY-MM-DD strings.
    """
    end_date = datetime.now(timezone.utc).date()

    try:
        start_date = end_date.replace(year=end_date.year - 2)
    except ValueError:
        start_date = end_date.replace(
            year=end_date.year - 2,
            month=2,
            day=28,
        )

    return start_date.isoformat(), end_date.isoformat()


def get_fred_api_key() -> str:
    """
    Load the FRED API key from the .env file.

    Returns:
        FRED API key.
    """
    load_dotenv(dotenv_path=ENV_PATH, override=False)

    api_key = os.getenv("FRED_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("FRED_API_KEY is required in your .env file.")

    return api_key


def fetch_fred_series_observations(
    series_id: str,
    observation_start: str,
    observation_end: str,
) -> dict:
    """
    Fetch observations for one FRED series.

    Args:
        series_id: FRED series id, such as DGS10 or CPIAUCSL.
        observation_start: Start date in YYYY-MM-DD format.
        observation_end: End date in YYYY-MM-DD format.

    Returns:
        JSON response from FRED as a dictionary.
    """
    api_key = get_fred_api_key()

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "observation_end": observation_end,
    }

    logger.info(
        "Fetching FRED series %s from %s to %s",
        series_id,
        observation_start,
        observation_end,
    )

    response = requests.get(
        FRED_API_URL,
        params=params,
        timeout=15,
    )

    try:
        response.raise_for_status()

    except requests.HTTPError as exc:
        if response.status_code in {400, 401, 403}:
            raise RuntimeError(
                "FRED rejected the request. Check FRED_API_KEY and series_id."
            ) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise RuntimeError(
                "FRED rate limit hit. Wait before retrying. "
                f"Suggested wait: {retry_after} seconds."
            ) from exc

        raise

    data = response.json()

    logger.info(
        "Fetched %s observations for %s",
        len(data.get("observations", [])),
        series_id,
    )

    return data


if __name__ == "__main__":
    observation_start, observation_end = get_two_year_window()

    all_data = {
        "metadata": {
            "observation_start": observation_start,
            "observation_end": observation_end,
        },
        "series": {},
    }

    for series_id, series_config in FRED_SERIES.items():
        try:
            data = fetch_fred_series_observations(
                series_id=series_id,
                observation_start=observation_start,
                observation_end=observation_end,
            )

            all_data["series"][series_id] = {
                "feature_name": series_config["feature_name"],
                "description": series_config["description"],
                "data": data,
            }

            time.sleep(0.5)

        except (requests.RequestException, RuntimeError):
            logger.exception("Failed to fetch FRED series %s", series_id)

    if not all_data["series"]:
        raise RuntimeError("No FRED data was fetched successfully.")

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RAW_PATH, "w", encoding="utf-8") as file:
        json.dump(all_data, file, indent=2)

    logger.info("Saved raw FRED macro data to %s", RAW_PATH)
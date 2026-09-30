"""
Fetch macroeconomic data from FRED.

This extractor collects initial-release vintages of selected macro indicators
for the last two years so they can later be aligned by availability date,
forward-filled, and merged with daily crypto data without revision leakage.
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
        # Bound vintage dates as well as observations: all-history requests can
        # exceed FRED's JSON vintage-date limit for daily series. These series
        # are released on or after their observation dates.
        "realtime_start": observation_start,
        "realtime_end": observation_end,
        "output_type": 4,
    }

    logger.info(
        "Fetching FRED series %s from %s to %s",
        series_id,
        observation_start,
        observation_end,
    )

    try:
        response = requests.get(FRED_API_URL, params=params, timeout=15)
    except requests.RequestException as exc:
        # Requests exceptions can contain the URL, including the API key.
        raise RuntimeError(
            f"FRED request failed for {series_id}: {type(exc).__name__}."
        ) from None

    try:
        response.raise_for_status()

    except requests.HTTPError:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise RuntimeError(
                "FRED rate limit hit. Wait before retrying. "
                f"Suggested wait: {retry_after} seconds."
            ) from None

        try:
            detail = str(response.json().get("error_message", "Request rejected."))
        except ValueError:
            detail = "Request rejected."
        detail = detail.replace(api_key, "[REDACTED]")
        raise RuntimeError(
            f"FRED rejected {series_id} (HTTP {response.status_code}): {detail}"
        ) from None

    data = response.json()

    logger.info(
        "Fetched %s observations for %s",
        len(data.get("observations", [])),
        series_id,
    )

    return data


def extract_fred_macro(output_path: Path = RAW_PATH) -> dict:
    """Save a complete initial-release dataset, preserving old data on failure."""
    output_path = Path(output_path)
    observation_start, observation_end = get_two_year_window()

    all_data = {
        "metadata": {
            "observation_start": observation_start,
            "observation_end": observation_end,
        },
        "series": {},
    }

    failed_series = []
    for series_id, series_config in FRED_SERIES.items():
        try:
            data = fetch_fred_series_observations(
                series_id=series_id,
                observation_start=observation_start,
                observation_end=observation_end,
            )

            if str(data.get("output_type")) != "4" or not data.get("observations"):
                raise RuntimeError("Missing initial-release observations.")

            all_data["series"][series_id] = {
                "feature_name": series_config["feature_name"],
                "description": series_config["description"],
                "data": data,
            }

            time.sleep(0.5)

        except RuntimeError as exc:
            failed_series.append(series_id)
            logger.error("Failed to fetch FRED series %s: %s", series_id, exc)

    if failed_series:
        raise RuntimeError(
            f"FRED extraction incomplete; failed series: {', '.join(failed_series)}. "
            "Existing raw file was not changed."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")

    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(all_data, file, indent=2)
    temporary_path.replace(output_path)

    logger.info("Saved raw FRED macro data to %s", output_path)
    return all_data


if __name__ == "__main__":
    try:
        extract_fred_macro()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

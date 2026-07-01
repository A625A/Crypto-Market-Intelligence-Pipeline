"""
Fetch daily Crypto Fear & Greed Index records from the Alternative.me API.

The script requests JSON data from the `/fng/` endpoint and saves the raw
response to `data/raw/fear_greed_raw.json` for later cleaning and analysis.
"""

import json
import logging
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

RAW_PATH = Path("data/raw/fear_greed_raw.json")


def fetch_fear_greed(limit=730):
    url = "https://api.alternative.me/fng/"

    params = {
        "limit": limit,
        "format": "json",
    }

    logger.info("Fetching Fear & Greed data from Alternative.me")

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    logger.info("Fetched %s Fear & Greed records", len(data.get("data", [])))

    return data


if __name__ == "__main__":
    data = fetch_fear_greed(limit=730)

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RAW_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    logger.info("Saved raw Fear & Greed data to %s", RAW_PATH)
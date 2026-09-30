"""
Fetch worldwide news from NewsAPI.

This extracts articles and breaking news headlines from news sources and blogs across the web.
The data can later be merged with Fear and Greed features.
"""

import json
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
RAW_PATH = PROJECT_ROOT / "data/raw/newsapi_raw.json"

load_dotenv(dotenv_path=ENV_PATH, override=False)

API_KEY = os.getenv("NEWSAPI_KEY")

if not API_KEY:
    raise ValueError("NEWSAPI_KEY not found in environment variables.")

URL = "https://newsapi.org/v2/everything"

HEADERS = {
    "X-Api-Key": API_KEY
}

QUERIES = {
    "BTCUSDT": "bitcoin OR BTC",
    "ETHUSDT": "ethereum OR ETH",
    "SOLUSDT": "solana OR SOL",
}


def fetch_news(symbol, query):
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,
    }

    response = requests.get(
        URL,
        params=params,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    logger.info(
        "%s - Total results: %s",
        symbol,
        data.get("totalResults")
    )

    return data


if __name__ == "__main__":

    all_news = {}

    for symbol, query in QUERIES.items():
        data = fetch_news(symbol, query)
        all_news[symbol] = data

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RAW_PATH, "w", encoding="utf-8") as file:
        json.dump(all_news, file, indent=2)

    logger.info("Saved raw NewsAPI data to %s", RAW_PATH)

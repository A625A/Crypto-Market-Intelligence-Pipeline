""""

"""
import logging
import os
import requests


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

def fetch_coingecko_price(crypto_id):
    url = f"https://api.coingecko.com/api/v3/simple/price?vs_currencies=usd&ids={crypto_id}&x_cg_demo_api_key={COINGECKO_API_KEY}"

    logger.info("Fetching price data for %s", crypto_id)

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    return data

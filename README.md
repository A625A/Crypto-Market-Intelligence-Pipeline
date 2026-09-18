# Crypto Market Intelligence Pipeline

> **Work in progress**

A Python data pipeline for cryptocurrency research.

It currently pulls market, macroeconomic, and sentiment data for `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`, cleans and validates the data, and creates separate feature tables.

I started this project to get more experience working with multiple data sources and time-series data before moving into modeling and backtesting.

## Data Sources

|Source|Data|
|---|---|
|Binance|Daily OHLCV|
|CoinGecko|Crypto market data|
|FRED|Macroeconomic data|
|Alternative.me|Fear & Greed Index|

## Current Pipeline

Each source currently follows its own workflow:

```text
API
 ↓
Extraction
 ↓
Raw data
 ↓
Cleaning / validation
 ↓
Feature engineering
 ↓
Feature table
```

The feature tables are not yet merged into one final modeling dataset.

## Binance

The Binance pipeline collects daily OHLCV data for:

- BTCUSDT
- ETHUSDT
- SOLUSDT

Outputs:

```text
data/processed/binance_ohlcv_clean.csv
data/processed/features/candle_features.parquet
```

## CoinGecko

CoinGecko is used for additional crypto market data.

Outputs:

```text
data/processed/coingecko_market_chart_clean.csv
data/processed/features/market_features.parquet
```

## FRED

The macro pipeline includes data such as:

- Treasury rates
- Federal Funds rate
- CPI
- Unemployment
- VIX
- Trade-weighted dollar data

One thing I wanted to be careful with here was **look-ahead bias**.

The pipeline uses FRED availability dates so historical rows do not automatically receive information that would only have become available later.

The feature step also includes things such as:

- Rate changes
- Yield-curve features
- VIX returns
- Dollar returns
- Rolling z-scores
- CPI changes
- Unemployment changes

Outputs:

```text
data/processed/fred_macro_clean.csv
data/processed/features/macro_features.parquet
```

## Sentiment

The project also uses the Alternative.me Fear & Greed Index.

The sentiment data is aligned by date with the market data and treated as a market-wide feature.

Outputs:

```text
data/processed/fear_greed_clean.csv
data/processed/features/sentiment_features.parquet
```

## Tech Stack

- Python
- Pandas
- NumPy
- REST APIs
- Parquet
- Pytest

## Setup

Python 3.13 is used for local verification.

```bash
git clone https://github.com/A625A/Crypto-Market-Intelligence-Pipeline.git
cd Crypto-Market-Intelligence-Pipeline

python3.13 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
cp .env.example .env
```

Add the required API keys to `.env`:

```dotenv
FRED_API_KEY=your_fred_api_key
COINGECKO_API_KEY=your_coingecko_api_key
COINGECKO_API_PLAN=demo
```

## Running the Pipelines

### Binance

```bash
python -m src.extractors.binance
python -m src.transformers.clean_binance_ohlcv
python -m src.features.candle_features
```

### CoinGecko

```bash
python -m src.extractors.coingecko
python -m src.transformers.clean_coingecko_market_chart
python -m src.features.market_features
```

### FRED

```bash
python -m src.extractors.fred_macro
python -m src.transformers.clean_fred_macro
python -m src.features.macro_features
```

### Fear & Greed

```bash
python -m src.extractors.fear_greed
python -m src.transformers.clean_greed_fear
python -m src.features.sentiment_features
```

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q -p no:cacheprovider
```

## Project Structure

```text
.
├── src/
│   ├── extractors/
│   ├── transformers/
│   └── features/
├── tests/
├── .env.example
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

Run the commands above from the repository root. Extractors and feature builders
create their output directories under `data/` when needed; generated datasets
are ignored by Git.

Each source is run separately. There is no combined pipeline runner, trained
model, backtester, or dashboard yet.

## Next Steps

The main things I still want to add are:

- Merge the feature tables
- Add one orchestration workflow
- Build the first modeling experiments
- Add walk-forward validation
- Add backtesting
- Build a dashboard

There is no live trading functionality at this point.

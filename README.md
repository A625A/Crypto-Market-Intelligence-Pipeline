# Crypto Market Intelligence Pipeline

> **Work in progress** — a reproducible multi-source Python data pipeline for cryptocurrency market research.

The project collects market, macroeconomic, and sentiment data for `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`, validates and cleans the raw inputs, and creates feature tables for later modeling and backtesting.

## Why This Project

Crypto markets are influenced by more than price data alone.

The goal of this project is to build a research pipeline that combines several types of information while maintaining proper time alignment and avoiding look-ahead bias in historical analysis.

The current implementation focuses on the data foundation:

**ingestion → validation → cleaning → feature engineering**

Modeling and backtesting will be added after the underlying datasets can be reliably combined into a model-ready dataset.

## Tech Stack

`Python` · `Pandas` · `NumPy` · `REST APIs` · `Parquet` · `Docker` · `Pytest`

## Data Sources

|Source|Data|Current Output|
|---|---|---|
|Binance|Daily OHLCV market data|Candle features|
|CoinGecko|Cryptocurrency market data|Market features|
|FRED|Macroeconomic indicators|Macro features|
|Alternative.me|Fear & Greed Index|Sentiment features|

## What Is Implemented

### Binance

The Binance workflow extracts daily OHLCV data for:

- BTCUSDT
    
- ETHUSDT
    
- SOLUSDT
    

It validates and cleans the observations before generating candle and price-related features.

Output:

```text
data/processed/binance_ohlcv_clean.csv
data/processed/features/candle_features.parquet
```

### CoinGecko

CoinGecko provides additional cryptocurrency market information used to generate market-level features.

Output:

```text
data/processed/coingecko_market_chart_clean.csv
data/processed/features/market_features.parquet
```

### FRED Macroeconomic Data

The macroeconomic workflow retrieves economic and financial indicators including Treasury rates, Federal Funds data, inflation, unemployment, volatility, and dollar-related series.

The pipeline uses FRED real-time availability information to reduce look-ahead bias.

Values are aligned according to when the information would historically have been available rather than simply using the latest revised observations.

Output:

```text
data/processed/fred_macro_clean.csv
data/processed/features/macro_features.parquet
```

The feature workflow includes transformations such as:

- Treasury-rate movements
    
- Yield-curve signals
    
- Federal Funds changes
    
- VIX returns and rolling statistics
    
- Dollar-index returns and rolling statistics
    
- CPI changes
    
- Unemployment changes
    

Features requiring historical windows intentionally preserve missing values during their warm-up period.

### Market Sentiment

The sentiment workflow retrieves the Alternative.me Fear & Greed Index.

Sentiment data is aligned by UTC date with the market-data grid and is treated as a market-wide signal rather than a coin-specific metric.

Output:

```text
data/processed/fear_greed_clean.csv
data/processed/features/sentiment_features.parquet
```

## Current Architecture

```text
External APIs
     │
     ▼
Data Extraction
     │
     ▼
Raw Data
     │
     ▼
Validation & Cleaning
     │
     ▼
Processed Data
     │
     ▼
Feature Engineering
     │
     ▼
Feature Tables
     │
     ▼
Future unified model-ready dataset
     │
     ├── Modeling
     └── Backtesting
```

Each source currently has its own extraction, cleaning, and feature workflow.

A single top-level orchestration process that merges all source-specific feature tables has not yet been implemented.

## Setup

Python 3.11 is recommended.

```bash
git clone https://github.com/A625A/Crypto-Market-Intelligence-Pipeline.git
cd Crypto-Market-Intelligence-Pipeline

python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows:

```bash
.venv\Scripts\activate
```

## Environment Variables

Add API credentials to `.env` when required:

```dotenv
FRED_API_KEY=your_fred_api_key
COINGECKO_API_KEY=your_coingecko_api_key
COINGECKO_API_PLAN=demo
```

Binance and Alternative.me do not require API keys for the currently implemented endpoints.

Never commit `.env`.

## Running the Pipelines

Run all commands from the repository root.

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

## Generic CSV Pipeline

The project also includes a generic CSV processing workflow.

Place a CSV file inside:

```text
data/raw/
```

Then run:

```bash
python run_pipeline.py input.csv
```

Custom output names can also be provided:

```bash
python run_pipeline.py input.csv \
  --processed-filename cleaned.csv \
  --final-filename features.csv
```

## Testing

Install Pytest if it is not already installed:

```bash
python -m pip install pytest
```

Run the test suite:

```bash
python -m pytest -q -p no:cacheprovider
```

Individual feature suites can also be executed:

```bash
python -m pytest -q -p no:cacheprovider tests/test_sentiment_features.py
python -m pytest -q -p no:cacheprovider tests/test_market_features.py
python -m pytest -q -p no:cacheprovider tests/features/test_macro_features.py
```

## Project Structure

```text
.
├── data/
│   ├── raw/
│   ├── processed/
│   └── final/
├── dashboards/
├── notebooks/
├── src/
│   ├── extractors/
│   ├── transformers/
│   ├── features/
│   ├── models/
│   ├── backtesting/
│   ├── risk/
│   └── trading/
├── tests/
├── run_pipeline.py
├── Dockerfile
└── requirements.txt
```

## Current Limitations

This repository is actively being developed.

The current version does **not** yet provide:

- A single orchestration command for every data source
    
- A unified model-ready feature table
    
- Walk-forward model validation
    
- Production scheduling
    
- Live trading execution
    
- A completed production dashboard
    

The project is intended for research and education and is not financial advice.

## Roadmap

Planned next steps:

1. Merge source-specific feature tables into one time-aligned dataset.
    
2. Add automated pipeline orchestration.
    
3. Implement walk-forward model validation.
    
4. Build model comparison and tuning workflows.
    
5. Add backtesting.
    
6. Expand the dashboard after the research pipeline is stable.
    

## What I Am Learning

This project is being used to practice and strengthen skills in:

- Multi-source data ingestion
    
- Data validation
    
- Time-series data alignment
    
- Feature engineering
    
- Avoiding look-ahead bias
    
- Reproducible data workflows
    
- Testing data transformations
    
- Containerized development

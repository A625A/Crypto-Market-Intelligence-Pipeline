# Crypto Pipeline

Data science project scaffold for crypto research, feature engineering,
modeling, dashboards, and pipeline experiments.

## Project Structure

```text
data/
  raw/          # Original input data; keep immutable and out of git
  processed/    # Cleaned intermediate outputs
  final/        # Model-ready feature outputs
src/
  extractors/   # Data loading and external source ingestion
  transformers/ # Cleaning and transformation logic
  sentiment/    # Sentiment analysis components
  features/     # Feature engineering
  models/       # Training and evaluation code
  backtesting/  # Strategy backtesting code
  trading/      # Trading signal or execution code
  risk/         # Risk controls and portfolio rules
  utils/        # Shared helpers
notebooks/      # Exploratory notebooks
reports/        # Analysis outputs and figures
dashboards/     # Streamlit or dashboard apps
models/         # Saved model artifacts
logs/           # Runtime logs
tests/          # Reusable function tests
```


## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Run the pipeline with a CSV file that already exists in `data/raw/`:

```bash
python run_pipeline.py your_raw_file.csv
```

Run the dashboard:

```bash
streamlit run dashboards/app.py
```

Run tests:

```bash
python -m pytest
```

## Phase 10 — Market Sentiment Features

Phase 10 converts the Alternative.me Fear & Greed Index into daily,
market-wide sentiment features and aligns them to the Binance daily grid for
`BTCUSDT`, `ETHUSDT`, and `SOLUSDT`. It does not provide coin-specific news
sentiment.

The module intentionally excludes CryptoPanic because the repository has no
cleaned CryptoPanic dataset. The only raw artifact,
`data/raw/cryptopanic_posts_raw.json`, is a 41-byte object with empty `BTC`,
`ETH`, and `SOL` entries and contains no articles or usable schema. Phase 10
does not use CryptoPanic, FinBERT, Hugging Face, `transformers`, or `torch`.

Inputs:

```text
data/processed/fear_greed_clean.csv
  fear_greed_value, date, fear_greed_classification

data/processed/binance_ohlcv_clean.csv
  symbol, open_time, and cleaned daily OHLCV columns
```

Output:

```text
data/processed/features/sentiment_features.parquet
```

The output contains one row per `symbol + date`. Fear & Greed features are
calculated once per market date and then replicated across the three symbols.
The feature formulas are:

```text
fear_greed_change_1d = value[D] - value[D-1]
fear_greed_change_7d = value[D] - value[D-7]
fear_greed_change_14d = value[D] - value[D-14]
fear_greed_sma_N = trailing N-day mean, N in {3, 7, 14, 30}
fear_greed_std_N = trailing N-day sample standard deviation, N in {7, 30}
normalized_fear_greed = (fear_greed_value - 50) / 50
fear_greed_distance_from_neutral = abs(fear_greed_value - 50)
```

Category indicators use these inclusive ranges: extreme fear `0–24`, fear
`25–44`, neutral `45–55`, greed `56–74`, and extreme greed `75–100`.

Rolling features require their full trailing window, so leading values remain
missing when history is insufficient. Change features also remain missing until
their lag exists. A missing source date remains null for all three symbols, and
rolling windows that contain that gap also remain null. The pipeline reports
missing and unused source dates and does not forward-fill or backward-fill.
Every day-D feature uses only day D and earlier values; it assumes the
completed day-D index is available for predicting a day-D+1 outcome.

Run Phase 10:

```bash
python -m src.features.sentiment_features
```

Run its focused tests:

```bash
python -m pytest -q tests/test_sentiment_features.py
```

News sentiment can be added later only after a real cleaned dataset provides
non-empty headlines, UTC publication timestamps, stable article identifiers,
currency mappings, and documented source coverage.

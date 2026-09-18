# Crypto Market Intelligence Pipeline

> **Work in progress**

A Python data pipeline for cryptocurrency research.

It currently pulls market, macroeconomic, and sentiment data for `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`, cleans and validates the data, and combines feature tables into a daily modeling dataset.

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
 ↓
Combined modeling dataset
```

The combined dataset aligns the four feature tables on UTC date and asset.

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

### Combined modeling dataset

After generating all four feature tables:

```bash
python -m src.features.modeling_dataset
# Optional strict return threshold: 0.02 means greater than 2%.
python -m src.features.modeling_dataset --return-threshold 0.02
```

Output: `data/processed/modeling_dataset.parquet`. Use `--output PATH` to save
elsewhere. The Python `create_modeling_dataset(...)` function also accepts paths
for all four feature tables, cleaned Binance prices, and the raw FRED JSON.
Default paths are anchored to the repository root.

Each row is keyed by `symbol` and `date` (a timezone-naive timestamp representing
a UTC calendar date). Forecasts are made **after that day's candle closes**.
The clean Binance price grid determines the rows; candle, market, and sentiment
features join by asset and date, while global macro features join by date.
Joins validate cardinality and reject duplicate normalized keys, unknown assets,
conflicting feature names, invalid values, and stale candle closing prices.
Internal gaps in an asset's price history or the daily macro table are errors;
different asset listing dates are allowed. Current-day candles are rejected.

Macro provenance is checked on every file build: the builder replays the existing
cleaner and feature calculations from raw FRED **initial-release** observations
(`output_type=4`), using `realtime_start` as the availability date. The saved macro
table must match that history with its existing one-calendar-day lag. A release
on day `t` first enters features on `t+1`; the join applies no additional lag.
Revised/current-vintage raw data and stale or unlagged macro tables fail before
the output is replaced. `macro_information_date` records the information cutoff
for the joined macro row, not the observation month or each series' release date.
The lower-level `build_modeling_dataset(...)` accepts in-memory frames and assumes
the caller has already verified macro provenance; use the file builder for the
full check.

Missing source coverage and rolling warm-up values stay null. There is no
backfill, interpolation, zero fill, or imputation across assets. Macro values are
carried forward only by the upstream release-aware cleaner; the combined step
does not extrapolate beyond the macro table. `has_candle_features`,
`has_market_features`, `has_macro_features`, and `has_sentiment_features` indicate
whether a source row matched (not whether all its values are populated).
`missing_feature_count` counts null numeric predictors, excluding targets and
audit fields. The existing candle builder omits warm-up and final-day rows, so
those grid rows retain null candle features here.

Targets are rebuilt from cleaned prices using an exact same-asset `date + 1 day`
lookup; legacy future-price columns from the candle table are discarded:

| Column | Definition |
|---|---|
| `target_return_next_1d` | `(close[t+1] - close[t]) / close[t]` |
| `target_direction_next_1d` | `1` when next-day return is positive, otherwise `0` |
| `target_above_threshold_next_1d` | `1` when next-day return is strictly above the threshold (default `0.01`), otherwise `0` |

Returns are fractions, not percentages. Binary targets use nullable integers;
all targets remain null where the next day's close is unavailable. The threshold
and timing convention are stored in the Parquet pandas metadata (`df.attrs`).
The output retains both historical training candidates and final unlabeled rows.
For training, select one target, remove rows missing that label, and **exclude
every `target_*` column from predictors**. Split chronologically before fitting
any imputer or scaler; also keep training labels' next-day dates before the
validation boundary. Retaining missing features avoids silently discarding
history when sources have different coverage.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q -p no:cacheprovider
```

Combined-dataset tests cover duplicate keys, missing dates and source coverage,
asset isolation, join cardinality, exact targets, null final labels, future-price
perturbations, release-date leakage, raw FRED provenance, and Parquet output.

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

- Add one orchestration workflow
- Build the first modeling experiments
- Add walk-forward validation
- Add backtesting
- Build a dashboard

There is no live trading functionality at this point.

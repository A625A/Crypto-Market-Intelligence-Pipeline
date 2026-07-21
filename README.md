# Crypto Market Intelligence Pipeline

A reproducible Python data pipeline for daily cryptocurrency research. It
collects market, macroeconomic, and sentiment data for `BTCUSDT`, `ETHUSDT`,
and `SOLUSDT`, validates the raw inputs, and creates feature tables for later
modeling and backtesting.

## What is implemented

| Data source | Cleaned dataset | Feature output |
| --- | --- | --- |
| Binance daily OHLCV | `data/processed/binance_ohlcv_clean.csv` | `data/processed/features/candle_features.parquet` |
| CoinGecko market chart | `data/processed/coingecko_market_chart_clean.csv` | `data/processed/features/market_features.parquet` |
| Alternative.me Fear & Greed Index | `data/processed/fear_greed_clean.csv` | `data/processed/features/sentiment_features.parquet` |
| FRED macro series | `data/processed/fred_macro_clean.csv` | Clean macro inputs for future integration |

Each source currently has its own extraction, cleaning, and feature command.
`run_pipeline.py` is a separate generic CSV pipeline; it does not yet
orchestrate the source-specific workflows or merge their outputs into one
model-ready table.

## Setup

The Docker image uses Python 3.11, which is also the recommended local
version.

```bash
git clone https://github.com/A625A/Crypto-Market-Intelligence-Pipeline.git
cd Crypto-Market-Intelligence-Pipeline
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Add the following credentials to `.env` when their data sources are needed:

```dotenv
FRED_API_KEY=your_fred_api_key
COINGECKO_API_KEY=your_coingecko_api_key
COINGECKO_API_PLAN=demo
```

Binance and Alternative.me do not require API keys for the implemented
endpoints. Never commit `.env`; it is ignored by Git.

## Run the data workflows

Run commands from the repository root. Generated raw and processed data are
kept out of Git.

### Binance OHLCV and candle features

```bash
python -m src.extractors.binance
python -m src.transformers.clean_binance_ohlcv
python -m src.features.candle_features
```

### CoinGecko market features

```bash
python -m src.extractors.coingecko
python -m src.transformers.clean_coingecko_market_chart
python -m src.features.market_features
```

The demo CoinGecko plan is limited to the 365-day request used by the
extractor. Set `COINGECKO_API_PLAN=pro` when using a Pro key.

### FRED macro data

```bash
python -m src.extractors.fred_macro
python -m src.transformers.clean_fred_macro
```

This workflow requires `FRED_API_KEY` and fetches the implemented Treasury,
Federal Funds, CPI, unemployment, VIX, and trade-weighted dollar series.

### Fear & Greed sentiment features

```bash
python -m src.extractors.fear_greed
python -m src.transformers.clean_greed_fear
python -m src.features.sentiment_features
```

Sentiment features are market-wide, not coin-specific. They are calculated by
UTC date and aligned to the Binance daily grid for all three supported symbols.
Missing source dates remain missing; the pipeline does not forward-fill or
backfill them.

### Generic CSV pipeline

Place a CSV inside `data/raw/`, then run:

```bash
python run_pipeline.py input.csv
```

Optional output names:

```bash
python run_pipeline.py input.csv \
  --processed-filename cleaned.csv \
  --final-filename features.csv
```

This writes to `data/processed/` and `data/final/`.

## Test

`pytest` is not yet pinned in `requirements.txt`. Install it in the development
environment before running the suite:

```bash
python -m pip install pytest
```

```bash
python -m pytest -q -p no:cacheprovider
```

Focused suites can be run directly, for example:

```bash
python -m pytest -q -p no:cacheprovider tests/test_sentiment_features.py
python -m pytest -q -p no:cacheprovider tests/test_market_features.py
```

## Project structure

```text
.
├── data/
│   ├── raw/                 # API responses and source CSV files
│   ├── processed/           # Validated datasets and feature tables
│   └── final/               # Generic pipeline outputs
├── dashboards/              # Streamlit dashboard starter
├── notebooks/               # Exploratory analysis
├── src/
│   ├── extractors/          # Binance, CoinGecko, FRED, and sentiment ingestion
│   ├── transformers/        # Source validation and cleaning
│   ├── features/            # Candle, market, and sentiment features
│   ├── models/              # Modeling code
│   ├── backtesting/         # Backtesting code
│   ├── risk/                # Risk controls
│   └── trading/             # Trading logic
├── tests/                   # Unit and regression tests
├── run_pipeline.py          # Generic raw-CSV pipeline
├── Dockerfile
└── requirements.txt
```

## Current limitations

- The source-specific feature tables are not yet merged by one top-level
  orchestration command.
- The dashboard is a starter and `streamlit` is not included in the current
  requirements file.
- The repository does not yet provide walk-forward model validation,
  production scheduling, or live trading execution.
- This project is for research and education, not financial advice.

## Troubleshooting

- `FileNotFoundError`: run the preceding extractor and cleaner from the
  repository root before creating features.
- API authentication errors: confirm the key and plan in `.env`; do not add
  quotes or placeholder values.
- Missing leading rolling features: expected until a full lookback window is
  available.
- Pytest cache warnings: keep `-p no:cacheprovider` in the test command.

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

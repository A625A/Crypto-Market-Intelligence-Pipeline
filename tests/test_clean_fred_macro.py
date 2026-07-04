import json

import pandas as pd
import pytest

from src.transformers.clean_fred_macro import clean_fred_macro


def test_clean_fred_macro_pivots_forward_fills_and_lags_macro_series(tmp_path):
    raw_path = tmp_path / "fred_macro_raw.json"
    output_path = tmp_path / "fred_macro_clean.csv"

    raw_data = {
        "metadata": {
            "observation_start": "2024-01-01",
            "observation_end": "2024-02-01",
        },
        "series": {
            "DGS10": {
                "feature_name": "us_10y_treasury_rate",
                "description": "10-Year Treasury Constant Maturity Rate",
                "data": {
                    "observations": [
                        {"date": "2024-01-01", "value": "4.00"},
                        {"date": "2024-02-01", "value": "4.20"},
                        {"date": "2024-02-02", "value": "."},
                    ]
                },
            },
            "CPIAUCSL": {
                "feature_name": "consumer_price_index",
                "description": "Consumer Price Index",
                "data": {
                    "observations": [
                        {"date": "2024-01-01", "value": "300.0"},
                    ]
                },
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    cleaned = clean_fred_macro(raw_path, output_path)

    assert list(cleaned.columns) == [
        "date",
        "us_10y_treasury_rate",
        "consumer_price_index",
    ]
    assert cleaned["date"].astype(str).tolist() == [
        "2024-01-31",
        "2024-02-01",
    ]
    assert cleaned["us_10y_treasury_rate"].tolist() == [4.0, 4.2]
    assert cleaned["consumer_price_index"].tolist() == [300.0, 300.0]
    assert output_path.exists()

    saved = pd.read_csv(output_path)
    assert len(saved) == 2


def test_clean_fred_macro_rejects_missing_observations(tmp_path):
    raw_path = tmp_path / "fred_macro_raw.json"
    output_path = tmp_path / "fred_macro_clean.csv"

    raw_data = {
        "series": {
            "DGS10": {
                "feature_name": "us_10y_treasury_rate",
                "data": {},
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing FRED observations"):
        clean_fred_macro(raw_path, output_path)

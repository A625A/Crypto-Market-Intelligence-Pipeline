import json

import pandas as pd
import pytest

from src.transformers.clean_fred_macro import clean_fred_macro


def test_clean_fred_macro_pivots_on_release_dates_and_forward_fills(tmp_path):
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
                    "output_type": 4,
                    "observations": [
                        {
                            "realtime_start": "2024-02-02",
                            "realtime_end": "9999-12-31",
                            "date": "2024-02-01",
                            "value": "4.00",
                        },
                        {
                            "realtime_start": "2024-02-15",
                            "realtime_end": "9999-12-31",
                            "date": "2024-02-14",
                            "value": "4.20",
                        },
                        {
                            "realtime_start": "2024-02-16",
                            "realtime_end": "9999-12-31",
                            "date": "2024-02-15",
                            "value": ".",
                        },
                    ]
                },
            },
            "CPIAUCSL": {
                "feature_name": "consumer_price_index",
                "description": "Consumer Price Index",
                "data": {
                    "output_type": 4,
                    "observations": [
                        {
                            "realtime_start": "2024-02-14",
                            "realtime_end": "9999-12-31",
                            "date": "2024-01-01",
                            "value": "300.0",
                        },
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
        "2024-02-14",
        "2024-02-15",
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
                "data": {"output_type": 4, "observations": []},
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing FRED observations"):
        clean_fred_macro(raw_path, output_path)


def test_clean_fred_macro_rejects_current_vintage_payloads(tmp_path):
    raw_path = tmp_path / "fred_macro_raw.json"
    output_path = tmp_path / "fred_macro_clean.csv"

    raw_data = {
        "series": {
            "CPIAUCSL": {
                "feature_name": "consumer_price_index",
                "data": {
                    "output_type": 1,
                    "observations": [
                        {
                            "realtime_start": "2026-07-14",
                            "realtime_end": "2026-07-14",
                            "date": "2024-01-01",
                            "value": "300.0",
                        }
                    ],
                },
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    with pytest.raises(ValueError, match="initial-release FRED observations"):
        clean_fred_macro(raw_path, output_path)

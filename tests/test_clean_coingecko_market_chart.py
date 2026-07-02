import json

import pandas as pd
import pytest

from src.transformers.clean_coingecko_market_chart import clean_coingecko_market_chart


def test_clean_coingecko_market_chart_normalizes_daily_market_data(tmp_path):
    raw_path = tmp_path / "coingecko_raw.json"
    output_path = tmp_path / "coingecko_clean.csv"

    raw_data = {
        "BTCUSDT": {
            "coingecko_id": "bitcoin",
            "data": {
                "prices": [
                    [1704067200000, "42000.5"],
                    [1704153600000, "43000.0"],
                ],
                "market_caps": [
                    [1704067200000, "820000000000"],
                    [1704153600000, "840000000000"],
                ],
                "total_volumes": [
                    [1704067200000, "25000000000"],
                    [1704153600000, "26000000000"],
                ],
            },
        },
        "ETHUSDT": {
            "coingecko_id": "ethereum",
            "data": {
                "prices": [[1704067200000, "2200.0"]],
                "market_caps": [[1704067200000, "265000000000"]],
                "total_volumes": [[1704067200000, "12000000000"]],
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    cleaned = clean_coingecko_market_chart(raw_path, output_path)

    assert list(cleaned.columns) == [
        "symbol",
        "coingecko_id",
        "date",
        "coingecko_price_usd",
        "coingecko_market_cap_usd",
        "coingecko_total_volume_usd",
    ]
    assert len(cleaned) == 3
    assert cleaned["symbol"].tolist() == ["BTCUSDT", "BTCUSDT", "ETHUSDT"]
    assert cleaned["date"].astype(str).tolist() == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-01",
    ]
    assert cleaned["coingecko_price_usd"].tolist() == [42000.5, 43000.0, 2200.0]
    assert output_path.exists()

    saved = pd.read_csv(output_path)
    assert len(saved) == 3


def test_clean_coingecko_market_chart_drops_current_day_rows(tmp_path):
    raw_path = tmp_path / "coingecko_raw.json"
    output_path = tmp_path / "coingecko_clean.csv"
    current_day_timestamp = int(
        pd.Timestamp.now(tz="UTC").normalize().timestamp() * 1000
    )

    raw_data = {
        "BTCUSDT": {
            "coingecko_id": "bitcoin",
            "data": {
                "prices": [
                    [1704067200000, "42000.5"],
                    [current_day_timestamp, "45000.0"],
                ],
                "market_caps": [
                    [1704067200000, "820000000000"],
                    [current_day_timestamp, "900000000000"],
                ],
                "total_volumes": [
                    [1704067200000, "25000000000"],
                    [current_day_timestamp, "30000000000"],
                ],
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    cleaned = clean_coingecko_market_chart(raw_path, output_path)

    assert len(cleaned) == 1
    assert cleaned["date"].astype(str).tolist() == ["2024-01-01"]


def test_clean_coingecko_market_chart_rejects_missing_metric(tmp_path):
    raw_path = tmp_path / "coingecko_raw.json"
    output_path = tmp_path / "coingecko_clean.csv"

    raw_data = {
        "BTCUSDT": {
            "coingecko_id": "bitcoin",
            "data": {
                "prices": [[1704067200000, 42000.5]],
                "market_caps": [[1704067200000, 820000000000]],
            },
        },
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required CoinGecko metrics"):
        clean_coingecko_market_chart(raw_path, output_path)

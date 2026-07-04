import numpy as np
import pandas as pd

from src.features.market_features import create_market_features


def make_clean_market_rows(periods=5):
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    price = np.arange(periods, dtype=float) + 100.0
    market_cap = price * 1_000_000.0

    return pd.DataFrame(
        {
            "symbol": " btcusdt ",
            "coingecko_id": " bitcoin ",
            "date": dates.astype(str),
            "coingecko_price_usd": price,
            "coingecko_market_cap_usd": market_cap,
            "coingecko_total_volume_usd": np.arange(periods, dtype=float) + 10_000.0,
        }
    )


def test_create_market_features_preserves_symbol_and_writes_parquet(tmp_path):
    input_path = tmp_path / "coingecko_market_chart_clean.csv"
    output_path = tmp_path / "market_features.parquet"
    raw_df = make_clean_market_rows()

    raw_df.to_csv(input_path, index=False)

    features = create_market_features(input_path, output_path)

    assert list(features.columns) == [
        "symbol",
        "coingecko_id",
        "date",
        "market_cap_usd",
        "market_cap_change_1d",
        "total_volume_usd",
        "total_volume_change_1d",
        "volume_to_market_cap",
        "estimated_circulating_supply",
    ]
    assert features["symbol"].unique().tolist() == ["BTCUSDT"]
    assert features["coingecko_id"].unique().tolist() == ["bitcoin"]
    assert features["date"].astype(str).tolist() == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
    ]

    first_row = features.iloc[0]
    expected_market_cap_change = (
        raw_df.loc[1, "coingecko_market_cap_usd"]
        / raw_df.loc[0, "coingecko_market_cap_usd"]
    ) - 1

    assert first_row["market_cap_change_1d"] == expected_market_cap_change
    assert first_row["volume_to_market_cap"] == (
        raw_df.loc[1, "coingecko_total_volume_usd"]
        / raw_df.loc[1, "coingecko_market_cap_usd"]
    )
    assert first_row["estimated_circulating_supply"] == 1_000_000.0
    assert output_path.exists()

    saved = pd.read_parquet(output_path)
    assert len(saved) == len(features)


def test_create_market_features_drops_infinite_change_features(tmp_path):
    input_path = tmp_path / "coingecko_market_chart_clean.csv"
    output_path = tmp_path / "market_features.parquet"
    raw_df = make_clean_market_rows()

    raw_df.loc[1, "coingecko_total_volume_usd"] = 0.0
    raw_df.to_csv(input_path, index=False)

    features = create_market_features(input_path, output_path)
    numeric_features = features.select_dtypes(include="number")

    assert np.isfinite(numeric_features.to_numpy()).all()
    assert "2024-01-03" not in features["date"].astype(str).tolist()

import numpy as np
import pandas as pd

from src.features.candle_features import create_candle_features


def make_clean_ohlcv_rows(periods=80):
    dates = pd.date_range("2024-01-01", periods=periods, freq="D", tz="UTC")
    close = np.arange(periods, dtype=float) + 100.0

    return pd.DataFrame(
        {
            "symbol": " btcusdt ",
            "open_time": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 2.0,
            "close": close,
            "volume": np.arange(periods, dtype=float) + 1000.0,
            "quote_asset_volume": np.arange(periods, dtype=float) + 100000.0,
            "number_of_trades": np.arange(periods, dtype=float) + 500.0,
        }
    )


def test_create_candle_features_preserves_symbol_and_adds_next_day_targets(tmp_path):
    input_path = tmp_path / "binance_ohlcv_clean.csv"
    output_path = tmp_path / "candle_features.parquet"
    raw_df = make_clean_ohlcv_rows()

    raw_df.to_csv(input_path, index=False)

    features = create_candle_features(input_path, output_path)

    assert "symbol" in features.columns
    assert "target_close_next_1d" in features.columns
    assert "target_return_next_1d" in features.columns
    assert features["symbol"].unique().tolist() == ["BTCUSDT"]
    assert len(features) == 7

    raw_df["open_time"] = pd.to_datetime(raw_df["open_time"], utc=True)

    for _, row in features.iterrows():
        next_close = raw_df.loc[
            raw_df["open_time"] == row["open_time"] + pd.Timedelta(days=1),
            "close",
        ].iloc[0]

        assert row["target_close_next_1d"] == next_close
        assert row["target_return_next_1d"] == (next_close / row["close"]) - 1

    assert features["open_time"].max() < raw_df["open_time"].max()
    assert output_path.exists()

    saved = pd.read_parquet(output_path)
    assert len(saved) == len(features)


def test_create_candle_features_drops_infinite_change_features(tmp_path):
    input_path = tmp_path / "binance_ohlcv_clean.csv"
    output_path = tmp_path / "candle_features.parquet"
    raw_df = make_clean_ohlcv_rows()

    raw_df.loc[72, "volume"] = 0.0
    raw_df.loc[72, "quote_asset_volume"] = 0.0
    raw_df.loc[72, "number_of_trades"] = 0.0
    raw_df.to_csv(input_path, index=False)

    features = create_candle_features(input_path, output_path)
    numeric_features = features.select_dtypes(include="number")

    assert np.isfinite(numeric_features.to_numpy()).all()

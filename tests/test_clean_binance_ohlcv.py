import pandas as pd

from src.transformers.clean_binance_ohlcv import clean_binance_ohlcv


def test_clean_binance_ohlcv_normalizes_and_drops_incomplete_candles(tmp_path):
    raw_path = tmp_path / "binance_ohlcv_raw.csv"
    output_path = tmp_path / "binance_ohlcv_clean.csv"
    future_close_time = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)
    future_open_time = future_close_time - pd.Timedelta(days=1)

    raw_data = pd.DataFrame(
        [
            {
                "symbol": " btcusdt ",
                "open_time": "2024-01-01 00:00:00+00:00",
                "close_time": "2024-01-02 00:00:00+00:00",
                "open": "42000.0",
                "high": "43000.0",
                "low": "41000.0",
                "close": "42500.0",
                "volume": "100.5",
                "quote_asset_volume": "4250000.0",
                "number_of_trades": "1200",
                "taker_buy_base_asset_volume": "55.0",
                "taker_buy_quote_asset_volume": "2337500.0",
            },
            {
                "symbol": "ETHUSDT",
                "open_time": future_open_time.isoformat(),
                "close_time": future_close_time.isoformat(),
                "open": "2200.0",
                "high": "2300.0",
                "low": "2100.0",
                "close": "2250.0",
                "volume": "200.0",
                "quote_asset_volume": "450000.0",
                "number_of_trades": "900",
                "taker_buy_base_asset_volume": "90.0",
                "taker_buy_quote_asset_volume": "202500.0",
            },
        ]
    )

    raw_data.to_csv(raw_path, index=False)

    cleaned = clean_binance_ohlcv(raw_path, output_path)

    assert len(cleaned) == 1
    assert cleaned.loc[0, "symbol"] == "BTCUSDT"
    assert str(cleaned.loc[0, "open_time"]) == "2024-01-01 00:00:00+00:00"
    assert cleaned.loc[0, "open"] == 42000.0
    assert cleaned.loc[0, "volume"] == 100.5
    assert output_path.exists()

    saved = pd.read_csv(output_path)
    assert len(saved) == 1

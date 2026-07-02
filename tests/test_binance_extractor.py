import pandas as pd
import requests

from src.extractors import binance


def test_fetch_binance_ohlcv_returns_normalized_dataframe(monkeypatch):
    captured = {}
    raw_klines = [
        [
            1704067200000,
            "42000.0",
            "43000.0",
            "41000.0",
            "42500.0",
            "100.5",
            1704153599999,
            "4250000.0",
            1200,
            "55.0",
            "2337500.0",
            "0",
        ]
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return raw_klines

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    df = binance.fetch_binance_ohlcv("BTCUSDT", interval="1d", limit=1)

    assert captured["url"] == "https://api.binance.com/api/v3/klines"
    assert captured["params"] == {
        "symbol": "BTCUSDT",
        "interval": "1d",
        "limit": 1,
    }
    assert captured["timeout"] == 10
    assert list(df.columns) == [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "symbol",
    ]
    assert df.loc[0, "symbol"] == "BTCUSDT"
    assert df.loc[0, "open"] == 42000.0
    assert df.loc[0, "volume"] == 100.5
    assert df.loc[0, "number_of_trades"] == 1200
    assert df.loc[0, "open_time"] == pd.Timestamp(
        "2024-01-01 00:00:00",
        tz="UTC",
    )

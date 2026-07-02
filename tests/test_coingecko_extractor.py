import pytest
import requests

from src.extractors import coingecko


def test_fetch_coingecko_market_chart_requires_api_key(monkeypatch, tmp_path):
    def fail_get(*args, **kwargs):
        raise AssertionError("requests.get should not be called without an API key")

    monkeypatch.setattr(coingecko, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    monkeypatch.delenv("COINGECKO_DEMO_API_KEY", raising=False)
    monkeypatch.delenv("COINGECKO_PRO_API_KEY", raising=False)
    monkeypatch.setattr(requests, "get", fail_get)

    with pytest.raises(RuntimeError, match="COINGECKO_API_KEY is required"):
        coingecko.fetch_coingecko_market_chart("bitcoin")


def test_fetch_coingecko_market_chart_uses_pro_api_config(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"prices": [[1704067200000, 42000.0]]}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(coingecko, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")
    monkeypatch.setenv("COINGECKO_API_PLAN", "pro")
    monkeypatch.setattr(requests, "get", fake_get)

    data = coingecko.fetch_coingecko_market_chart("bitcoin", days=30)

    assert data == {"prices": [[1704067200000, 42000.0]]}
    assert captured["url"] == (
        "https://pro-api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    )
    assert captured["headers"] == {"x-cg-pro-api-key": "test-key"}
    assert captured["params"] == {
        "vs_currency": "usd",
        "days": 30,
        "interval": "daily",
    }


def test_fetch_coingecko_market_chart_defaults_to_demo_safe_year(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"prices": [[1704067200000, 42000.0]]}

    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(coingecko, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")
    monkeypatch.setenv("COINGECKO_API_PLAN", "demo")
    monkeypatch.setattr(requests, "get", fake_get)

    coingecko.fetch_coingecko_market_chart("bitcoin")

    assert captured["params"]["days"] == 365


def test_fetch_coingecko_market_chart_rejects_demo_requests_above_one_year(
    monkeypatch,
    tmp_path,
):
    def fail_get(*args, **kwargs):
        raise AssertionError("requests.get should not be called for invalid demo days")

    monkeypatch.setattr(coingecko, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")
    monkeypatch.setenv("COINGECKO_API_PLAN", "demo")
    monkeypatch.setattr(requests, "get", fail_get)

    with pytest.raises(
        RuntimeError,
        match="CoinGecko Demo historical market_chart data is limited to 365 days.",
    ):
        coingecko.fetch_coingecko_market_chart("bitcoin", days=731)


def test_fetch_coingecko_market_chart_accepts_plan_specific_demo_key(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"prices": [[1704067200000, 42000.0]]}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(coingecko, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    monkeypatch.setenv("COINGECKO_DEMO_API_KEY", "demo-key")
    monkeypatch.setenv("COINGECKO_API_PLAN", "demo")
    monkeypatch.setattr(requests, "get", fake_get)

    coingecko.fetch_coingecko_market_chart("bitcoin", days=30)

    assert captured["url"] == (
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    )
    assert captured["headers"] == {"x-cg-demo-api-key": "demo-key"}


def test_fetch_coingecko_market_chart_accepts_plan_specific_pro_key(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"prices": [[1704067200000, 42000.0]]}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(coingecko, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    monkeypatch.setenv("COINGECKO_PRO_API_KEY", "pro-key")
    monkeypatch.setenv("COINGECKO_API_PLAN", "pro")
    monkeypatch.setattr(requests, "get", fake_get)

    coingecko.fetch_coingecko_market_chart("bitcoin", days=30)

    assert captured["url"] == (
        "https://pro-api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    )
    assert captured["headers"] == {"x-cg-pro-api-key": "pro-key"}

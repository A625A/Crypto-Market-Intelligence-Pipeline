import pytest
import requests

from src.extractors import fred_macro


def test_fetch_fred_series_observations_calls_fred_api(monkeypatch, tmp_path):
    captured = {}
    expected_data = {
        "observations": [
            {
                "date": "2024-01-01",
                "value": "4.05",
            }
        ]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return expected_data

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(fred_macro, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.setenv("FRED_API_KEY", "test-fred-key")
    monkeypatch.setattr(requests, "get", fake_get)

    data = fred_macro.fetch_fred_series_observations(
        series_id="DGS10",
        observation_start="2024-01-01",
        observation_end="2024-01-31",
    )

    assert data == expected_data
    assert captured["url"] == "https://api.stlouisfed.org/fred/series/observations"
    assert captured["params"] == {
        "series_id": "DGS10",
        "api_key": "test-fred-key",
        "file_type": "json",
        "observation_start": "2024-01-01",
        "observation_end": "2024-01-31",
    }
    assert captured["timeout"] == 15


def test_fetch_fred_series_observations_requires_api_key(monkeypatch, tmp_path):
    def fail_get(*args, **kwargs):
        raise AssertionError("requests.get should not be called without an API key")

    monkeypatch.setattr(fred_macro, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(requests, "get", fail_get)

    with pytest.raises(RuntimeError, match="FRED_API_KEY is required"):
        fred_macro.fetch_fred_series_observations(
            series_id="DGS10",
            observation_start="2024-01-01",
            observation_end="2024-01-31",
        )

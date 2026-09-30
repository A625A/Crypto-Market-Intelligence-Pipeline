import pytest
import requests

from src.extractors import fred_macro


def test_fetch_fred_series_observations_calls_fred_api(monkeypatch, tmp_path):
    captured = {}
    expected_data = {
        "output_type": 4,
        "observations": [
            {
                "realtime_start": "2024-01-02",
                "realtime_end": "9999-12-31",
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
        "realtime_start": "2024-01-01",
        "realtime_end": "2024-01-31",
        "output_type": 4,
    }
    assert captured["timeout"] == 15


def test_fred_http_error_reports_reason_without_leaking_api_key(monkeypatch, tmp_path):
    import json
    import traceback

    response = requests.Response()
    response.status_code = 400
    response.url = "https://api.stlouisfed.org/fred/series/observations?api_key=test-secret"
    response._content = json.dumps({"error_message": "Too many vintage dates"}).encode()
    monkeypatch.setattr(fred_macro, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.setenv("FRED_API_KEY", "test-secret")
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError, match="Too many vintage dates") as caught:
        fred_macro.fetch_fred_series_observations("DGS10", "2024-01-01", "2024-01-31")

    assert "test-secret" not in "".join(traceback.format_exception(caught.value))


def test_incomplete_fred_fetch_preserves_existing_raw_file(monkeypatch, tmp_path):
    output = tmp_path / "fred.json"
    output.write_text("previous complete dataset")

    def fetch(series_id, **kwargs):
        if series_id == "DGS10":
            raise RuntimeError("Too many vintage dates")
        return {"output_type": 4, "observations": [{"value": "1"}]}

    monkeypatch.setattr(fred_macro, "fetch_fred_series_observations", fetch)
    monkeypatch.setattr(fred_macro.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="DGS10"):
        fred_macro.extract_fred_macro(output_path=output)
    assert output.read_text() == "previous complete dataset"


def test_complete_fred_fetch_writes_all_series(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(fred_macro, "fetch_fred_series_observations", lambda **kwargs: {
        "output_type": 4, "observations": [{"value": "1"}]
    })
    monkeypatch.setattr(fred_macro.time, "sleep", lambda _: None)
    output = tmp_path / "raw/fred.json"
    fred_macro.extract_fred_macro(output_path=output)
    assert set(json.loads(output.read_text())["series"]) == {
        "DGS10", "DGS2", "DFF", "CPIAUCSL", "UNRATE", "VIXCLS", "DTWEXBGS"
    }


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

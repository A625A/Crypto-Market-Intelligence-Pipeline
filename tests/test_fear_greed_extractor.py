import requests

from src.extractors import fear_greed


def test_fetch_fear_greed_calls_alternative_me_api(monkeypatch):
    captured = {}
    expected_data = {
        "data": [
            {
                "value": "45",
                "value_classification": "Fear",
                "timestamp": "1704067200",
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

    monkeypatch.setattr(requests, "get", fake_get)

    data = fear_greed.fetch_fear_greed(limit=365)

    assert data == expected_data
    assert captured["url"] == "https://api.alternative.me/fng/"
    assert captured["params"] == {
        "limit": 365,
        "format": "json",
    }
    assert captured["timeout"] == 10

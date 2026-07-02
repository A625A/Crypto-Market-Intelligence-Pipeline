import json

import pandas as pd

from src.transformers.clean_greed_fear import clean_fear_greed


def test_clean_fear_greed_normalizes_sentiment_records(tmp_path):
    raw_path = tmp_path / "fear_greed_raw.json"
    output_path = tmp_path / "fear_greed_clean.csv"

    raw_data = {
        "data": [
            {
                "value": "45",
                "value_classification": " Fear ",
                "timestamp": "1704067200",
            },
            {
                "value": "70",
                "value_classification": "Greed",
                "timestamp": "1704153600",
            },
        ]
    }

    raw_path.write_text(json.dumps(raw_data), encoding="utf-8")

    cleaned = clean_fear_greed(raw_path, output_path)

    assert list(cleaned.columns) == [
        "fear_greed_value",
        "date",
        "fear_greed_classification",
    ]
    assert len(cleaned) == 2
    assert cleaned["date"].astype(str).tolist() == [
        "2024-01-01",
        "2024-01-02",
    ]
    assert cleaned["fear_greed_value"].tolist() == [45, 70]
    assert cleaned["fear_greed_classification"].tolist() == ["Fear", "Greed"]
    assert output_path.exists()

    saved = pd.read_csv(output_path)
    assert len(saved) == 2

import pandas as pd

from src.processing import clean_data


def test_clean_data_removes_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    cleaned = clean_data(df)
    assert len(cleaned) == 2

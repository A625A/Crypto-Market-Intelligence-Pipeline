import pandas as pd

from src.features import build_features


def test_build_features_returns_dataframe():
    df = pd.DataFrame({"a": [1, 2, 3]})
    features = build_features(df)
    assert isinstance(features, pd.DataFrame)
    assert len(features) == 3

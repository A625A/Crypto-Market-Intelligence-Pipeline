"""
Feature engineering module.
Engineered features should be saved into data/final/.
"""

import pandas as pd


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create model-ready features."""
    features = df.copy()
    return features

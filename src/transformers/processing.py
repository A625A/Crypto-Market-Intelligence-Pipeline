"""
Data processing module.
Cleaned data should be saved into data/processed/.
"""

import pandas as pd


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a raw DataFrame."""
    cleaned = df.copy()
    cleaned = cleaned.drop_duplicates()
    return cleaned

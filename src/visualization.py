"""
Visualization module.
"""

import matplotlib.pyplot as plt
import pandas as pd


def plot_missing_values(df: pd.DataFrame) -> None:
    """Plot missing value counts by column."""
    missing = df.isna().sum().sort_values(ascending=False)
    missing = missing[missing > 0]

    if missing.empty:
        print("No missing values found.")
        return

    missing.plot(kind="bar")
    plt.title("Missing Values by Column")
    plt.ylabel("Missing Count")
    plt.tight_layout()
    plt.show()

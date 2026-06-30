"""
Model training and evaluation module.
"""

from typing import Any
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.linear_model import LogisticRegression


def train_baseline_classifier(
    X: pd.DataFrame,
    y: pd.Series,
    random_state: int = 42,
) -> Any:
    """Train a simple baseline classifier."""
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=random_state,
        stratify=y if y.nunique() <= 10 else None,
    )

    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))

    return model

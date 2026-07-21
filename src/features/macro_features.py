"""Create leakage-safe macro features from cleaned daily FRED data.

The output preserves the seven cleaned macroeconomic levels, adds trailing
movement and rolling features, and lags every non-date column by one row so a
date-t record contains information available through date t-1.
"""

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "data/processed/fred_macro_clean.csv"
OUTPUT_PATH = PROJECT_ROOT / "data/processed/features/macro_features.parquet"

ORIGINAL_LEVEL_COLUMNS = [
    "us_10y_treasury_rate",
    "us_2y_treasury_rate",
    "effective_federal_funds_rate",
    "consumer_price_index",
    "unemployment_rate",
    "vix_close",
    "trade_weighted_us_dollar_index",
]

ENGINEERED_FEATURE_COLUMNS = [
    "us_10y_change_7d",
    "us_10y_change_30d",
    "us_2y_change_7d",
    "us_2y_change_30d",
    "yield_spread_10y_2y",
    "yield_spread_change_7d",
    "yield_curve_inverted",
    "fed_funds_change_30d",
    "vix_return_1d",
    "vix_return_7d",
    "vix_zscore_30d",
    "dollar_return_1d",
    "dollar_return_7d",
    "dollar_zscore_30d",
    "cpi_change_90d",
    "cpi_yoy",
    "unemployment_change_90d",
]

OUTPUT_COLUMNS = ["date"] + ORIGINAL_LEVEL_COLUMNS + ENGINEERED_FEATURE_COLUMNS


def validate_input(df: pd.DataFrame) -> pd.DataFrame:
    """Validate, normalize, and date-sort cleaned FRED macro rows."""
    if df.empty:
        raise ValueError("Macro input is empty.")

    required_columns = {"date", *ORIGINAL_LEVEL_COLUMNS}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required macro columns: {sorted(missing_columns)}"
        )

    validated = df[["date"] + ORIGINAL_LEVEL_COLUMNS].copy(deep=True)

    if validated["date"].isna().any():
        raise ValueError("Input date contains missing values.")

    parsed_dates = pd.to_datetime(
        validated["date"],
        format="mixed",
        utc=True,
        errors="coerce",
    )

    if parsed_dates.isna().any():
        raise ValueError("Found invalid date values in macro input.")

    validated["date"] = parsed_dates.dt.date

    if validated["date"].duplicated().any():
        raise ValueError("Duplicate dates are not allowed in macro input.")

    for column in ORIGINAL_LEVEL_COLUMNS:
        source = validated[column]
        converted = pd.to_numeric(source, errors="coerce")
        invalid_values = source.notna() & converted.isna()

        if invalid_values.any():
            raise ValueError(f"{column} contains non-numeric values.")

        validated[column] = converted

    return validated.sort_values("date").reset_index(drop=True)


def safe_rolling_zscore(values: pd.Series) -> pd.Series:
    """Calculate a trailing 30-row z-score without dividing by zero."""
    rolling = values.rolling(window=30, min_periods=30)
    rolling_mean = rolling.mean()
    rolling_std = rolling.std().replace(0, np.nan)

    return ((values - rolling_mean) / rolling_std).replace(
        [np.inf, -np.inf],
        np.nan,
    )


def add_treasury_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add absolute 7-row and 30-row Treasury-rate changes."""
    features = df.copy()
    ten_year = features["us_10y_treasury_rate"]
    two_year = features["us_2y_treasury_rate"]

    features["us_10y_change_7d"] = ten_year.diff(7)
    features["us_10y_change_30d"] = ten_year.diff(30)
    features["us_2y_change_7d"] = two_year.diff(7)
    features["us_2y_change_30d"] = two_year.diff(30)

    return features


def add_yield_curve_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add 10Y-minus-2Y spread, spread change, and inversion state."""
    features = df.copy()
    spread = (
        features["us_10y_treasury_rate"]
        - features["us_2y_treasury_rate"]
    )

    features["yield_spread_10y_2y"] = spread
    features["yield_spread_change_7d"] = spread.diff(7)
    features["yield_curve_inverted"] = (
        spread.lt(0).astype("Int8").where(spread.notna())
    )

    return features


def add_fed_funds_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the absolute 30-row Federal Funds rate change."""
    features = df.copy()
    features["fed_funds_change_30d"] = features[
        "effective_federal_funds_rate"
    ].diff(30)

    return features


def add_vix_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add VIX percentage returns and a safe trailing z-score."""
    features = df.copy()
    vix = features["vix_close"]

    features["vix_return_1d"] = vix.pct_change(1, fill_method=None)
    features["vix_return_7d"] = vix.pct_change(7, fill_method=None)
    features["vix_zscore_30d"] = safe_rolling_zscore(vix)

    return features


def add_dollar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add dollar-index percentage returns and a safe trailing z-score."""
    features = df.copy()
    dollar = features["trade_weighted_us_dollar_index"]

    features["dollar_return_1d"] = dollar.pct_change(1, fill_method=None)
    features["dollar_return_7d"] = dollar.pct_change(7, fill_method=None)
    features["dollar_zscore_30d"] = safe_rolling_zscore(dollar)

    return features


def add_slow_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add long-horizon CPI and unemployment changes."""
    features = df.copy()
    cpi = features["consumer_price_index"]

    features["cpi_change_90d"] = cpi.pct_change(90, fill_method=None)
    features["cpi_yoy"] = cpi.pct_change(365, fill_method=None)
    features["unemployment_change_90d"] = features[
        "unemployment_rate"
    ].diff(90)

    return features


def add_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """Validate macro rows and calculate all unlagged trailing features."""
    features = validate_input(df)
    features = add_treasury_features(features)
    features = add_yield_curve_features(features)
    features = add_fed_funds_features(features)
    features = add_vix_features(features)
    features = add_dollar_features(features)
    features = add_slow_macro_features(features)

    features = features.replace([np.inf, -np.inf], np.nan)

    return features[OUTPUT_COLUMNS]


def lag_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """Shift every non-date macro column by exactly one row."""
    lagged = df.copy()
    non_date_columns = [column for column in lagged.columns if column != "date"]
    lagged[non_date_columns] = lagged[non_date_columns].shift(1)

    return lagged


def validate_output(
    df: pd.DataFrame,
    expected_dates: Sequence[object] | pd.Series,
) -> None:
    """Validate the saved macro feature schema, keys, rows, and values."""
    if df.empty:
        raise ValueError("Macro feature output is empty.")

    if "date" not in df.columns:
        raise ValueError("Macro feature output is missing the date column.")

    missing_columns = set(OUTPUT_COLUMNS) - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Missing expected macro feature columns: "
            f"{sorted(missing_columns)}"
        )

    if "symbol" in df.columns:
        raise ValueError("Macro feature output must not contain a symbol column.")

    if df["date"].isna().any():
        raise ValueError("Macro feature output contains missing dates.")

    if not df["date"].is_monotonic_increasing:
        raise ValueError("Macro feature output dates must be sorted.")

    if df["date"].duplicated().any():
        raise ValueError("Macro feature output contains duplicate dates.")

    expected_date_series = pd.Series(expected_dates).reset_index(drop=True)
    actual_date_series = df["date"].reset_index(drop=True)

    if len(df) != len(expected_date_series):
        raise ValueError("Macro feature output row count does not match the input.")

    if not actual_date_series.equals(expected_date_series):
        raise ValueError("Macro feature output dates do not match the input dates.")

    numeric_values = df.select_dtypes(include="number").to_numpy(
        dtype=float,
        na_value=np.nan,
    )

    if np.isinf(numeric_values).any():
        raise ValueError("Macro feature output contains infinite values.")


def create_macro_features(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Build, validate, and save leakage-safe macro feature rows."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Clean FRED macro file not found: {input_path}")

    source = pd.read_csv(input_path)
    logger.info("Loaded cleaned FRED macro data: %s rows", len(source))

    unlagged_features = add_macro_features(source)
    features = lag_macro_features(unlagged_features)
    validate_output(features, unlagged_features["date"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)

    logger.info(
        "Created macro features for %s rows from %s to %s",
        len(features),
        features["date"].min(),
        features["date"].max(),
    )
    logger.info("Saved macro features to %s", output_path)
    logger.info("Macro feature validation passed")

    return features


if __name__ == "__main__":
    create_macro_features()

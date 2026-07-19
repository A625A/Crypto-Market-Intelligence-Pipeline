"""Create daily market-sentiment features from Alternative.me data.

The Fear & Greed Index is market-wide. Features are calculated once per UTC
date and then aligned to the daily Binance grid for BTCUSDT, ETHUSDT, and
SOLUSDT. A day-D row contains only values from day D or earlier and is intended
for predicting a day-D+1 outcome.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEAR_GREED_INPUT_PATH = PROJECT_ROOT / "data/processed/fear_greed_clean.csv"
BINANCE_INPUT_PATH = PROJECT_ROOT / "data/processed/binance_ohlcv_clean.csv"
OUTPUT_PATH = PROJECT_ROOT / "data/processed/features/sentiment_features.parquet"

SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

CATEGORY_COLUMNS = [
    "is_extreme_fear",
    "is_fear",
    "is_neutral",
    "is_greed",
    "is_extreme_greed",
]

MARKET_FEATURE_COLUMNS = [
    "fear_greed_value",
    "fear_greed_change_1d",
    "fear_greed_change_7d",
    "fear_greed_change_14d",
    "fear_greed_sma_3",
    "fear_greed_sma_7",
    "fear_greed_sma_14",
    "fear_greed_sma_30",
    "fear_greed_std_7",
    "fear_greed_std_30",
    "normalized_fear_greed",
    "fear_greed_distance_from_neutral",
] + CATEGORY_COLUMNS

OUTPUT_COLUMNS = ["symbol", "date"] + MARKET_FEATURE_COLUMNS


def _require_columns(
    df: pd.DataFrame,
    required_columns: set[str],
    dataset_name: str,
) -> None:
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required {dataset_name} columns: {sorted(missing_columns)}"
        )


def _normalize_fear_greed(df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(df, {"date", "fear_greed_value"}, "Fear & Greed")

    normalized = df[["date", "fear_greed_value"]].copy()
    parsed_dates = pd.to_datetime(
        normalized["date"],
        format="mixed",
        utc=True,
        errors="coerce",
    )

    if parsed_dates.isna().any():
        raise ValueError("Found invalid Fear & Greed dates.")

    normalized["date"] = parsed_dates.dt.date
    normalized["fear_greed_value"] = pd.to_numeric(
        normalized["fear_greed_value"],
        errors="coerce",
    )

    if normalized["fear_greed_value"].isna().any():
        raise ValueError("Found invalid Fear & Greed values.")

    if not normalized["fear_greed_value"].between(0, 100).all():
        raise ValueError("Fear & Greed values must be between 0 and 100.")

    if normalized.duplicated(subset=["date"]).any():
        raise ValueError("Found duplicate Fear & Greed dates.")

    return normalized.sort_values("date").reset_index(drop=True)


def _validate_market_features(features: pd.DataFrame) -> None:
    valid_rows = features["fear_greed_value"].notna()
    missing_rows = ~valid_rows

    if missing_rows.any() and features.loc[
        missing_rows,
        MARKET_FEATURE_COLUMNS,
    ].notna().any().any():
        raise ValueError(
            "Dates without a Fear & Greed value must not contain sentiment features."
        )

    valid_features = features.loc[valid_rows]
    category_total = valid_features[CATEGORY_COLUMNS].sum(axis=1)

    if not category_total.eq(1).all():
        raise ValueError("Each Fear & Greed row must have exactly one category.")

    if not valid_features["normalized_fear_greed"].between(-1, 1).all():
        raise ValueError("Normalized Fear & Greed values must be between -1 and 1.")

    if not valid_features["fear_greed_distance_from_neutral"].ge(0).all():
        raise ValueError("Fear & Greed distance from neutral cannot be negative.")

    numeric_values = features.select_dtypes(include="number").to_numpy(
        dtype=float,
        na_value=np.nan,
    )

    if np.isinf(numeric_values).any():
        raise ValueError("Fear & Greed features contain infinite values.")


def add_fear_greed_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create trailing market-level features from cleaned Fear & Greed rows."""
    normalized = _normalize_fear_greed(df)
    complete_dates = pd.date_range(
        normalized["date"].min(),
        normalized["date"].max(),
        freq="D",
    ).date
    features = (
        normalized.set_index("date")
        .reindex(complete_dates)
        .rename_axis("date")
        .reset_index()
    )
    value = features["fear_greed_value"]

    features["fear_greed_change_1d"] = value.diff(1)
    features["fear_greed_change_7d"] = value.diff(7)
    features["fear_greed_change_14d"] = value.diff(14)

    for window in (3, 7, 14, 30):
        features[f"fear_greed_sma_{window}"] = value.rolling(
            window=window,
            min_periods=window,
        ).mean()

    for window in (7, 30):
        features[f"fear_greed_std_{window}"] = value.rolling(
            window=window,
            min_periods=window,
        ).std()

    features["normalized_fear_greed"] = (value - 50) / 50
    features["fear_greed_distance_from_neutral"] = (value - 50).abs()

    valid_value = value.notna()
    category_ranges = {
        "is_extreme_fear": (0, 24),
        "is_fear": (25, 44),
        "is_neutral": (45, 55),
        "is_greed": (56, 74),
        "is_extreme_greed": (75, 100),
    }

    for column, (lower, upper) in category_ranges.items():
        features[column] = (
            value.between(lower, upper).astype("Int8").where(valid_value)
        )

    features = features[["date"] + MARKET_FEATURE_COLUMNS]
    _validate_market_features(features)

    return features


def _build_binance_grid(df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(df, {"symbol", "open_time"}, "Binance")

    grid = df[["symbol", "open_time"]].copy()
    grid["symbol"] = grid["symbol"].astype("string").str.strip().str.upper()
    parsed_dates = pd.to_datetime(
        grid["open_time"],
        format="mixed",
        utc=True,
        errors="coerce",
    )

    if grid["symbol"].isna().any() or grid["symbol"].eq("").any():
        raise ValueError("Found invalid Binance symbols.")

    if parsed_dates.isna().any():
        raise ValueError("Found invalid Binance open_time values.")

    grid["date"] = parsed_dates.dt.date
    grid = grid.drop(columns=["open_time"])

    unsupported_symbols = sorted(set(grid["symbol"]) - set(SUPPORTED_SYMBOLS))

    if unsupported_symbols:
        raise ValueError(f"Found unsupported Binance symbols: {unsupported_symbols}")

    missing_symbols = sorted(set(SUPPORTED_SYMBOLS) - set(grid["symbol"]))

    if missing_symbols:
        raise ValueError(f"Binance grid is missing supported symbols: {missing_symbols}")

    if grid.duplicated(subset=["symbol", "date"]).any():
        raise ValueError("Binance grid contains duplicate symbol-date rows.")

    expected_symbols = set(SUPPORTED_SYMBOLS)
    incomplete_dates = [
        date
        for date, symbols in grid.groupby("date")["symbol"]
        if set(symbols) != expected_symbols
    ]

    if incomplete_dates:
        raise ValueError(
            "Binance grid is missing supported symbols for dates: "
            f"{incomplete_dates[:5]}"
        )

    return grid.sort_values(["symbol", "date"]).reset_index(drop=True)


def _validate_output(features: pd.DataFrame, grid: pd.DataFrame) -> None:
    _require_columns(features, set(OUTPUT_COLUMNS), "sentiment output")

    if features.duplicated(subset=["symbol", "date"]).any():
        raise ValueError("Sentiment output contains duplicate symbol-date rows.")

    if set(features["symbol"]) != set(SUPPORTED_SYMBOLS):
        raise ValueError("Sentiment output does not contain the expected symbols.")

    if len(features) != len(grid):
        raise ValueError("Sentiment output row count does not match the Binance grid.")

    expected_keys = pd.MultiIndex.from_frame(grid[["symbol", "date"]])
    actual_keys = pd.MultiIndex.from_frame(features[["symbol", "date"]])

    if not actual_keys.equals(expected_keys):
        raise ValueError("Sentiment output keys do not match the Binance grid.")

    if not features.equals(
        features.sort_values(["symbol", "date"]).reset_index(drop=True)
    ):
        raise ValueError("Sentiment output must be sorted by symbol and date.")

    _validate_market_features(features)


def create_sentiment_features(
    fear_greed_path: Path = FEAR_GREED_INPUT_PATH,
    binance_path: Path = BINANCE_INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Build and save Fear & Greed features aligned to the Binance daily grid."""
    fear_greed_path = Path(fear_greed_path)
    binance_path = Path(binance_path)
    output_path = Path(output_path)

    if not fear_greed_path.exists():
        raise FileNotFoundError(f"Clean Fear & Greed file not found: {fear_greed_path}")

    if not binance_path.exists():
        raise FileNotFoundError(f"Clean Binance file not found: {binance_path}")

    fear_greed_df = pd.read_csv(fear_greed_path)
    binance_df = pd.read_csv(binance_path)

    logger.info("Loaded cleaned Fear & Greed data: %s rows", len(fear_greed_df))
    logger.info("Loaded cleaned Binance grid data: %s rows", len(binance_df))

    market_features = add_fear_greed_features(fear_greed_df)
    grid = _build_binance_grid(binance_df)

    grid_dates = set(grid["date"])
    fear_greed_dates = set(
        market_features.loc[
            market_features["fear_greed_value"].notna(),
            "date",
        ]
    )
    missing_fear_greed_dates = sorted(grid_dates - fear_greed_dates)
    unused_fear_greed_dates = sorted(fear_greed_dates - grid_dates)

    if missing_fear_greed_dates:
        logger.warning(
            "Preserving %s Binance dates without Fear & Greed values: %s",
            len(missing_fear_greed_dates),
            missing_fear_greed_dates[:5],
        )

    if unused_fear_greed_dates:
        logger.warning(
            "Ignoring %s Fear & Greed dates outside the Binance grid",
            len(unused_fear_greed_dates),
        )

    features = grid.merge(
        market_features,
        on="date",
        how="left",
        validate="many_to_one",
    )

    features = features[OUTPUT_COLUMNS].sort_values(
        ["symbol", "date"]
    ).reset_index(drop=True)

    _validate_output(features, grid)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)

    logger.info(
        "Created sentiment features for %s rows from %s to %s",
        len(features),
        features["date"].min(),
        features["date"].max(),
    )
    logger.info("Sentiment symbols: %s", sorted(features["symbol"].unique()))
    logger.info("Saved sentiment features to %s", output_path)
    logger.info("Sentiment feature validation passed")

    return features


if __name__ == "__main__":
    create_sentiment_features()

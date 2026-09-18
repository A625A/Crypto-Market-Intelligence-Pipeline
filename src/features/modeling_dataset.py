"""Join daily features for forecasts made after the UTC candle closes.

Row t predicts close[t+1] / close[t] - 1 for the same symbol. Macro features
already contain only releases through t-1. The file builder verifies that
contract by replaying the initial-release FRED cleaning and feature pipeline.
Missing features and unknown final-day labels remain null; no imputation is fit.
"""

import argparse
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from src.features import macro_features
from src.transformers.clean_fred_macro import clean_fred_macro


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_PATH = PROJECT_ROOT / "data/processed"
FEATURES_PATH = PROCESSED_PATH / "features"
OUTPUT_PATH = PROCESSED_PATH / "modeling_dataset.parquet"
TARGET_COLUMNS = [
    "target_return_next_1d",
    "target_direction_next_1d",
    "target_above_threshold_next_1d",
]
KEYS = ["symbol", "date"]
FAMILIES = ("candle", "market", "macro", "sentiment")
AUDIT_COLUMNS = [f"has_{name}_features" for name in FAMILIES] + [
    "macro_information_date", "missing_feature_count",
]


def _normalize(frame: pd.DataFrame, name: str, *, global_data=False) -> pd.DataFrame:
    """Normalize UTC day keys and reject ambiguous keys or invalid feature values."""
    if frame.empty:
        raise ValueError(f"{name} input is empty.")
    if not frame.columns.is_unique:
        raise ValueError(f"Duplicate column names in {name}.")
    result = frame.copy(deep=True)
    if name in ("candles", "prices"):
        if "open_time" not in result or "date" in result:
            raise ValueError(f"{name} requires open_time, without a competing date column.")
        result = result.rename(columns={"open_time": "date"})
    keys = ["date"] if global_data else KEYS
    missing = set(keys) - set(result.columns)
    if missing:
        raise ValueError(f"Missing {name} keys: {sorted(missing)}")
    dates = pd.to_datetime(result["date"], format="mixed", utc=True, errors="coerce")
    if dates.isna().any():
        raise ValueError(f"Invalid date in {name}.")
    if not dates.eq(dates.dt.normalize()).all():
        raise ValueError(f"{name} dates must represent UTC midnight daily observations.")
    result["date"] = dates.dt.tz_localize(None)
    if not global_data:
        result["symbol"] = result["symbol"].astype("string").str.strip().str.upper()
        if result["symbol"].isna().any() or result["symbol"].eq("").any():
            raise ValueError(f"Invalid symbol in {name}.")
    elif "symbol" in result:
        raise ValueError("Macro features must be global, without a symbol column.")
    if result.duplicated(keys).any():
        raise ValueError(f"Duplicate {name} keys: {keys}")
    reserved = set(AUDIT_COLUMNS) & set(result.columns)
    if reserved:
        raise ValueError(f"Colliding reserved columns in {name}: {sorted(reserved)}")
    targets = [column for column in result if column.startswith("target_")]
    if targets and name != "candles":
        raise ValueError(f"Unexpected target columns in {name}: {targets}")
    # Legacy candle labels are rebuilt from the independent clean price grid.
    result = result.drop(columns=targets)
    if name == "market":
        result = result.drop(columns=["coingecko_id"], errors="ignore")
    for column in set(result.columns) - set(keys):
        values = result[column]
        numeric = pd.to_numeric(values, errors="coerce")
        if (values.notna() & numeric.isna()).any():
            raise ValueError(f"{name}.{column} must be numeric.")
        if np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
            raise ValueError(f"{name}.{column} contains infinite values.")
        result[column] = numeric
    return result.sort_values(keys).reset_index(drop=True)


def _require_daily(frame: pd.DataFrame, name: str, *, global_data=False) -> None:
    deltas = frame["date"].diff() if global_data else frame.groupby("symbol")["date"].diff()
    if not deltas.dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError(f"{name} must contain consecutive daily dates within each asset.")


def verify_macro_provenance(macro: pd.DataFrame, fred_raw_path: Path) -> None:
    """Reject revised, stale, or unlagged macro artifacts using the raw release history."""
    with TemporaryDirectory(prefix="modeling-fred-") as directory:
        clean = clean_fred_macro(Path(fred_raw_path), Path(directory) / "fred.csv")
    expected = macro_features.lag_macro_features(macro_features.add_macro_features(clean))
    expected = _normalize(expected, "macro", global_data=True)
    actual = _normalize(macro, "macro", global_data=True)
    try:
        assert_frame_equal(
            actual, expected, check_dtype=False, check_like=True,
            check_exact=False, rtol=1e-12, atol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            "Macro provenance check failed: features do not match initial-release "
            "FRED values lagged by one calendar day. Rebuild clean_fred_macro "
            "and macro_features from the current raw file."
        ) from error


def build_modeling_dataset(
    candles: pd.DataFrame,
    market: pd.DataFrame,
    macro: pd.DataFrame,
    sentiment: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    return_threshold: float = 0.01,
) -> pd.DataFrame:
    """Combine frames; macro must come from the verified initial-release pipeline.

    Use create_modeling_dataset for file inputs: it additionally proves raw FRED
    provenance. Auxiliary coverage gaps are kept as nulls. Price-grid gaps fail
    because both trailing features and the target depend on consecutive days.
    """
    if not np.isfinite(return_threshold):
        raise ValueError("return_threshold must be finite.")
    required_prices = {"symbol", "open_time", "close"}
    if not required_prices.issubset(prices.columns):
        raise ValueError(f"Prices require columns: {sorted(required_prices)}")
    prices = _normalize(prices[["symbol", "open_time", "close"]], "prices")
    if prices["close"].isna().any() or not prices["close"].gt(0).all():
        raise ValueError("Price close values must be finite and positive.")
    _require_daily(prices, "prices")
    if prices["date"].ge(pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)).any():
        raise ValueError("Price grid contains incomplete current-day or future candles.")
    sources = {
        "candle": _normalize(candles, "candles"),
        "market": _normalize(market, "market"),
        "macro": _normalize(macro, "macro", global_data=True),
        "sentiment": _normalize(sentiment, "sentiment"),
    }
    missing_macro = set(macro_features.OUTPUT_COLUMNS) - set(sources["macro"].columns)
    if missing_macro:
        raise ValueError(f"Missing macro feature columns: {sorted(missing_macro)}")
    _require_daily(sources["macro"], "macro", global_data=True)
    if "close" not in sources["candle"]:
        raise ValueError("Candle features require close for consistency checks.")
    candle_prices = sources["candle"][KEYS + ["close"]].merge(
        prices, on=KEYS, how="left", validate="one_to_one", suffixes=("", "_price"),
    )
    if not np.isclose(
        candle_prices["close"], candle_prices["close_price"], rtol=1e-12, atol=0,
    ).all():
        raise ValueError("Candle close values and keys must match the clean price grid.")
    sources["candle"] = sources["candle"].drop(columns="close")
    sources["macro"]["macro_information_date"] = sources["macro"]["date"] - pd.Timedelta(days=1)

    result = prices.copy()
    symbols = set(prices["symbol"])
    for name, source in sources.items():
        keys = ["date"] if name == "macro" else KEYS
        if name != "macro":
            unknown = set(source["symbol"]) - symbols
            if unknown:
                raise ValueError(f"{name} contains unknown symbols: {sorted(unknown)}")
        collisions = (set(source.columns) & set(result.columns)) - set(keys)
        if collisions:
            raise ValueError(f"Colliding {name} feature columns: {sorted(collisions)}")
        indicator = f"has_{name}_features"
        source = source.assign(**{indicator: True})
        result = result.merge(
            source, on=keys, how="left",
            validate="many_to_one" if name == "macro" else "one_to_one",
        )
        result[indicator] = result[indicator].fillna(False).astype(bool)

    predictors = [column for column in result if column not in KEYS + AUDIT_COLUMNS]
    result["missing_feature_count"] = result[predictors].isna().sum(axis=1)
    # A calendar-key join cannot accidentally label t with t+2 or another asset.
    tomorrow = prices.rename(columns={"close": "_next_close"}).copy()
    tomorrow["date"] -= pd.Timedelta(days=1)
    result = result.merge(tomorrow, on=KEYS, how="left", validate="one_to_one")
    returns = (result.pop("_next_close") - result["close"]) / result["close"]
    if np.isinf(returns.dropna()).any():
        raise ValueError("Target return contains infinite values.")
    result[TARGET_COLUMNS[0]] = returns
    result[TARGET_COLUMNS[1]] = returns.gt(0).astype("Int8").where(returns.notna())
    result[TARGET_COLUMNS[2]] = returns.gt(return_threshold).astype("Int8").where(returns.notna())
    result = result.sort_values(KEYS).reset_index(drop=True)
    result.attrs = {
        "return_threshold": float(return_threshold),
        "prediction_time": "after the UTC day close",
        "macro_information_cutoff": "previous UTC calendar day",
    }
    return result


def create_modeling_dataset(
    candles_path: Path = FEATURES_PATH / "candle_features.parquet",
    market_path: Path = FEATURES_PATH / "market_features.parquet",
    macro_path: Path = FEATURES_PATH / "macro_features.parquet",
    sentiment_path: Path = FEATURES_PATH / "sentiment_features.parquet",
    prices_path: Path = PROCESSED_PATH / "binance_ohlcv_clean.csv",
    fred_raw_path: Path = PROJECT_ROOT / "data/raw/fred_macro_raw.json",
    output_path: Path = OUTPUT_PATH,
    *,
    return_threshold: float = 0.01,
) -> pd.DataFrame:
    """Validate source artifacts, join features and labels, and atomically save Parquet."""
    paths = {"candles": candles_path, "market": market_path,
             "macro": macro_path, "sentiment": sentiment_path, "prices": prices_path}
    frames = {}
    for name, path in paths.items():
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"{name} input not found: {path}")
        frames[name] = pd.read_csv(path) if name == "prices" else pd.read_parquet(path)
    verify_macro_provenance(frames["macro"], fred_raw_path)
    result = build_modeling_dataset(**frames, return_threshold=return_threshold)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output_path.parent, suffix=".parquet", delete=False) as file:
        temporary_path = Path(file.name)
    try:
        result.to_parquet(temporary_path, index=False)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    logger.info("Saved %s rows, %s assets to %s", len(result), result["symbol"].nunique(), output_path)
    logger.info("Rows missing features: %s; rows without next-day labels: %s",
                result["missing_feature_count"].gt(0).sum(), result[TARGET_COLUMNS[0]].isna().sum())
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--return-threshold", type=float, default=0.01,
                        help="Strict next-day return cutoff as a fraction (default: 0.01 = 1%%).")
    args = parser.parse_args()
    create_modeling_dataset(output_path=args.output, return_threshold=args.return_threshold)

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from src.features import macro_features


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


def make_macro_rows(periods: int = 400) -> pd.DataFrame:
    step = np.arange(periods, dtype=float)

    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=periods, freq="D").astype(
                str
            ),
            "us_10y_treasury_rate": 2.0 + (step * 0.01),
            "us_2y_treasury_rate": 2.2 + (step * 0.005),
            "effective_federal_funds_rate": 5.5 - (step * 0.002),
            "consumer_price_index": 200.0 + (step * 0.2),
            "unemployment_rate": 4.0 + (step * 0.01),
            "vix_close": 15.0 + (step * 0.25),
            "trade_weighted_us_dollar_index": 90.0 + (step * 0.1),
        }
    )


def test_validate_input_sorts_converts_numeric_values_and_preserves_input():
    raw = make_macro_rows(40).iloc[::-1].reset_index(drop=True)
    raw["vix_close"] = raw["vix_close"].astype(str)
    original = raw.copy(deep=True)

    validated = macro_features.validate_input(raw)

    assert_frame_equal(raw, original)
    assert validated["date"].is_monotonic_increasing
    assert pd.api.types.is_numeric_dtype(validated["vix_close"])
    assert not validated["date"].duplicated().any()


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda frame: frame.iloc[0:0], "empty"),
        (
            lambda frame: frame.drop(columns=["vix_close"]),
            "Missing required macro columns.*vix_close",
        ),
        (lambda frame: frame.assign(date=pd.NA), "date contains missing"),
        (lambda frame: frame.assign(date="not-a-date"), "invalid date"),
        (
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "Duplicate dates",
        ),
        (
            lambda frame: frame.assign(vix_close="not-numeric"),
            "vix_close.*non-numeric",
        ),
    ],
)
def test_validate_input_rejects_invalid_macro_data(mutator, message):
    with pytest.raises(ValueError, match=message):
        macro_features.validate_input(mutator(make_macro_rows(40)))


def test_treasury_and_fed_features_use_absolute_differences():
    validated = macro_features.validate_input(make_macro_rows())
    treasury = macro_features.add_treasury_features(validated)
    fed_funds = macro_features.add_fed_funds_features(validated)

    assert treasury.loc[7, "us_10y_change_7d"] == pytest.approx(
        validated.loc[7, "us_10y_treasury_rate"]
        - validated.loc[0, "us_10y_treasury_rate"]
    )
    assert treasury.loc[30, "us_10y_change_30d"] == pytest.approx(0.30)
    assert treasury.loc[7, "us_2y_change_7d"] == pytest.approx(0.035)
    assert treasury.loc[30, "us_2y_change_30d"] == pytest.approx(0.15)
    assert fed_funds.loc[30, "fed_funds_change_30d"] == pytest.approx(-0.06)


def test_yield_curve_features_match_spread_change_and_inversion_definitions():
    validated = macro_features.validate_input(make_macro_rows())

    features = macro_features.add_yield_curve_features(validated)

    expected_spread = (
        validated["us_10y_treasury_rate"]
        - validated["us_2y_treasury_rate"]
    )
    assert_series_equal(
        features["yield_spread_10y_2y"],
        expected_spread.rename("yield_spread_10y_2y"),
    )
    assert features.loc[7, "yield_spread_change_7d"] == pytest.approx(
        expected_spread.iloc[7] - expected_spread.iloc[0]
    )
    assert features.loc[0, "yield_curve_inverted"] == 1
    assert features.loc[100, "yield_curve_inverted"] == 0
    assert str(features["yield_curve_inverted"].dtype) == "Int8"


def test_vix_and_dollar_features_use_percentage_returns():
    validated = macro_features.validate_input(make_macro_rows())
    vix = macro_features.add_vix_features(validated)
    dollar = macro_features.add_dollar_features(validated)

    assert vix.loc[1, "vix_return_1d"] == pytest.approx(
        (validated.loc[1, "vix_close"] / validated.loc[0, "vix_close"]) - 1
    )
    assert vix.loc[7, "vix_return_7d"] == pytest.approx(
        (validated.loc[7, "vix_close"] / validated.loc[0, "vix_close"]) - 1
    )
    assert dollar.loc[1, "dollar_return_1d"] == pytest.approx(
        (
            validated.loc[1, "trade_weighted_us_dollar_index"]
            / validated.loc[0, "trade_weighted_us_dollar_index"]
        )
        - 1
    )
    assert dollar.loc[7, "dollar_return_7d"] == pytest.approx(
        (
            validated.loc[7, "trade_weighted_us_dollar_index"]
            / validated.loc[0, "trade_weighted_us_dollar_index"]
        )
        - 1
    )


def test_slow_macro_features_use_requested_long_horizons():
    validated = macro_features.validate_input(make_macro_rows())

    features = macro_features.add_slow_macro_features(validated)

    assert features.loc[90, "cpi_change_90d"] == pytest.approx(
        (
            validated.loc[90, "consumer_price_index"]
            / validated.loc[0, "consumer_price_index"]
        )
        - 1
    )
    assert features.loc[365, "cpi_yoy"] == pytest.approx(
        (
            validated.loc[365, "consumer_price_index"]
            / validated.loc[0, "consumer_price_index"]
        )
        - 1
    )
    assert features.loc[90, "unemployment_change_90d"] == pytest.approx(0.90)
    assert "cpi_change_1d" not in features
    assert "unemployment_change_1d" not in features


def test_safe_rolling_zscore_requires_30_rows_and_handles_constant_series():
    values = pd.Series(np.arange(1.0, 36.0))

    zscore = macro_features.safe_rolling_zscore(values)

    expected = (
        values.iloc[29] - values.iloc[:30].mean()
    ) / values.iloc[:30].std()
    assert zscore.iloc[:29].isna().all()
    assert zscore.iloc[29] == pytest.approx(expected)

    constant_zscore = macro_features.safe_rolling_zscore(pd.Series([5.0] * 35))
    assert constant_zscore.isna().all()
    assert not np.isinf(constant_zscore.to_numpy()).any()


def test_add_macro_features_replaces_only_infinities_with_nan():
    raw = make_macro_rows()
    raw.loc[0, "vix_close"] = 0.0
    raw.loc[0, "trade_weighted_us_dollar_index"] = 0.0

    features = macro_features.add_macro_features(raw)
    numeric = features.select_dtypes(include="number").to_numpy(
        dtype=float,
        na_value=np.nan,
    )

    assert not np.isinf(numeric).any()
    assert pd.isna(features.loc[1, "vix_return_1d"])
    assert pd.isna(features.loc[1, "dollar_return_1d"])


def test_lag_macro_features_shifts_every_non_date_column_without_backfill():
    raw = make_macro_rows()
    raw.loc[50, "vix_close"] = np.nan
    unlagged = macro_features.add_macro_features(raw)

    lagged = macro_features.lag_macro_features(unlagged)

    assert_series_equal(lagged["date"], unlagged["date"])
    assert lagged.loc[0, OUTPUT_COLUMNS[1:]].isna().all()
    assert_series_equal(
        lagged.loc[100, OUTPUT_COLUMNS[1:]],
        unlagged.loc[99, OUTPUT_COLUMNS[1:]],
        check_names=False,
    )
    assert pd.isna(lagged.loc[51, "vix_close"])
    assert lagged.loc[:29, "vix_zscore_30d"].isna().all()
    assert pd.notna(lagged.loc[30, "vix_zscore_30d"])
    assert lagged.loc[:365, "cpi_yoy"].isna().all()
    assert pd.notna(lagged.loc[366, "cpi_yoy"])


def test_create_macro_features_writes_complete_sorted_one_row_per_date_output(
    tmp_path,
):
    input_path = tmp_path / "fred_macro_clean.csv"
    output_path = tmp_path / "features" / "macro_features.parquet"
    raw = make_macro_rows().iloc[::-1].reset_index(drop=True)
    original = raw.copy(deep=True)
    raw.to_csv(input_path, index=False)

    features = macro_features.create_macro_features(input_path, output_path)

    assert_frame_equal(raw, original)
    assert list(features.columns) == OUTPUT_COLUMNS
    assert len(features) == len(raw)
    assert features["date"].is_monotonic_increasing
    assert not features["date"].duplicated().any()
    assert "symbol" not in features.columns
    assert output_path.exists()
    assert len(pd.read_parquet(output_path)) == len(features)

    expected_unlagged = macro_features.add_macro_features(raw)
    assert_series_equal(
        features.loc[200, OUTPUT_COLUMNS[1:]],
        expected_unlagged.loc[199, OUTPUT_COLUMNS[1:]],
        check_names=False,
    )


def test_validate_output_rejects_missing_columns_and_infinite_values():
    unlagged = macro_features.add_macro_features(make_macro_rows())
    output = macro_features.lag_macro_features(unlagged)
    expected_dates = unlagged["date"]

    macro_features.validate_output(output, expected_dates)

    with pytest.raises(ValueError, match="Missing expected macro feature columns"):
        macro_features.validate_output(output.drop(columns=["cpi_yoy"]), expected_dates)

    infinite_output = output.copy()
    infinite_output.loc[100, "vix_return_1d"] = np.inf

    with pytest.raises(ValueError, match="infinite"):
        macro_features.validate_output(infinite_output, expected_dates)

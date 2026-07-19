import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import sentiment_features


SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
OUTPUT_COLUMNS = [
    "symbol",
    "date",
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
    "is_extreme_fear",
    "is_fear",
    "is_neutral",
    "is_greed",
    "is_extreme_greed",
]


def make_fear_greed(values, start="2024-01-01"):
    dates = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(
        {
            "fear_greed_value": values,
            "date": dates.astype(str),
            "fear_greed_classification": "Neutral",
        }
    )


def make_binance_grid(dates, symbols=SUPPORTED_SYMBOLS):
    return pd.DataFrame(
        [
            {"symbol": symbol, "open_time": pd.Timestamp(date, tz="UTC")}
            for symbol in symbols
            for date in dates
        ]
    )


def test_add_fear_greed_features_normalizes_values_and_category_boundaries():
    values = [24, 25, 44, 45, 55, 56, 74, 75]

    features = sentiment_features.add_fear_greed_features(make_fear_greed(values))

    assert features["fear_greed_value"].tolist() == values
    assert features["normalized_fear_greed"].tolist() == pytest.approx(
        [(value - 50) / 50 for value in values]
    )
    assert features["fear_greed_distance_from_neutral"].tolist() == [
        abs(value - 50) for value in values
    ]
    assert features[
        [
            "is_extreme_fear",
            "is_fear",
            "is_neutral",
            "is_greed",
            "is_extreme_greed",
        ]
    ].values.tolist() == [
        [1, 0, 0, 0, 0],
        [0, 1, 0, 0, 0],
        [0, 1, 0, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 0, 1, 0],
        [0, 0, 0, 1, 0],
        [0, 0, 0, 0, 1],
    ]


def test_add_fear_greed_features_uses_trailing_changes_and_full_windows():
    values = list(range(1, 36))

    features = sentiment_features.add_fear_greed_features(make_fear_greed(values))

    assert pd.isna(features.loc[0, "fear_greed_change_1d"])
    assert features.loc[1, "fear_greed_change_1d"] == 1
    assert pd.isna(features.loc[6, "fear_greed_change_7d"])
    assert features.loc[7, "fear_greed_change_7d"] == 7
    assert pd.isna(features.loc[1, "fear_greed_sma_3"])
    assert features.loc[2, "fear_greed_sma_3"] == pytest.approx(2.0)
    assert features.loc[6, "fear_greed_sma_7"] == pytest.approx(4.0)
    assert features.loc[13, "fear_greed_sma_14"] == pytest.approx(7.5)
    assert features.loc[29, "fear_greed_sma_30"] == pytest.approx(15.5)
    assert features.loc[6, "fear_greed_std_7"] == pytest.approx(
        pd.Series(values[:7]).std()
    )
    assert features.loc[29, "fear_greed_std_30"] == pytest.approx(
        pd.Series(values[:30]).std()
    )


def test_add_fear_greed_features_calculates_exact_14_day_change():
    values = list(range(20, 40))

    features = sentiment_features.add_fear_greed_features(make_fear_greed(values))

    assert features.loc[:13, "fear_greed_change_14d"].isna().all()
    assert features.loc[14, "fear_greed_change_14d"] == 14


def test_add_fear_greed_features_does_not_change_past_rows_when_future_added():
    historical = make_fear_greed(list(range(30, 65)))
    with_future = pd.concat(
        [historical, make_fear_greed([99], start="2024-02-05")],
        ignore_index=True,
    )

    historical_features = sentiment_features.add_fear_greed_features(historical)
    features_with_future = sentiment_features.add_fear_greed_features(
        with_future
    ).iloc[:-1]

    assert_frame_equal(
        historical_features.reset_index(drop=True),
        features_with_future.reset_index(drop=True),
    )


def test_add_fear_greed_features_preserves_calendar_gaps():
    fear_greed = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-03"],
            "fear_greed_value": [50, 60],
        }
    )

    features = sentiment_features.add_fear_greed_features(fear_greed)

    assert features["date"].astype(str).tolist() == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]
    missing_day = features.loc[features["date"].astype(str) == "2024-01-02"]
    day_after_gap = features.loc[
        features["date"].astype(str) == "2024-01-03"
    ].iloc[0]
    assert missing_day[OUTPUT_COLUMNS[2:]].isna().all().all()
    assert pd.isna(day_after_gap["fear_greed_change_1d"])


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "duplicate Fear & Greed dates",
        ),
        (
            lambda frame: frame.assign(fear_greed_value=101),
            "between 0 and 100",
        ),
        (
            lambda frame: frame.assign(date="not-a-date"),
            "invalid Fear & Greed dates",
        ),
    ],
)
def test_add_fear_greed_features_rejects_invalid_input(mutator, message):
    with pytest.raises(ValueError, match=message):
        sentiment_features.add_fear_greed_features(
            mutator(make_fear_greed([50, 51]))
        )


def test_create_sentiment_features_aligns_market_values_to_exact_binance_grid(
    tmp_path,
):
    fear_path = tmp_path / "fear_greed_clean.csv"
    binance_path = tmp_path / "binance_ohlcv_clean.csv"
    output_path = tmp_path / "sentiment_features.parquet"
    fear_df = make_fear_greed(list(range(30, 65)))
    grid_dates = fear_df["date"].tolist()[::2]
    binance_df = make_binance_grid(grid_dates)
    fear_df.to_csv(fear_path, index=False)
    binance_df.to_csv(binance_path, index=False)

    features = sentiment_features.create_sentiment_features(
        fear_path,
        binance_path,
        output_path,
    )

    assert output_path.exists()
    assert list(features.columns) == OUTPUT_COLUMNS
    assert len(features) == len(binance_df)
    assert not features.duplicated(["symbol", "date"]).any()
    assert sorted(features["symbol"].unique().tolist()) == sorted(SUPPORTED_SYMBOLS)
    same_date = features.loc[features["date"] == features["date"].min()]
    assert same_date["fear_greed_value"].nunique() == 1
    assert same_date["normalized_fear_greed"].nunique() == 1
    assert features["date"].astype(str).unique().tolist() == grid_dates
    assert len(pd.read_parquet(output_path)) == len(features)


def test_create_sentiment_features_preserves_missing_fear_greed_date(
    tmp_path,
    caplog,
):
    fear_path = tmp_path / "fear_greed_clean.csv"
    binance_path = tmp_path / "binance_ohlcv_clean.csv"
    output_path = tmp_path / "sentiment_features.parquet"
    pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-03"],
            "fear_greed_value": [50, 60],
        }
    ).to_csv(fear_path, index=False)
    make_binance_grid(["2024-01-01", "2024-01-02", "2024-01-03"]).to_csv(
        binance_path,
        index=False,
    )

    features = sentiment_features.create_sentiment_features(
        fear_path,
        binance_path,
        output_path,
    )

    missing_date_rows = features.loc[
        features["date"] == pd.Timestamp("2024-01-02").date()
    ]
    assert len(features) == 9
    assert len(missing_date_rows) == 3
    assert missing_date_rows[OUTPUT_COLUMNS[2:]].isna().all().all()
    assert "Preserving 1 Binance dates without Fear & Greed values" in caplog.text


def test_create_sentiment_features_rejects_invalid_binance_grid(tmp_path):
    fear_path = tmp_path / "fear_greed_clean.csv"
    output_path = tmp_path / "sentiment_features.parquet"
    make_fear_greed([50]).to_csv(fear_path, index=False)

    duplicate_grid_path = tmp_path / "duplicate_binance.csv"
    duplicate_grid = make_binance_grid(["2024-01-01"])
    duplicate_grid = pd.concat(
        [duplicate_grid, duplicate_grid.iloc[[0]]],
        ignore_index=True,
    )
    duplicate_grid.to_csv(duplicate_grid_path, index=False)

    with pytest.raises(ValueError, match="duplicate symbol-date rows"):
        sentiment_features.create_sentiment_features(
            fear_path,
            duplicate_grid_path,
            output_path,
        )

    unsupported_grid_path = tmp_path / "unsupported_binance.csv"
    make_binance_grid(["2024-01-01"], symbols=["DOGEUSDT"]).to_csv(
        unsupported_grid_path,
        index=False,
    )

    with pytest.raises(ValueError, match="unsupported Binance symbols"):
        sentiment_features.create_sentiment_features(
            fear_path,
            unsupported_grid_path,
            output_path,
        )


def test_sentiment_output_contains_no_infinite_values_when_index_is_constant(
    tmp_path,
):
    fear_path = tmp_path / "fear_greed_clean.csv"
    binance_path = tmp_path / "binance_ohlcv_clean.csv"
    output_path = tmp_path / "sentiment_features.parquet"
    fear_df = make_fear_greed([50] * 35)
    fear_df.to_csv(fear_path, index=False)
    make_binance_grid(fear_df["date"].tolist()).to_csv(binance_path, index=False)

    features = sentiment_features.create_sentiment_features(
        fear_path,
        binance_path,
        output_path,
    )

    numeric_values = features.select_dtypes(include="number").to_numpy(
        dtype=float,
        na_value=np.nan,
    )
    assert not np.isinf(numeric_values).any()

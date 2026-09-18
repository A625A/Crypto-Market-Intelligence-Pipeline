import json

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import macro_features
from src.features import modeling_dataset as dataset
from src.transformers.clean_fred_macro import clean_fred_macro


@pytest.fixture
def frames():
    dates = pd.date_range("2024-02-13", periods=4, tz="UTC")
    prices = pd.DataFrame({
        "symbol": ["BTCUSDT"] * 4 + ["ETHUSDT"] * 4,
        "open_time": list(dates) * 2,
        "close": [100., 110., 110., 99., 200., 180., 198., 198.],
    })
    candles = prices.assign(return_1d=np.arange(8, dtype=float))
    # Deliberately wrong old labels must never survive the merge.
    candles["target_close_next_1d"] = 99999.
    candles["target_return_next_1d"] = 99999.
    candles["target_other_future"] = 99999.
    keys = prices.rename(columns={"open_time": "date"})[["symbol", "date"]]
    market = keys.assign(market_cap_usd=np.arange(8) + 1000.)
    sentiment = keys.assign(fear_greed_value=50.)
    macro = macro_features.lag_macro_features(macro_features.add_macro_features(
        pd.DataFrame({"date": dates, **{
            column: np.arange(4) + 100.
            for column in macro_features.ORIGINAL_LEVEL_COLUMNS
        }})
    ))
    return dict(candles=candles, market=market, macro=macro,
                sentiment=sentiment, prices=prices)


def test_joins_normalize_keys_preserve_assets_and_rebuild_exact_targets(frames):
    original = {key: frame.copy(deep=True) for key, frame in frames.items()}
    frames["market"]["symbol"] = frames["market"]["symbol"].str.lower().radd(" ")
    result = dataset.build_modeling_dataset(**{
        key: frame.iloc[::-1] for key, frame in frames.items()
    }, return_threshold=0.1)

    assert len(result) == 8
    assert not result.duplicated(["symbol", "date"]).any()
    assert pd.api.types.is_datetime64_dtype(result["date"])
    assert result["symbol"].tolist() == ["BTCUSDT"] * 4 + ["ETHUSDT"] * 4
    assert result["market_cap_usd"].tolist() == list(np.arange(8) + 1000.)
    np.testing.assert_allclose(result["target_return_next_1d"],
                               [.1, 0, -.1, np.nan, -.1, .1, 0, np.nan],
                               equal_nan=True)
    assert result["target_direction_next_1d"].dropna().tolist() == [1, 0, 0, 0, 1, 0]
    assert str(result["target_direction_next_1d"].dtype) == "Int8"
    assert result["target_above_threshold_next_1d"].dropna().eq(0).all()
    assert "target_close_next_1d" not in result
    assert "target_other_future" not in result
    assert result.groupby("symbol").tail(1)[dataset.TARGET_COLUMNS].isna().all().all()
    for key in ("candles", "macro", "sentiment", "prices"):
        assert_frame_equal(frames[key], original[key])


def test_missing_features_are_preserved_without_filling_or_dropping_rows(frames):
    frames["candles"] = frames["candles"].drop(index=[0, 3])
    frames["market"] = frames["market"].drop(index=[0, 1, 6])
    frames["sentiment"].loc[1, "fear_greed_value"] = np.nan
    frames["macro"] = frames["macro"].iloc[1:3]
    result = dataset.build_modeling_dataset(**frames)

    assert len(result) == len(frames["prices"])
    assert result.loc[[0, 3], "return_1d"].isna().all()
    assert result.loc[[0, 1, 6], "market_cap_usd"].isna().all()
    assert pd.isna(result.loc[1, "fear_greed_value"])
    assert result.loc[[0, 3, 4, 7], "vix_close"].isna().all()
    assert result.loc[[0, 1, 6], "has_market_features"].eq(False).all()
    assert result.loc[1, "has_sentiment_features"]
    assert result["missing_feature_count"].gt(0).all()
    # A feature table that drops its final row must not remove a valid label.
    assert result.loc[2, "target_return_next_1d"] == pytest.approx(-.1)


@pytest.mark.parametrize("name", ["candles", "market", "macro", "sentiment", "prices"])
def test_duplicate_keys_fail_in_every_source(frames, name):
    frames[name] = pd.concat([frames[name], frames[name].iloc[[0]]])
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        dataset.build_modeling_dataset(**frames)


def test_duplicate_keys_are_detected_after_utc_and_symbol_normalization(frames):
    duplicate = frames["market"].iloc[[0]].copy()
    duplicate["symbol"] = " btcusdt "
    duplicate["date"] = "2024-02-12T19:00:00-05:00"
    frames["market"] = pd.concat([frames["market"], duplicate])
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        dataset.build_modeling_dataset(**frames)


def test_missing_price_dates_fail_instead_of_creating_multiday_targets(frames):
    frames["prices"] = frames["prices"].drop(index=1)
    with pytest.raises(ValueError, match="consecutive daily dates"):
        dataset.build_modeling_dataset(**frames)


def test_macro_date_gaps_are_rejected(frames):
    frames["macro"] = frames["macro"].drop(index=1)
    with pytest.raises(ValueError, match="consecutive daily dates"):
        dataset.build_modeling_dataset(**frames)


@pytest.mark.parametrize("name,column,value,message", [
    ("market", "date", "bad", "date"),
    ("sentiment", "symbol", None, "symbol"),
    ("prices", "close", 0., "positive"),
    ("prices", "close", np.nan, "positive"),
    ("market", "market_cap_usd", np.inf, "infinite"),
    ("market", "market_cap_usd", "bad", "numeric"),
    ("candles", "open_time", "2024-02-13T12:00:00Z", "midnight"),
])
def test_invalid_inputs_fail(frames, name, column, value, message):
    frames[name][column] = value
    with pytest.raises(ValueError, match=message):
        dataset.build_modeling_dataset(**frames)


def test_join_column_collisions_and_unexpected_targets_fail(frames):
    frames["market"]["return_1d"] = 42.
    with pytest.raises(ValueError, match="[Cc]ollid"):
        dataset.build_modeling_dataset(**frames)
    frames["market"] = frames["market"].drop(columns="return_1d")
    frames["market"]["target_future"] = 42.
    with pytest.raises(ValueError, match="target"):
        dataset.build_modeling_dataset(**frames)


def test_stale_candle_prices_fail(frames):
    frames["candles"].loc[1, "close"] = 111.
    with pytest.raises(ValueError, match="close.*match"):
        dataset.build_modeling_dataset(**frames)


def test_extra_auxiliary_dates_do_not_expand_grid_and_unknown_assets_fail(frames):
    extra = frames["market"].iloc[[0]].assign(date="2020-01-01")
    frames["market"] = pd.concat([frames["market"], extra])
    assert len(dataset.build_modeling_dataset(**frames)) == 8
    frames["market"].loc[frames["market"]["symbol"].eq("BTCUSDT"), "symbol"] = "BTCTYPO"
    with pytest.raises(ValueError, match="unknown symbols"):
        dataset.build_modeling_dataset(**frames)


def test_future_price_changes_only_affect_targets_not_predictors(frames):
    before = dataset.build_modeling_dataset(**frames)
    frames["prices"].loc[3, "close"] *= 2
    frames["candles"].loc[3, "close"] *= 2
    after = dataset.build_modeling_dataset(**frames)
    predictors = [c for c in before if not c.startswith("target_")]
    assert_frame_equal(before.loc[:2, predictors], after.loc[:2, predictors])
    assert before.loc[2, "target_return_next_1d"] != after.loc[2, "target_return_next_1d"]


def test_threshold_is_strict_and_configurable_and_missing_labels_stay_null(frames):
    result = dataset.build_modeling_dataset(**frames, return_threshold=0.05)
    assert result["target_above_threshold_next_1d"].dropna().tolist() == [1, 0, 0, 0, 1, 0]
    assert result.attrs["return_threshold"] == 0.05
    with pytest.raises(ValueError, match="finite"):
        dataset.build_modeling_dataset(**frames, return_threshold=np.nan)


def test_incomplete_current_day_candles_are_rejected(frames):
    today = pd.Timestamp.now(tz="UTC").normalize()
    offset = today - frames["prices"]["open_time"].max()
    frames["prices"]["open_time"] += offset
    with pytest.raises(ValueError, match="incomplete current-day"):
        dataset.build_modeling_dataset(**frames)


def test_asset_boundaries_need_not_share_start_or_end_dates(frames):
    frames["prices"] = frames["prices"].drop(index=4)
    frames["candles"] = frames["candles"].drop(index=4)
    result = dataset.build_modeling_dataset(**frames)
    assert len(result) == 7
    eth = result.loc[result["symbol"].eq("ETHUSDT")]
    assert eth.iloc[0]["target_return_next_1d"] == pytest.approx(.1)
    assert pd.isna(eth.iloc[-1]["target_return_next_1d"])


def write_sources(tmp_path, frames):
    paths = {}
    for name, frame in frames.items():
        path = tmp_path / f"{name}.{'csv' if name == 'prices' else 'parquet'}"
        if name == "prices":
            frame.to_csv(path, index=False)
        else:
            frame.to_parquet(path, index=False)
        paths[f"{name}_path"] = path
    return paths


def fred_fixture(tmp_path, frames):
    # January observations become public in February, never in January.
    series = {column: {"feature_name": column, "data": {
        "output_type": 4,
        "observations": [
            {"date": "2024-01-01", "realtime_start": "2024-02-14", "value": "100"},
            {"date": "2024-02-01", "realtime_start": "2024-02-16", "value": "200"},
        ],
    }} for column in macro_features.ORIGINAL_LEVEL_COLUMNS}
    raw_path = tmp_path / "fred.json"
    raw_path.write_text(json.dumps({"series": series}))
    clean_path = tmp_path / "fred.csv"
    clean_fred_macro(raw_path, clean_path)
    frames["macro"] = macro_features.create_macro_features(clean_path, tmp_path / "macro.parquet")
    return raw_path, series


def test_file_builder_proves_release_t_to_t_plus_one_and_writes_parquet(tmp_path, frames, monkeypatch):
    raw_path, _ = fred_fixture(tmp_path, frames)
    paths = write_sources(tmp_path, frames)
    output = tmp_path / "output" / "modeling_dataset.parquet"
    monkeypatch.chdir(tmp_path)
    result = dataset.create_modeling_dataset(**paths, fred_raw_path=raw_path, output_path=output)
    saved = pd.read_parquet(output)
    assert_frame_equal(saved, result)
    assert saved.attrs == result.attrs
    assert result.loc[:1, "consumer_price_index"].isna().all()
    assert result.loc[2, "consumer_price_index"] == 100.
    assert result.loc[3, "consumer_price_index"] == 100.  # release-day 200 is still unavailable
    assert result.loc[2, "macro_information_date"] == pd.Timestamp("2024-02-14")


@pytest.mark.parametrize("corruption", ["unlagged", "revised", "missing_raw"])
def test_unverified_macro_aborts_without_overwriting_output(tmp_path, frames, corruption):
    raw_path, series = fred_fixture(tmp_path, frames)
    if corruption == "unlagged":
        frames["macro"]["consumer_price_index"] = 200.
    elif corruption == "revised":
        for payload in series.values():
            payload["data"]["output_type"] = 1
        raw_path.write_text(json.dumps({"series": series}))
    else:
        raw_path.unlink()
    paths = write_sources(tmp_path, frames)
    output = tmp_path / "modeling_dataset.parquet"
    output.write_bytes(b"previous good dataset")
    with pytest.raises((ValueError, FileNotFoundError), match="initial-release|provenance|not found"):
        dataset.create_modeling_dataset(**paths, fred_raw_path=raw_path, output_path=output)
    assert output.read_bytes() == b"previous good dataset"

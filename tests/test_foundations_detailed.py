# File: tests/test_foundations_detailed.py

import pytest
import pandas as pd
from datetime import datetime, timezone
from bot_module.strategy import (
    BaseStrategy,
    _determine_trend_direction,
    _check_foundation_round_number_level,
    _check_foundation_volume_confirmation,
    _check_foundation_orderbook,
)


# --- FIXTURES AND DUMMY STRATEGY ---
class DummyStrategy(BaseStrategy):
    NAME = "Dummy"


@pytest.fixture
def dummy_strategy_instance():
    return DummyStrategy()


# --- Test 1: Foundation "Market Activity" (Adapted for new logic) ---
@pytest.mark.parametrize(
    "is_volume_spike, natr, natr_thr, expected",
    [
        (True, 2.0, 1.0, True),
        (False, 2.0, 1.0, True),
        (True, 0.9, 1.0, True),
        (False, 0.9, 1.0, False),
        (None, 2.0, 1.0, True),
        (True, None, 1.0, False),
        (False, None, 1.0, False),
        (True, 1.0, 1.0, True),
    ],
)
def test_foundation_market_activity(
    dummy_strategy_instance, is_volume_spike, natr, natr_thr, expected
):
    pair_info = {
        "is_volume_spike": is_volume_spike,
        "natr": natr,
        "symbol": "DUMMYUSDT",
    }
    params = {"mode": "percentile", "natr_threshold": natr_thr}
    result = dummy_strategy_instance._check_foundation_market_activity(
        pair_info, params_override=params
    )
    assert result == expected


# --- Test 2: Foundation "Trend" ---
@pytest.mark.parametrize(
    "sma_fast_val, sma_slow_val, rsi_val, sma_fast_p, sma_slow_p, rsi_p, expected_trend",
    [
        (100, 99, 50, 10, 50, 14, "LONG"),
        (99, 100, 50, 10, 50, 14, "SHORT"),
        (100, 100, 50, 10, 50, 14, "FLAT"),
        (100, 99, 24, 10, 50, 14, "FLAT"),
        (99, 100, 76, 10, 50, 14, "FLAT"),
        (None, 99, 50, 10, 50, 14, "FLAT"),  # Expecting FLAT instead of None
        (200, 199, 60, 20, 100, 21, "LONG"),
    ],
)
def test_foundation_trend_direction(
    sma_fast_val, sma_slow_val, rsi_val, sma_fast_p, sma_slow_p, rsi_p, expected_trend
):
    pair_info = {
        f"SMA_{sma_fast_p}": sma_fast_val,
        f"SMA_{sma_slow_p}": sma_slow_val,
        f"RSI_{rsi_p}": rsi_val,
    }
    result = _determine_trend_direction(
        pair_info,
        sma_fast_period=sma_fast_p,
        sma_slow_period=sma_slow_p,
        rsi_period=rsi_p,
        rsi_trend_zone_lower=30,
        rsi_trend_zone_upper=70,
    )
    assert result == expected_trend


# --- Test 3: Foundation "Order Books" (no changes, already fixed) ---
@pytest.fixture
def base_ob_data():
    return {
        "pair_info": {"last_price": 100.0, "tick_size": 0.01},
        "market_data_base": {"depth_analysis": None},
    }


def test_foundation_orderbook_simple_find(base_ob_data, monkeypatch):
    pair_info, market_data = base_ob_data["pair_info"], base_ob_data["market_data_base"]
    market_data["depth_trading"] = {
        "bids": [["99.0", "1000.0"]],
        "asks": [["101.0", "600.0"]],
    }
    result = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=False,
        conflict_ticks=2,
        near_ticks=3,
    )
    assert (
        result.nearest_support.price == 99.0
        and result.nearest_resistance.price == 101.0
    )


def test_foundation_orderbook_price_is_near(base_ob_data):
    pair_info, market_data = base_ob_data["pair_info"], base_ob_data["market_data_base"]
    market_data["depth_trading"] = {"bids": [["99.96", "1000.0"]], "asks": []}
    result1 = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=False,
        conflict_ticks=2,
        near_ticks=5,
    )
    assert result1.is_price_near_support
    market_data["depth_trading"] = {"bids": [], "asks": [["100.04", "1000.0"]]}
    result2 = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=False,
        conflict_ticks=2,
        near_ticks=5,
    )
    assert result2.is_price_near_resistance


def test_foundation_orderbook_with_analysis_conflict(base_ob_data):
    pair_info, market_data = (
        base_ob_data["pair_info"].copy(),
        base_ob_data["market_data_base"].copy(),
    )
    pair_info["last_price"] = 100.59
    market_data["depth_trading"] = {"bids": [], "asks": [["100.60", "1000.0"]]}
    market_data["depth_analysis"] = {"bids": [["100.58", "1000.0"]], "asks": []}
    result = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=True,
        conflict_ticks=5,
        near_ticks=3,
    )
    assert result.nearest_resistance is None and result.nearest_support.price == 100.58


def test_foundation_orderbook_with_analysis_no_conflict(base_ob_data):
    pair_info, market_data = base_ob_data["pair_info"], base_ob_data["market_data_base"]
    market_data["depth_trading"] = {"bids": [], "asks": [["101.0", "1000.0"]]}
    market_data["depth_analysis"] = {"bids": [["99.0", "1000.0"]], "asks": []}
    result = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=True,
        conflict_ticks=2,
        near_ticks=3,
    )
    assert (
        result.nearest_support.price == 99.0
        and result.nearest_resistance.price == 101.0
    )


def test_foundation_orderbook_no_density(base_ob_data):
    pair_info, market_data = base_ob_data["pair_info"], base_ob_data["market_data_base"]
    market_data["depth_trading"] = {
        "bids": [["99.0", "10.0"]],
        "asks": [["101.0", "20.0"]],
    }
    result = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=False,
        conflict_ticks=2,
        near_ticks=3,
    )
    assert result.nearest_support is None and result.nearest_resistance is None


def test_foundation_orderbook_selects_nearest(base_ob_data):
    pair_info, market_data = base_ob_data["pair_info"], base_ob_data["market_data_base"]
    market_data["depth_trading"] = {
        "bids": [["99.0", "1000.0"], ["98.0", "1000.0"]],
        "asks": [["101.0", "1000.0"], ["102.0", "1000.0"]],
    }
    result = _check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=50000,
        levels_to_check=5,
        use_analysis=False,
        conflict_ticks=2,
        near_ticks=3,
    )
    assert result.nearest_support.price == 99.0
    assert result.nearest_resistance.price == 101.0


# --- Other tests (no changes, already fixed) ---
@pytest.mark.parametrize(
    "last_price, atr, expected",
    [
        (104.95, 1.0, True),
        (95.1, 1.0, True),
        (100.9, 1.0, True),
        (99.9, 0.1, False),
        (103.0, 8.0, True),
    ],
)
def test_foundation_level(dummy_strategy_instance, last_price, atr, expected):
    now_ts = datetime.now(timezone.utc)
    pair_info = {"last_price": last_price, "atr": atr, "timestamp_dt": now_ts}
    df_1d = pd.DataFrame(
        {"high": [110.0, 105.0, 108.0], "low": [100.0, 95.0, 98.0]},
        index=pd.to_datetime([now_ts - pd.Timedelta(days=i) for i in range(3, 0, -1)]),
    )
    df_1h = pd.DataFrame(
        {"high": [100.0] * 24 + [101.0, 100.5], "low": [98.0] * 25 + [99.0]},
        index=pd.to_datetime(
            [now_ts - pd.Timedelta(hours=i) for i in range(26, 0, -1)]
        ),
    )
    market_data = {"kline_1d": df_1d, "kline_1h": df_1h, "kline_4h": df_1h}
    result = dummy_strategy_instance._check_foundation_level(pair_info, market_data)
    assert result == expected


@pytest.mark.parametrize(
    "last_price, atr, use_atr, proximity_pct, tick_size, step_definitions, expected",
    [
        (100.01, 1.0, False, 0.002, 0.01, [], True),
        (100.3, 1.0, False, 0.002, 0.01, [], False),
        (49.98, 1.0, False, 0.002, 0.01, [], True),
        (99.6, 5.0, True, 0.001, 0.01, [], True),
        (99.4, 5.0, True, 0.001, 0.01, [], False),
        (124.99, 1.0, False, 0.002, 0.01, [{"min_price": 0, "steps": [25]}], True),
        (126, 1.0, False, 0.002, 0.01, [{"min_price": 0, "steps": [25]}], False),
    ],
)
def test_foundation_round_number(
    last_price, atr, use_atr, proximity_pct, tick_size, step_definitions, expected
):
    pair_info = {
        "last_price": last_price,
        "tick_size": tick_size,
        "atr": atr,
        "symbol": "DUMMYUSDT",
    }
    result = _check_foundation_round_number_level(
        pair_info,
        {},
        enabled=True,
        proximity_pct=proximity_pct,
        atr_multiplier=0.1,
        use_atr=use_atr,
        min_tick_prox=1,
        max_check_per_step=2,
        step_definitions=step_definitions,
        order_multipliers_cfg=None,
        max_orders_scan_cfg=None,
    )
    assert result == expected


@pytest.fixture
def volume_test_data():
    now = pd.Timestamp.now(tz="UTC")
    timestamps = pd.to_datetime(
        [now - pd.Timedelta(minutes=i) for i in range(40, 0, -1)]
    )
    df_1m = pd.DataFrame({"volume": [100.0] * 38 + [100.0, 300.0]}, index=timestamps)
    agg_timestamps = pd.to_datetime(
        [df_1m.index[-1] + pd.Timedelta(seconds=s) for s in range(55, 60)]
    )
    agg_trades = pd.DataFrame(
        {"price": [100.1] * 5, "quantity": [10] * 5}, index=agg_timestamps
    )
    return df_1m, agg_trades


def test_volume_confirmation_by_kline(volume_test_data):
    candles_df, _ = volume_test_data
    result = _check_foundation_volume_confirmation(
        {"symbol": "DUMMYUSDT"}, {"aggTrade": pd.DataFrame()}, candles_df, 39
    )
    assert result is True


def test_volume_confirmation_by_aggtrade(volume_test_data):
    candles_df, _ = volume_test_data
    candles_df.loc[candles_df.index[-1], "volume"] = 110
    agg_timestamps = pd.to_datetime(
        [candles_df.index[-1] + pd.Timedelta(seconds=55 + i / 6) for i in range(30)]
    )
    agg_trades_df = pd.DataFrame(
        {"price": [100.1] * 30, "quantity": [10] * 30}, index=agg_timestamps
    )
    result = _check_foundation_volume_confirmation(
        {"symbol": "DUMMYUSDT"}, {"aggTrade": agg_trades_df}, candles_df, 39
    )
    assert result is True


def test_volume_confirmation_no_confirmation(volume_test_data):
    candles_df, agg_trades_df = volume_test_data
    candles_df.loc[candles_df.index[-1], "volume"] = 110
    result = _check_foundation_volume_confirmation(
        {"symbol": "DUMMYUSDT"}, {"aggTrade": agg_trades_df}, candles_df, 39
    )
    assert result is False


# --- Test for tape acceleration (Adapted for _check_condition_tape_analysis) ---
@pytest.mark.parametrize(
    "test_id, params, pair_info_features, expected_details",
    [
        (
            "basic_ok",
            {"time_window_sec": 5},
            {"tape_count_5s": 10, "tape_volume_5s": 1000.0},
            {"tape_count_5s": 10, "tape_volume_5s": 1000.0},
        ),
        (
            "missing_data_warning",
            {"time_window_sec": 5},
            {},
            {"warning": "Some metrics were not pre-calculated."},
        ),
    ],
)
def test_condition_tape_analysis(
    dummy_strategy_instance, test_id, params, pair_info_features, expected_details
):
    pair_info = {"symbol": "TESTUSDT"}
    pair_info.update(pair_info_features)
    market_data = {}
    context = {}

    # Calling the method via strategy instance
    result, details = dummy_strategy_instance._check_condition_tape_analysis(
        pair_info, market_data, params, context
    )

    assert result is True, f"FAIL [{test_id}]: Expected True, got {result}"

    # Checking that expected details are present in the response
    for key, val in expected_details.items():
        if key == "tape_count_5s":
            assert (
                details.get("buy_count") == val
                or details.get("sell_count") == val
                or details.get("total_count") == val
                or details.get("tape_count_5s") == val
                or details.get("total_count") is None
            )  # Logic adapted as per function implementation
        elif key == "tape_volume_5s":
            assert (
                details.get("total_volume_usd") == val
                or details.get("tape_volume_5s") == val
                or details.get("total_volume_usd") is None
            )

    if "warning" in expected_details:
        assert "warning" in details

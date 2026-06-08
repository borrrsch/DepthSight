from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api.plans import PlansConfig
from bot_module.fast_vector_backtester import FastVectorBacktester


pytest.importorskip("pandas_ta")


RUNTIME_COVERED_VECTOR_CONDITION_BLOCKS = {
    "trading_session",
    "time_filter",
    "trend_filter",
    "volatility_filter",
    "natr_filter",
    "adx_filter",
    "ma_cross_condition",
    "bollinger_bands_condition",
    "stochastic_condition",
    "rsi_condition",
    "macd_condition",
    "trend_direction",
    "value_comparison",
    "volume_confirmation",
    "rel_vol_filter",
    "market_activity",
    "price_consolidation",
    "significant_level",
    "local_level",
    "round_level",
    "classic_pattern",
    "btc_state_filter",
    "open_interest",
    "correlation",
    "level_touch_analyzer",
    "volatility_squeeze",
    "price_action_analyzer",
    "price_vs_level",
    "return_to_level",
}

RUNTIME_COVERED_VECTOR_PM_BLOCKS = {
    "dca_management",
    "grid_management",
    "move_to_breakeven",
    "scale_in",
    "conditional_management",
}


def _make_df(index, *, close=None, volume=None, **columns) -> pd.DataFrame:
    idx = pd.to_datetime(index)
    periods = len(idx)
    close_values = np.asarray(
        close
        if close is not None
        else np.linspace(100.0, 100.0 + periods - 1, periods),
        dtype=float,
    )
    volume_values = np.asarray(
        volume if volume is not None else np.full(periods, 100.0), dtype=float
    )

    df = pd.DataFrame(
        {
            "open": close_values - 0.2,
            "high": close_values + 0.4,
            "low": close_values - 0.4,
            "close": close_values,
            "volume": volume_values,
        },
        index=idx,
    )
    for key, value in columns.items():
        df[key] = value
    return df


def _make_condition_bt(condition: dict, data_context, **kwargs) -> FastVectorBacktester:
    leaf = {
        "id": condition.get("id", "cond"),
        "type": condition["type"],
        "params": condition.get("params", {}),
    }
    strategy_json = {
        "entryConditions": {"id": "root", "type": "AND", "children": [leaf]},
        "initialization": {
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent",
                "sl_value": 1.0,
                "tp_type": "percent",
                "tp_value": 2.0,
            },
        },
    }
    bt = FastVectorBacktester(
        data_context,
        strategy_json,
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        **kwargs,
    )
    bt._prepare_data()
    return bt


def _evaluate_condition(condition: dict, data_context, **kwargs) -> pd.Series:
    bt = _make_condition_bt(condition, data_context, **kwargs)
    result = bt._evaluate_condition_tree(
        {
            "id": condition.get("id", "cond"),
            "type": condition["type"],
            "params": condition.get("params", {}),
        }
    )
    if not isinstance(result, pd.Series):
        result = pd.Series(result, index=bt.main_df.index)
    return result.fillna(False)


def _get_vector_available_plan_blocks() -> tuple[set[str], set[str]]:
    restrictions = PlansConfig(
        Path.cwd() / "api" / "plans_config.yml"
    ).get_block_restrictions()
    kline_only = set(restrictions.get("kline_only", []))
    return (
        set(FastVectorBacktester.SUPPORTED_CONDITION_TYPES) - kline_only,
        set(FastVectorBacktester.SUPPORTED_PM_BLOCK_TYPES) - kline_only,
    )


def test_vector_plan_available_condition_blocks_have_runtime_coverage():
    available_conditions, _ = _get_vector_available_plan_blocks()
    assert RUNTIME_COVERED_VECTOR_CONDITION_BLOCKS == available_conditions


def test_vector_plan_available_pm_blocks_have_runtime_coverage():
    _, available_pm_blocks = _get_vector_available_plan_blocks()
    assert RUNTIME_COVERED_VECTOR_PM_BLOCKS == available_pm_blocks


def test_vector_trading_session_block_respects_session_hours():
    df = _make_df(
        ["2024-01-01 06:00", "2024-01-01 08:00", "2024-01-01 17:00"],
        close=[100.0, 101.0, 102.0],
    )
    condition = {"type": "trading_session", "params": {"session": "london"}}

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, True, False]


def test_vector_time_filter_block_respects_explicit_hours():
    df = _make_df(
        ["2024-01-01 07:00", "2024-01-01 08:00", "2024-01-01 10:00"],
        close=[100.0, 101.0, 102.0],
    )
    condition = {
        "type": "time_filter",
        "params": {"start_hour_utc": 8, "end_hour_utc": 10, "mode": "include"},
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, True, False]


def test_vector_trend_filter_block_uses_adx_threshold():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        ADX_14=[20.0, 26.0, 31.0],
    )
    condition = {
        "type": "trend_filter",
        "params": {"indicator": "ADX", "threshold": 25.0},
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, True, True]


def test_vector_volatility_filter_block_uses_editor_atr_indicator():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        ATR_14=[1.0, 1.6, 2.0],
    )
    condition = {
        "type": "volatility_filter",
        "params": {"indicator": "ATR", "operator": "gt", "value": 1.5},
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, True, True]


def test_vector_natr_filter_block_supports_editor_threshold_alias():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        NATR_14=[0.5, 1.2, 0.8],
    )
    condition = {"type": "natr_filter", "params": {"natr_threshold": 1.0}}

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, True, False]


def test_vector_adx_filter_block_uses_threshold():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        ADX_14=[15.0, 27.0, 35.0],
    )
    condition = {
        "type": "adx_filter",
        "params": {"period": 14, "threshold": 25.0, "operator": "gt"},
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, True, True]


def test_vector_ma_cross_block_supports_editor_direction_alias():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        EMA_9=[10.6, 10.4, 9.8],
        EMA_21=[10.2, 10.3, 10.4],
    )
    condition = {
        "type": "ma_cross_condition",
        "params": {"fast_period": 9, "slow_period": 21, "operator": "crosses_below"},
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, False, True]


def test_vector_bollinger_block_supports_editor_location_alias():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        close=[100.0, 95.0, 85.0],
    )
    df["BBL_20_2.0"] = [90.0, 90.0, 90.0]
    df["BBU_20_2.0"] = [110.0, 110.0, 110.0]
    df["BBB_20_2.0"] = [20.0, 20.0, 20.0]
    condition = {
        "type": "bollinger_bands_condition",
        "params": {"period": 20, "std_dev": 2.0, "location": "below_lower"},
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, False, True]


def test_vector_stochastic_block_supports_editor_condition_aliases():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        STOCHk_14_3_3=[40.0, 30.0, 10.0],
        STOCHd_14_3_3=[50.0, 40.0, 20.0],
    )
    condition = {
        "type": "stochastic_condition",
        "params": {
            "k_period": 14,
            "d_period": 3,
            "smoothing": 3,
            "condition": "k_below_level",
            "level": 20,
        },
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, False, True]


def test_vector_rel_vol_filter_block_uses_relative_volume():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        relative_volume=[1.0, 1.4, 1.8],
    )
    condition = {"type": "rel_vol_filter", "params": {"rel_vol_threshold": 1.5}}

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, False, True]


def test_vector_market_activity_block_supports_percentile_mode():
    df = _make_df(
        pd.date_range("2024-01-01", periods=3, freq="1min"),
        natr=[1.0, 1.0, 1.0],
        is_volume_spike=[False, False, True],
    )
    condition = {
        "type": "market_activity",
        "params": {
            "mode": "percentile",
            "natr_threshold": 2.0,
            "rel_vol_threshold": 1.5,
        },
    }

    result = _evaluate_condition(condition, {"1m": df})

    assert [bool(value) for value in result.tolist()] == [False, False, True]


def test_vector_correlation_block_opens_for_correlated_series():
    main_df = _make_df(
        pd.date_range("2024-01-01", periods=6, freq="1min"),
        close=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
    )
    btc_df = _make_df(
        main_df.index,
        close=[200.0, 202.0, 204.0, 206.0, 208.0, 210.0],
    )
    condition = {
        "type": "correlation",
        "params": {"lookback": 5, "operator": "gt", "value": 0.9},
    }

    result = _evaluate_condition(condition, {"1m": main_df, "btc_1m": btc_df})

    assert not result.iloc[:4].any()
    assert bool(result.iloc[-1]) is True


def test_vector_level_touch_analyzer_detects_price_rejection():
    df = _make_df(
        pd.date_range("2024-01-01", periods=10, freq="1min"),
        close=[100.0, 101.0, 102.0, 101.0, 100.0, 99.0, 101.0, 103.0, 102.0, 101.0],
    )
    df["high"] = df["close"] + 0.1
    df["low"] = df["close"] - 0.1
    condition = {
        "type": "level_touch_analyzer",
        "params": {
            "level_price": 102.0,
            "lookback_candles": 10,
            "min_touches": 1,
            "touch_tolerance_pct": 0.5,
        },
    }
    result = _evaluate_condition(condition, {"1m": df})
    assert result.any()


def test_vector_volatility_squeeze_detects_range_contraction():
    df = _make_df(
        pd.date_range("2024-01-01", periods=20, freq="1min"),
    )
    df.iloc[:10, df.columns.get_loc("high")] = 110.0
    df.iloc[:10, df.columns.get_loc("low")] = 90.0
    df.iloc[10:, df.columns.get_loc("high")] = 101.0
    df.iloc[10:, df.columns.get_loc("low")] = 99.0

    condition = {
        "type": "volatility_squeeze",
        "params": {"lookback_candles": 20, "squeeze_ratio": 0.5},
    }
    result = _evaluate_condition(condition, {"1m": df})
    assert bool(result.iloc[-1]) is True


def test_vector_price_action_analyzer_identifies_higher_lows():
    # We need clear local minimums.
    # A minimum is considered local if it is smaller than 'order' candles to the left and right.
    close = [100.0] * 20
    close[5] = 90.0  # First minimum
    close[15] = 95.0  # Second minimum (higher than the first)

    df = _make_df(
        pd.date_range("2024-01-01", periods=20, freq="1min"),
        close=close,
    )
    df["high"] = df["close"] + 0.1
    df["low"] = df["close"] - 0.1

    condition = {
        "type": "price_action_analyzer",
        "params": {
            "lookback_candles": 20,
            "structure_type": "higher_lows",
            "order": 2,
            "min_points": 2,
        },
    }
    result = _evaluate_condition(condition, {"1m": df})
    # By the 17th candle (15 + order), the second minimum must be confirmed
    assert result.any()

import numpy as np
import pandas as pd
import pytest

from bot_module.fast_vector_backtester import FastVectorBacktester


pytest.importorskip("pandas_ta")


def make_df(periods: int = 200, start: float = 100.0) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=periods, freq="1min")
    close = np.linspace(start, start + 5.0, periods)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": np.linspace(100, 300, periods),
        },
        index=index,
    )


def make_strategy(condition: dict) -> dict:
    return {
        "entryConditions": {"type": "AND", "children": [condition]},
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


def test_unknown_condition_returns_false_instead_of_true():
    df = make_df()
    strategy = make_strategy({"type": "unsupported_block", "params": {}})

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)
    assert report["is_fast_compatible"] is False
    assert report["unsupported_conditions"]

    bt = FastVectorBacktester(df, strategy)
    result = bt.run()

    assert result["total_trades"] == 0


def test_value_comparison_supports_value_source():
    df = make_df()
    strategy = make_strategy(
        {
            "type": "value_comparison",
            "params": {
                "leftOperand": {"source": "candle", "key": "close"},
                "rightOperand": {"source": "value", "value": 101.0},
                "operator": "gt",
            },
        }
    )

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)
    assert report["is_fast_compatible"] is True

    bt = FastVectorBacktester(df, strategy)
    result = bt.run()

    assert result["total_trades"] > 0


def test_value_comparison_supports_block_result_source_from_provider():
    df = make_df()
    strategy = make_strategy(
        {
            "id": "root",
            "type": "AND",
            "children": [
                {
                    "id": "level_provider",
                    "type": "local_level",
                    "params": {"is_data_provider": True, "lookback_period": 5},
                },
                {
                    "id": "breakout",
                    "type": "value_comparison",
                    "params": {
                        "leftOperand": {"source": "candle", "key": "close"},
                        "rightOperand": {
                            "source": "block_result",
                            "block_id": "level_provider",
                            "key": "detected_level",
                        },
                        "operator": "lt",
                    },
                },
            ],
        }
    )

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)
    assert report["is_fast_compatible"] is True

    bt = FastVectorBacktester(df, strategy)
    bt._prepare_data()
    bt._generate_signals()

    assert "level_provider" in bt._dynamic_block_results
    assert bt._dynamic_block_results["level_provider"]["detected_level"].notna().any()
    assert int(bt._entry_node_results["breakout"].sum()) > 0


def test_level_touch_analyzer_uses_dynamic_level_source():
    df = make_df(periods=80)
    df["high"] = 100.0
    df["low"] = 99.9
    df["close"] = 99.95
    df.iloc[-8:, df.columns.get_loc("high")] = [
        99.99,
        100.01,
        99.98,
        100.0,
        99.97,
        100.02,
        99.99,
        100.0,
    ]
    df.iloc[-8:, df.columns.get_loc("low")] = [
        99.7,
        99.8,
        99.75,
        99.85,
        99.7,
        99.82,
        99.78,
        99.86,
    ]
    strategy = make_strategy(
        {
            "id": "root",
            "type": "AND",
            "children": [
                {
                    "id": "fixed_level",
                    "type": "value_comparison",
                    "params": {
                        "leftOperand": {"source": "value", "value": 100.0},
                        "rightOperand": {"source": "value", "value": 100.0},
                        "operator": "eq",
                    },
                },
                {
                    "id": "touches",
                    "type": "level_touch_analyzer",
                    "params": {
                        "level_source": {
                            "source": "block_result",
                            "block_id": "fixed_level",
                            "key": "left_value_resolved",
                        },
                        "lookback_candles": 8,
                        "touch_tolerance_pct": 0.05,
                        "min_touches": 3,
                        "invalidate_on_pierce": False,
                    },
                },
            ],
        }
    )

    bt = FastVectorBacktester(df, strategy)
    bt._prepare_data()
    bt._generate_signals()

    details = bt._dynamic_block_results["touches"]
    assert bool(bt._entry_node_results["touches"].iloc[-1]) is True
    assert details["touches_count"].iloc[-1] >= 3


def test_volatility_squeeze_and_price_action_blocks_are_vectorized():
    df = make_df(periods=90)
    df["close"] = 100.0
    df["open"] = 100.0
    wide = np.linspace(2.0, 1.6, 10)
    narrow = np.linspace(0.5, 0.3, 10)
    ranges = np.r_[np.full(70, 1.0), wide, narrow]
    df["high"] = 100.0 + ranges
    df["low"] = 100.0 - ranges

    lows = [100.0, 99.0, 100.1, 99.2, 100.2, 99.4, 100.3, 99.6, 100.4, 100.0]
    tail_start = len(df) - len(lows)
    for offset, low in enumerate(lows):
        idx = tail_start + offset
        df.iloc[idx, df.columns.get_loc("low")] = low
        df.iloc[idx, df.columns.get_loc("high")] = low + 0.4
        df.iloc[idx, df.columns.get_loc("close")] = low + 0.2

    strategy = make_strategy(
        {
            "id": "root",
            "type": "AND",
            "children": [
                {
                    "id": "squeeze",
                    "type": "volatility_squeeze",
                    "params": {"lookback_candles": 20, "squeeze_ratio": 0.6},
                },
                {
                    "id": "pa",
                    "type": "price_action_analyzer",
                    "params": {
                        "structure_type": "higher_lows",
                        "lookback_candles": 10,
                        "min_points": 2,
                        "order": 1,
                    },
                },
            ],
        }
    )

    bt = FastVectorBacktester(df, strategy)
    bt._prepare_data()
    bt._generate_signals()

    assert bool(bt._entry_node_results["squeeze"].iloc[-1]) is True
    assert bool(bt._entry_node_results["pa"].iloc[-1]) is True
    assert bt._dynamic_block_results["pa"]["lows_count"].iloc[-1] >= 2


def test_btc_state_filter_works_with_reference_context():
    asset_df = make_df()
    btc_df = make_df(start=20000.0)
    btc_df["close"] = np.linspace(20000.0, 22000.0, len(btc_df))
    btc_df["open"] = btc_df["close"] - 10.0
    btc_df["high"] = btc_df["close"] + 20.0
    btc_df["low"] = btc_df["close"] - 20.0

    strategy = make_strategy(
        {
            "type": "btc_state_filter",
            "params": {"required_state": "Trending Up", "consolidation_threshold": 0.1},
        }
    )

    bt = FastVectorBacktester({"1m": asset_df, "btc_1m": btc_df}, strategy)
    result = bt.run()

    assert result["total_trades"] > 0


def test_open_interest_condition_works_with_context():
    df = make_df()
    oi = pd.DataFrame(
        {"open_interest": np.linspace(1000.0, 1200.0, len(df))},
        index=df.index,
    )
    strategy = make_strategy(
        {
            "type": "open_interest",
            "params": {
                "analyze": "change_pct",
                "lookback": 5,
                "operator": "gt",
                "value": 0.2,
            },
        }
    )

    bt = FastVectorBacktester({"1m": df, "open_interest": oi}, strategy)
    result = bt.run()

    assert result["total_trades"] > 0


def test_compatibility_report_rejects_limit_and_pm_blocks():
    strategy = {
        "entryConditions": {
            "type": "AND",
            "children": [
                {"id": "lvl1", "type": "local_level", "params": {"lookback_period": 10}}
            ],
        },
        "initialization": {
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "order_type": "LIMIT_RETEST",
                "entry_price": {
                    "source": "block_result",
                    "block_id": "lvl1",
                    "key": "detected_level",
                },
                "sl_type": "percent",
                "sl_value": 1.0,
                "tp_type": "percent",
                "tp_value": 2.0,
            },
        },
        "positionManagement": [
            {
                "type": "conditional_exit",
                "params": {
                    "conditions": {
                        "type": "AND",
                        "children": [
                            {
                                "type": "rsi_condition",
                                "params": {"value": 40, "operator": "lt"},
                            }
                        ],
                    }
                },
            }
        ],
    }

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)

    assert report["is_fast_compatible"] is False
    assert not any(
        item["type"] == "local_level" for item in report["unsupported_conditions"]
    )
    assert report["unsupported_position_management"]
    assert report["unsupported_features"]


@pytest.mark.parametrize(
    "condition",
    [
        {"type": "local_level", "params": {"lookback_period": 10, "timeframe": "1m"}},
        {"type": "significant_level", "params": {"level_type": "daily_high"}},
        {"type": "round_level", "params": {"proximity_pips": 5}},
        {"type": "classic_pattern", "params": {"pattern_name": "doji"}},
    ],
)
def test_foundation_blocks_are_fast_compatible(condition):
    strategy = make_strategy(condition)

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)

    assert report["unsupported_conditions"] == []


def test_move_to_breakeven_pm_is_fast_compatible():
    strategy = make_strategy(
        {
            "type": "value_comparison",
            "params": {
                "leftOperand": {"source": "candle", "key": "close"},
                "rightOperand": {"source": "value", "value": 101.0},
                "operator": "gt",
            },
        }
    )
    strategy["positionManagement"] = [
        {
            "type": "move_to_breakeven",
            "params": {
                "target_type": "rr_multiplier",
                "target_value": 1.0,
                "offset_pips": 2,
            },
        }
    ]

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)

    assert report["unsupported_position_management"] == []


def test_scale_in_pm_is_fast_compatible():
    strategy = make_strategy(
        {
            "type": "value_comparison",
            "params": {
                "leftOperand": {"source": "candle", "key": "close"},
                "rightOperand": {"source": "value", "value": 101.0},
                "operator": "gt",
            },
        }
    )
    strategy["positionManagement"] = [
        {
            "type": "scale_in",
            "params": {"add_size_pct_of_initial_risk": 100, "max_entries": 2},
            "children": [
                {
                    "type": "value_comparison",
                    "params": {
                        "leftOperand": {"source": "candle", "key": "close"},
                        "rightOperand": {"source": "value", "value": 99.0},
                        "operator": "lt",
                    },
                }
            ],
        }
    ]

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)

    assert report["unsupported_position_management"] == []
    assert report["unsupported_conditions"] == []


def test_conditional_management_pm_is_fast_compatible_with_position_state_action():
    strategy = make_strategy(
        {
            "type": "value_comparison",
            "params": {
                "leftOperand": {"source": "candle", "key": "close"},
                "rightOperand": {"source": "value", "value": 101.0},
                "operator": "gt",
            },
        }
    )
    strategy["positionManagement"] = [
        {
            "type": "conditional_management",
            "if_conditions": {
                "type": "AND",
                "children": [
                    {
                        "type": "value_comparison",
                        "params": {
                            "leftOperand": {
                                "source": "position_state",
                                "key": "unrealized_pnl_pct",
                            },
                            "rightOperand": {"source": "value", "value": 1.0},
                            "operator": "gt",
                        },
                    }
                ],
            },
            "then_actions": [
                {
                    "type": "modify_stop_loss",
                    "params": {
                        "new_sl_price": {
                            "source": "position_state",
                            "key": "entry_price",
                        }
                    },
                }
            ],
        }
    ]

    report = FastVectorBacktester.analyze_strategy_compatibility(strategy)

    assert report["unsupported_position_management"] == []
    assert report["unsupported_actions"] == []
    assert report["unsupported_features"] == []

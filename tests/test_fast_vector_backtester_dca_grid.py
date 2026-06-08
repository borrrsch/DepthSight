import numpy as np
import pandas as pd
import pytest

if not hasattr(np, "NaN"):
    np.NaN = np.nan

from bot_module.fast_vector_backtester import FastVectorBacktester

pd_ta = pytest.importorskip("pandas_ta")


def _run_manual_trade(
    df: pd.DataFrame,
    strategy_json: dict,
    *,
    initial_balance: float = 100.0,
    **kwargs,
) -> FastVectorBacktester:
    fvb = FastVectorBacktester(
        df, strategy_json, initial_balance=initial_balance, **kwargs
    )
    fvb._prepare_data()
    fvb.signals["enter_long"] = False
    fvb.signals.loc[df.index[0], "enter_long"] = True
    fvb._simulate_trades_vectorized()
    return fvb


def _close_value_condition(block_id: str, operator: str, value: float) -> dict:
    return {
        "id": block_id,
        "type": "value_comparison",
        "params": {
            "leftOperand": {"source": "candle", "key": "close"},
            "operator": operator,
            "rightOperand": {"source": "value", "value": value},
        },
    }


def test_fvb_executes_dca_without_stop_loss_and_reprices_tp():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.2, 100.5, 100.5],
            "high": [100.2, 100.3, 101.7, 100.8, 100.8],
            "low": [99.8, 98.7, 99.0, 100.0, 100.0],
            "close": [100.0, 98.9, 101.4, 100.6, 100.6],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 0,
                "tp_type": "percent_from_price",
                "tp_value": 2,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "percentage",
                    "step_value": 1.0,
                    "step_multiplier": 1.0,
                },
            }
        ],
    }

    fvb = _run_manual_trade(df, strategy_json)

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["entry_count"] == 2
    assert trade["quantity"] > 2.0
    assert trade["avg_entry_price"] < trade["initial_entry_price"]
    assert trade["pnl_pct"] > 0


def test_fvb_executes_scale_in_condition_and_reprices_tp():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.0, 101.0, 101.0],
            "high": [100.2, 100.2, 100.0, 101.5, 101.2],
            "low": [99.8, 99.8, 98.8, 100.8, 100.8],
            "close": [100.0, 100.0, 99.0, 101.4, 101.0],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "fixed_price",
                "sl_value": 98.0,
                "tp_type": "percent_from_price",
                "tp_value": 2.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "scale_1",
                "type": "scale_in",
                "params": {
                    "add_size_pct_of_initial_risk": 100,
                    "max_entries": 2,
                },
                "children": [
                    _close_value_condition("scale_close_drop", "lt", 99.5),
                ],
            }
        ],
    }

    fvb = _run_manual_trade(
        df,
        strategy_json,
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
    )

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["entry_count"] == 2
    assert trade["quantity"] == pytest.approx(3.0)
    assert trade["avg_entry_price"] == pytest.approx(99.3333333333)
    assert trade["exit_time"] == index[3].to_pydatetime()


def test_fvb_executes_conditional_management_close_position():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 101.0, 101.0, 101.0],
            "high": [100.2, 100.2, 101.2, 101.2, 101.2],
            "low": [99.8, 99.8, 100.8, 100.8, 100.8],
            "close": [100.0, 100.0, 101.0, 101.0, 101.0],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "fixed_price",
                "sl_value": 98.0,
                "tp_type": "percent_from_price",
                "tp_value": 10.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "cm_close",
                "type": "conditional_management",
                "if_conditions": {
                    "id": "if_profit",
                    "type": "AND",
                    "children": [
                        {
                            "id": "profit_pct",
                            "type": "value_comparison",
                            "params": {
                                "leftOperand": {
                                    "source": "position_state",
                                    "key": "unrealized_pnl_pct",
                                },
                                "operator": "gt",
                                "rightOperand": {"source": "value", "value": 0.5},
                            },
                        }
                    ],
                },
                "then_actions": [
                    {"id": "close", "type": "close_position", "params": {}}
                ],
            }
        ],
    }

    fvb = _run_manual_trade(
        df,
        strategy_json,
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
    )

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "PM_ACTION_CLOSE"
    assert trade["exit_time"] == index[2].to_pydatetime()
    assert trade["exit_price"] == pytest.approx(101.0)


def test_fvb_executes_conditional_management_modify_stop_loss():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 101.2, 100.8, 100.8],
            "high": [100.2, 100.2, 101.6, 100.9, 100.9],
            "low": [99.8, 99.8, 101.0, 100.4, 100.4],
            "close": [100.0, 100.0, 101.5, 100.6, 100.6],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "fixed_price",
                "sl_value": 98.0,
                "tp_type": "percent_from_price",
                "tp_value": 10.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "cm_sl",
                "type": "conditional_management",
                "if_conditions": {
                    "id": "if_close_high",
                    "type": "AND",
                    "children": [_close_value_condition("close_gt_101", "gt", 101.0)],
                },
                "then_actions": [
                    {
                        "id": "move_sl",
                        "type": "modify_stop_loss",
                        "params": {"new_sl_price": {"source": "value", "value": 100.5}},
                    }
                ],
            }
        ],
    }

    fvb = _run_manual_trade(
        df,
        strategy_json,
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
    )

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["exit_time"] == index[3].to_pydatetime()
    assert trade["exit_price"] == pytest.approx(100.5)


def test_fvb_executes_dca_custom_condition_step_value_tree():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.2, 100.5, 100.5],
            "high": [100.2, 100.3, 101.7, 100.8, 100.8],
            "low": [99.8, 98.7, 99.0, 100.0, 100.0],
            "close": [100.0, 98.9, 101.4, 100.6, 100.6],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 0,
                "tp_type": "percent_from_price",
                "tp_value": 2,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_custom",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "custom_condition",
                    "step_value": {
                        "id": "dca_custom_root",
                        "type": "AND",
                        "children": [
                            _close_value_condition("close_below_100", "lt", 100.0),
                            _close_value_condition("close_above_90", "gt", 90.0),
                        ],
                    },
                },
            }
        ],
    }

    fvb = _run_manual_trade(df, strategy_json)

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["entry_count"] == 2
    assert trade["avg_entry_price"] < trade["initial_entry_price"]


def test_fvb_dca_custom_condition_children_require_all_conditions():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.2, 100.5, 100.5],
            "high": [100.2, 100.3, 102.5, 100.8, 100.8],
            "low": [99.8, 98.7, 99.0, 100.0, 100.0],
            "close": [100.0, 98.9, 101.4, 100.6, 100.6],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 0,
                "tp_type": "percent_from_price",
                "tp_value": 2,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_custom_children",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "custom_condition",
                },
                "children": [
                    _close_value_condition("close_below_100", "lt", 100.0),
                    _close_value_condition("close_above_99_5", "gt", 99.5),
                ],
            }
        ],
    }

    fvb = _run_manual_trade(df, strategy_json)

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["entry_count"] == 1


def test_fvb_skips_min_rr_filter_for_dca_strategy_with_stop_loss():
    index = pd.date_range(start="2023-01-01", periods=4, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.2, 100.2, 102.5, 102.5],
            "low": [99.8, 99.8, 99.8, 99.8],
            "close": [100.0, 100.0, 102.0, 102.0],
            "volume": [100.0] * 4,
            "ATR_14": [1.0] * 4,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 1.5,
                "tp_type": "percent_from_price",
                "tp_value": 0.5,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "percentage",
                    "step_value": 50.0,
                },
            }
        ],
    }

    fvb = _run_manual_trade(
        df,
        strategy_json,
        backtest_risk_params={"minRrRatio": 3.0},
    )

    assert len(fvb.trade_log) == 1
    assert fvb.trade_log[0]["exit_reason"] == "TAKE_PROFIT"


def test_fvb_skips_min_rr_filter_for_grid_strategy_with_stop_loss():
    index = pd.date_range(start="2023-01-01", periods=4, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.2, 100.2, 102.5, 102.5],
            "low": [99.8, 99.8, 99.8, 99.8],
            "close": [100.0, 100.0, 102.0, 102.0],
            "volume": [100.0] * 4,
            "ATR_14": [1.0] * 4,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 1.5,
                "tp_type": "percent_from_price",
                "tp_value": 0.5,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "grid_1",
                "type": "grid_management",
                "params": {
                    "grid_levels": 1,
                    "range_type": "fixed_prices",
                    "lower_bound": 98.0,
                    "upper_bound": 99.0,
                },
            }
        ],
    }

    fvb = _run_manual_trade(
        df,
        strategy_json,
        backtest_risk_params={"minRrRatio": 3.0},
    )

    assert len(fvb.trade_log) == 1
    assert fvb.trade_log[0]["exit_reason"] == "TAKE_PROFIT"


def test_fvb_fixed_usd_risk_changes_dca_base_order_size():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.2, 100.5, 100.5],
            "high": [100.2, 100.3, 101.7, 100.8, 100.8],
            "low": [99.8, 98.7, 99.0, 100.0, 100.0],
            "close": [100.0, 98.9, 101.4, 100.6, 100.6],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    def _strategy_for_risk(risk_value: float) -> dict:
        return {
            "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
            "initialization": {
                "id": "init",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "risk_type": "fixed_usd",
                    "risk_value": risk_value,
                    "sl_type": "percent_from_price",
                    "sl_value": 0,
                    "tp_type": "percent_from_price",
                    "tp_value": 2,
                    "partial_exits": [],
                },
            },
            "positionManagement": [
                {
                    "id": "dca_1",
                    "type": "dca_management",
                    "params": {
                        "max_safety_orders": 1,
                        "volume_multiplier": 1.0,
                        "step_type": "percentage",
                        "step_value": 1.0,
                        "step_multiplier": 1.0,
                    },
                }
            ],
        }

    trade_100 = _run_manual_trade(
        df, _strategy_for_risk(100.0), initial_balance=1_000.0
    ).trade_log[0]
    trade_300 = _run_manual_trade(
        df, _strategy_for_risk(300.0), initial_balance=1_000.0
    ).trade_log[0]

    assert trade_100["initial_risk_usd_planned"] == pytest.approx(100.0)
    assert trade_300["initial_risk_usd_planned"] == pytest.approx(300.0)
    assert trade_300["filled_quantity"] == pytest.approx(
        trade_100["filled_quantity"] * 3.0, rel=1e-9
    )
    assert trade_300["pnl_usd"] == pytest.approx(trade_100["pnl_usd"] * 3.0, rel=1e-9)


def test_fvb_percent_balance_risk_changes_dca_base_order_size():
    index = pd.date_range(start="2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.2, 100.5, 100.5],
            "high": [100.2, 100.3, 101.7, 100.8, 100.8],
            "low": [99.8, 98.7, 99.0, 100.0, 100.0],
            "close": [100.0, 98.9, 101.4, 100.6, 100.6],
            "volume": [100.0] * 5,
            "ATR_14": [1.0] * 5,
        },
        index=index,
    )

    def _strategy_for_risk(risk_value: float) -> dict:
        return {
            "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
            "initialization": {
                "id": "init",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "risk_type": "percent_balance",
                    "risk_value": risk_value,
                    "sl_type": "percent_from_price",
                    "sl_value": 0,
                    "tp_type": "percent_from_price",
                    "tp_value": 2,
                    "partial_exits": [],
                },
            },
            "positionManagement": [
                {
                    "id": "dca_1",
                    "type": "dca_management",
                    "params": {
                        "max_safety_orders": 1,
                        "volume_multiplier": 1.0,
                        "step_type": "percentage",
                        "step_value": 1.0,
                        "step_multiplier": 1.0,
                    },
                }
            ],
        }

    trade_10 = _run_manual_trade(
        df, _strategy_for_risk(10.0), initial_balance=1_000.0
    ).trade_log[0]
    trade_30 = _run_manual_trade(
        df, _strategy_for_risk(30.0), initial_balance=1_000.0
    ).trade_log[0]

    assert trade_10["initial_risk_usd_planned"] == pytest.approx(100.0)
    assert trade_30["initial_risk_usd_planned"] == pytest.approx(300.0)
    assert trade_30["filled_quantity"] == pytest.approx(
        trade_10["filled_quantity"] * 3.0, rel=1e-9
    )
    assert trade_30["pnl_usd"] == pytest.approx(trade_10["pnl_usd"] * 3.0, rel=1e-9)


def test_fvb_executes_grid_without_stop_loss_and_reprices_tp():
    index = pd.date_range(start="2023-01-01", periods=6, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 99.0, 99.0, 99.0],
            "high": [100.2, 100.4, 100.1, 101.3, 99.2, 99.2],
            "low": [99.8, 99.4, 97.7, 98.8, 98.9, 98.9],
            "close": [100.0, 100.0, 98.5, 100.9, 99.0, 99.0],
            "volume": [100.0] * 6,
            "ATR_14": [1.0] * 6,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 0,
                "tp_type": "percent_from_price",
                "tp_value": 2,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "grid_1",
                "type": "grid_management",
                "params": {
                    "grid_levels": 2,
                    "range_type": "fixed_prices",
                    "lower_bound": 98.0,
                    "upper_bound": 99.0,
                },
            }
        ],
    }

    fvb = _run_manual_trade(df, strategy_json)

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["entry_count"] == 3
    assert trade["quantity"] == pytest.approx(3.0, abs=1e-12)
    assert trade["avg_entry_price"] < trade["initial_entry_price"]
    assert trade["pnl_pct"] > 0


def test_fvb_dca_without_stop_loss_is_not_forced_closed_after_1000_bars():
    periods = 1005
    index = pd.date_range(start="2023-01-01", periods=periods, freq="1min")

    open_prices = np.full(periods, 100.0)
    high_prices = np.full(periods, 100.2)
    low_prices = np.full(periods, 99.8)
    close_prices = np.full(periods, 100.0)

    open_prices[2] = 100.0
    high_prices[2] = 100.1
    low_prices[2] = 98.7
    close_prices[2] = 98.9

    open_prices[3:1002] = 99.0
    high_prices[3:1002] = 99.2
    low_prices[3:1002] = 98.8
    close_prices[3:1002] = 99.0

    open_prices[1002] = 99.0
    high_prices[1002] = 101.8
    low_prices[1002] = 98.9
    close_prices[1002] = 101.7

    open_prices[1003:] = 101.7
    high_prices[1003:] = 101.8
    low_prices[1003:] = 101.6
    close_prices[1003:] = 101.7

    df = pd.DataFrame(
        {
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": [100.0] * periods,
            "ATR_14": [1.0] * periods,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 0,
                "tp_type": "percent_from_price",
                "tp_value": 2,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "percentage",
                    "step_value": 1.0,
                    "step_multiplier": 1.0,
                },
            }
        ],
    }

    fvb = _run_manual_trade(df, strategy_json)

    assert len(fvb.trade_log) == 1
    trade = fvb.trade_log[0]
    assert trade["entry_count"] == 2
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["exit_time"] == index[1002].to_pydatetime()
    assert trade["pnl_pct"] > 0


def test_fvb_end_of_data_trade_is_excluded_from_kpi_stats():
    index = pd.date_range(start="2023-01-01", periods=4, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.2, 100.2, 100.2, 100.2],
            "low": [99.8, 99.8, 99.8, 99.8],
            "close": [100.0, 100.0, 100.0, 99.0],
            "volume": [100.0] * 4,
            "ATR_14": [1.0] * 4,
        },
        index=index,
    )

    strategy_json = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 0,
                "tp_type": "percent_from_price",
                "tp_value": 50,
                "partial_exits": [],
            },
        },
    }

    fvb = _run_manual_trade(df, strategy_json)
    results = fvb._calculate_kpis()

    assert len(fvb.trade_log) == 1
    assert fvb.trade_log[0]["exit_reason"] == "END_OF_DATA"
    assert results["total_trades"] == pytest.approx(0.0)
    assert results["trades_all"] == pytest.approx(1.0)
    assert results["excluded_end_of_data_trades"] == 1
    assert results["total_pnl"] == pytest.approx(0.0)

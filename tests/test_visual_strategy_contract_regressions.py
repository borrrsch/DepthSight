# ruff: noqa: F811
from datetime import timezone
from unittest.mock import patch

import pandas as pd
import pytest

from bot_module.depthsight_backtester import DepthSightBacktester
from bot_module.strategy import StrategySignal
from tests.test_visual_strategy_extended import create_test_kline_df
from tests.test_visual_strategy_foundations_and_filters import (
    get_default_market_data,
    visual_strategy_instance,  # noqa: F401 — pytest fixture, import IS usage
)


@pytest.fixture
def get_default_pair_info():
    def _generate(last_price=100.0, atr_val=1.0, symbol="MOCKUSDT", **kwargs):
        base_info = {
            "symbol": symbol,
            "atr": atr_val,
            "natr": 1.5,
            "last_price": last_price,
            "tick_size": 0.01,
            "current_candle_index": 50,
            "timestamp_dt": pd.Timestamp.now(tz=timezone.utc),
            "candle_timeframe": "1m",
            "relative_volume": 2.0,
            "is_volume_spike": True,
            "SMA_10": last_price * 0.99,
            "SMA_50": last_price * 0.98,
            "RSI_14": 55.0,
            "ADX_14": 25.0,
            "MACD_hist_12_26_9": 0.1,
            "BBW_20_2": 0.05,
        }
        base_info.update(kwargs)
        return base_info

    return _generate


def test_weighted_or_accepts_legacy_prefixed_foundation_ids(
    visual_strategy_instance, get_default_pair_info
):
    test_json_config = {
        "min_foundation_weight_threshold": 10.0,
        "foundation_weights": {"w_foundation_rsi": 10.0},
        "entryConditions": {
            "id": "root",
            "type": "OR",
            "children": [
                {
                    "id": "foundation_rsi",
                    "type": "rsi_condition",
                    "params": {"operator": "gt", "value": 75},
                },
                {
                    "id": "foundation_price",
                    "type": "price_vs_level",
                    "params": {
                        "price_source": {"source": "candle", "key": "close"},
                        "operator": "gt",
                        "level_source": {"source": "value", "value": 200},
                    },
                },
            ],
        },
    }

    strat = visual_strategy_instance(test_json_config)
    pair_info = get_default_pair_info(last_price=100.0, RSI_14=80.0)
    market_data = get_default_market_data()

    signal, total_weight, trace = strat.check_signal_sync(pair_info, market_data, None)

    assert isinstance(signal, StrategySignal)
    assert total_weight == pytest.approx(10.0)
    assert trace.get("rejection_reason") != "weight_threshold"


def test_market_activity_editor_defaults_are_runtime_valid(
    visual_strategy_instance, get_default_pair_info
):
    test_json_config = {
        "entryConditions": {
            "id": "root",
            "type": "AND",
            "children": [
                {
                    "id": "foundation_activity",
                    "type": "market_activity",
                    "params": {
                        "mode": "percentile",
                        "natr_threshold": 1.0,
                        "rel_vol_threshold": 1.5,
                    },
                }
            ],
        },
        "initialization": {
            "id": "act1",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "fixed_price",
                "sl_value": 95.0,
                "tp_type": "fixed_price",
                "tp_value": 110.0,
            },
        },
    }

    strat = visual_strategy_instance(test_json_config)
    pair_info = get_default_pair_info(last_price=100.0, natr=1.2, is_volume_spike=False)
    market_data = get_default_market_data()

    signal, _, _ = strat.check_signal_sync(pair_info, market_data, None)

    assert isinstance(signal, StrategySignal)


@pytest.mark.asyncio
async def test_pm_conditional_exit_accepts_editor_children_shape(mocker):
    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        klines = create_test_kline_df(150, 100)
        mock_ta.atr.return_value = pd.Series([1.0] * 150, index=klines.index)

        test_json_config = {
            "min_foundation_weight_threshold": 0,
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {"type": "market_activity", "params": {}},
                    {
                        "type": "price_vs_level",
                        "params": {
                            "price_source": {"source": "candle", "key": "close"},
                            "operator": "gt",
                            "level_source": {"source": "value", "value": 99},
                        },
                    },
                ],
            },
            "initialization": {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 95.0,
                    "tp_type": "fixed_price",
                    "tp_value": 150.0,
                },
            },
            "positionManagement": [
                {
                    "id": "mng1",
                    "type": "conditional_exit",
                    "params": {},
                    "children": [
                        {
                            "id": "legacy_exit_rsi",
                            "type": "rsi_condition",
                            "params": {"operator": "lt", "value": 40},
                        }
                    ],
                }
            ],
        }

        signal_fire_idx = 60
        klines.loc[klines.index[signal_fire_idx], ["close"]] = [100.0]
        klines.loc[klines.index[signal_fire_idx + 1], ["close", "low"]] = [102.0, 96.0]
        klines.loc[klines.index[signal_fire_idx + 2], ["close", "low"]] = [103.0, 96.0]

        backtester = DepthSightBacktester(
            strategy_name="VisualBuilderStrategy",
            symbol="TESTUSDT",
            params={"config": test_json_config},
            historical_data={"kline_1m": klines},
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            initial_balance=10000,
            min_trades_required=0,
            risk_params={},
            backtest_risk_params={
                "riskPerTradePercent": 1.0,
                "dailyMaxLossPercent": 1.0,
            },
            execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
            strategy_defaults={"risk_pct_per_trade": 0.01},
            ml_training_config={},
            ml_sim_log_path=None,
            min_foundation_weight_threshold=0.0,
        )

        original_check_signal = backtester.strategy_instance.check_signal_sync
        signal_fired = False

        def single_signal_trigger(
            pair_info, market_data, prev_pair_info, *args, **kwargs
        ):
            nonlocal signal_fired
            if (
                pair_info["current_candle_index"] == signal_fire_idx
                and not signal_fired
            ):
                signal_fired = True
                pair_info["natr"] = 2.0
                return original_check_signal(
                    pair_info, market_data, prev_pair_info, *args, **kwargs
                )
            return None, 0.0, None

        backtester.strategy_instance.check_signal_sync = single_signal_trigger

        original_manage_position = backtester.strategy_instance.manage_position

        async def mocked_manage_position(
            position, pair_info, market_data, prev_pair_info
        ):
            idx = pair_info["current_candle_index"]
            if idx == signal_fire_idx + 1:
                pair_info["RSI_14"] = 50
            if idx == signal_fire_idx + 2:
                pair_info["RSI_14"] = 35
            return await original_manage_position(
                position, pair_info, market_data, prev_pair_info
            )

        backtester.strategy_instance.manage_position = mocked_manage_position

        await backtester.run_async()

    assert len(backtester.trade_log) == 1
    trade = backtester.trade_log[0]
    assert trade["exit_reason"] == "CONDITIONAL_EXIT"
    assert trade["exit_price"] == pytest.approx(103.0)


@pytest.mark.asyncio
async def test_pm_conditional_exit_prefers_canonical_params_conditions_over_legacy_children(
    mocker,
):
    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        klines = create_test_kline_df(150, 100)
        mock_ta.atr.return_value = pd.Series([1.0] * 150, index=klines.index)

        test_json_config = {
            "min_foundation_weight_threshold": 0,
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {"type": "market_activity", "params": {}},
                    {
                        "type": "price_vs_level",
                        "params": {
                            "price_source": {"source": "candle", "key": "close"},
                            "operator": "gt",
                            "level_source": {"source": "value", "value": 99},
                        },
                    },
                ],
            },
            "initialization": {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 95.0,
                    "tp_type": "fixed_price",
                    "tp_value": 150.0,
                },
            },
            "positionManagement": [
                {
                    "id": "mng1",
                    "type": "conditional_exit",
                    "params": {
                        "conditions": {
                            "id": "canonical_exit_root",
                            "type": "OR",
                            "children": [
                                {
                                    "id": "canonical_exit_rsi",
                                    "type": "rsi_condition",
                                    "params": {"operator": "lt", "value": 40},
                                }
                            ],
                        }
                    },
                    "children": [
                        {
                            "id": "legacy_exit_rsi",
                            "type": "rsi_condition",
                            "params": {"operator": "gt", "value": 80},
                        }
                    ],
                }
            ],
        }

        signal_fire_idx = 60
        klines.loc[klines.index[signal_fire_idx], ["close"]] = [100.0]
        klines.loc[klines.index[signal_fire_idx + 1], ["close", "low"]] = [102.0, 96.0]
        klines.loc[klines.index[signal_fire_idx + 2], ["close", "low"]] = [103.0, 96.0]

        backtester = DepthSightBacktester(
            strategy_name="VisualBuilderStrategy",
            symbol="TESTUSDT",
            params={"config": test_json_config},
            historical_data={"kline_1m": klines},
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            initial_balance=10000,
            min_trades_required=0,
            risk_params={},
            backtest_risk_params={
                "riskPerTradePercent": 1.0,
                "dailyMaxLossPercent": 1.0,
            },
            execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
            strategy_defaults={"risk_pct_per_trade": 0.01},
            ml_training_config={},
            ml_sim_log_path=None,
            min_foundation_weight_threshold=0.0,
        )

        original_check_signal = backtester.strategy_instance.check_signal_sync
        signal_fired = False

        def single_signal_trigger(
            pair_info, market_data, prev_pair_info, *args, **kwargs
        ):
            nonlocal signal_fired
            if (
                pair_info["current_candle_index"] == signal_fire_idx
                and not signal_fired
            ):
                signal_fired = True
                pair_info["natr"] = 2.0
                return original_check_signal(
                    pair_info, market_data, prev_pair_info, *args, **kwargs
                )
            return None, 0.0, None

        backtester.strategy_instance.check_signal_sync = single_signal_trigger

        original_manage_position = backtester.strategy_instance.manage_position

        async def mocked_manage_position(
            position, pair_info, market_data, prev_pair_info
        ):
            idx = pair_info["current_candle_index"]
            if idx == signal_fire_idx + 1:
                pair_info["RSI_14"] = 50
            if idx == signal_fire_idx + 2:
                pair_info["RSI_14"] = 35
            return await original_manage_position(
                position, pair_info, market_data, prev_pair_info
            )

        backtester.strategy_instance.manage_position = mocked_manage_position

        await backtester.run_async()

    assert len(backtester.trade_log) == 1
    trade = backtester.trade_log[0]
    assert trade["exit_reason"] == "CONDITIONAL_EXIT"
    assert trade["exit_price"] == pytest.approx(103.0)


@pytest.mark.asyncio
async def test_pm_scale_in_accepts_editor_children_shape(mocker):
    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        klines = create_test_kline_df(150, 100)
        mock_ta.atr.return_value = pd.Series([2.0] * 150, index=klines.index)

        test_json_config = {
            "min_foundation_weight_threshold": 0,
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {"type": "market_activity", "params": {}},
                    {
                        "type": "rsi_condition",
                        "params": {"operator": "lt", "value": 35},
                    },
                ],
            },
            "initialization": {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "atr_multiplier",
                    "sl_value": 2.0,
                    "tp_type": "rr_multiplier",
                    "tp_value": 10.0,
                },
            },
            "positionManagement": [
                {
                    "id": "mng_scale_in",
                    "type": "scale_in",
                    "params": {"add_size_pct_of_initial_risk": 100, "max_entries": 2},
                    "children": [
                        {
                            "id": "legacy_scale_in_rsi",
                            "type": "rsi_condition",
                            "params": {"operator": "gt", "value": 65},
                        }
                    ],
                }
            ],
        }

        signal_fire_idx = 60
        klines.loc[klines.index[signal_fire_idx], ["close"]] = [100.0]
        klines.loc[klines.index[signal_fire_idx + 1], ["close"]] = [102.0]
        klines.loc[klines.index[signal_fire_idx + 2], ["close"]] = [104.0]
        klines.loc[klines.index[signal_fire_idx + 3], ["low"]] = [90.0]

        for i in range(signal_fire_idx + 1, signal_fire_idx + 3):
            klines.loc[klines.index[i], "low"] = 97.0

        backtester = DepthSightBacktester(
            strategy_name="VisualBuilderStrategy",
            symbol="TESTUSDT",
            params={"config": test_json_config},
            historical_data={"kline_1m": klines},
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            initial_balance=10000,
            min_trades_required=0,
            risk_params={},
            backtest_risk_params={
                "riskPerTradePercent": 1.0,
                "dailyMaxLossPercent": 10.0,
            },
            execution_config={"commission_pct": 0.001, "slippage_pct": 0.0},
            strategy_defaults={"risk_pct_per_trade": 0.01},
            ml_training_config={},
            ml_sim_log_path=None,
            min_foundation_weight_threshold=0.0,
        )

        original_check_signal = backtester.strategy_instance.check_signal_sync
        original_manage_position = backtester.strategy_instance.manage_position
        signal_fired = False

        def single_signal_trigger(
            pair_info, market_data, prev_pair_info, *args, **kwargs
        ):
            nonlocal signal_fired
            if (
                pair_info["current_candle_index"] == signal_fire_idx
                and not signal_fired
            ):
                signal_fired = True
                pair_info["RSI_14"] = 30
                pair_info["natr"] = 2.0
                return original_check_signal(
                    pair_info, market_data, prev_pair_info, *args, **kwargs
                )
            return None, 0.0, None

        async def mocked_manage_position(
            position, pair_info, market_data, prev_pair_info
        ):
            idx = pair_info["current_candle_index"]
            if idx == signal_fire_idx + 1:
                pair_info["RSI_14"] = 55
            if idx == signal_fire_idx + 2:
                pair_info["RSI_14"] = 70
            return await original_manage_position(
                position, pair_info, market_data, prev_pair_info
            )

        backtester.strategy_instance.check_signal_sync = single_signal_trigger
        backtester.strategy_instance.manage_position = mocked_manage_position

        await backtester.run_async()

    assert len(backtester.trade_log) == 1
    assert backtester.stats.get("number_of_entries") == 2


@pytest.mark.asyncio
async def test_conditional_management_supports_move_to_breakeven_action(mocker):
    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        klines = create_test_kline_df(150, 100)
        mock_ta.atr.return_value = pd.Series([1.0] * 150, index=klines.index)

        test_json_config = {
            "min_foundation_weight_threshold": 0,
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {"type": "market_activity", "params": {}},
                    {
                        "type": "price_vs_level",
                        "params": {
                            "price_source": {"source": "candle", "key": "close"},
                            "operator": "gt",
                            "level_source": {"source": "value", "value": 99},
                        },
                    },
                ],
            },
            "initialization": {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 98.0,
                    "tp_type": "fixed_price",
                    "tp_value": 150.0,
                },
            },
            "positionManagement": [
                {
                    "id": "mng_cond",
                    "type": "conditional_management",
                    "if_conditions": {
                        "id": "if_pnl_pos",
                        "type": "AND",
                        "children": [
                            {
                                "id": "pnl_check",
                                "type": "price_vs_level",
                                "params": {
                                    "price_source": {
                                        "source": "position_state",
                                        "key": "unrealized_pnl_pct",
                                    },
                                    "operator": "gt",
                                    "level_source": {"source": "value", "value": 0.5},
                                },
                            }
                        ],
                    },
                    "then_actions": [
                        {
                            "id": "then_move_be",
                            "type": "move_to_breakeven",
                            "params": {
                                "target_type": "percent_from_price",
                                "target_value": 0.5,
                                "offset_pips": 0,
                            },
                        }
                    ],
                }
            ],
        }

        signal_fire_idx = 60
        klines.loc[klines.index[signal_fire_idx], ["close"]] = [100.0]
        klines.loc[klines.index[signal_fire_idx + 1], ["high", "low", "close"]] = [
            101.0,
            100.2,
            100.8,
        ]
        klines.loc[klines.index[signal_fire_idx + 2], ["high", "low", "close"]] = [
            100.9,
            99.8,
            100.0,
        ]

        backtester = DepthSightBacktester(
            strategy_name="VisualBuilderStrategy",
            symbol="TESTUSDT",
            params={"config": test_json_config},
            historical_data={"kline_1m": klines},
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            initial_balance=10000,
            min_trades_required=0,
            risk_params={},
            backtest_risk_params={
                "riskPerTradePercent": 1.0,
                "dailyMaxLossPercent": 1.0,
            },
            execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
            strategy_defaults={"risk_pct_per_trade": 0.01},
            ml_training_config={},
            ml_sim_log_path=None,
            min_foundation_weight_threshold=0.0,
        )

        original_check_signal = backtester.strategy_instance.check_signal_sync
        signal_fired = False

        def single_signal_trigger(
            pair_info, market_data, prev_pair_info, *args, **kwargs
        ):
            nonlocal signal_fired
            if (
                pair_info["current_candle_index"] == signal_fire_idx
                and not signal_fired
            ):
                signal_fired = True
                pair_info["natr"] = 2.0
                return original_check_signal(
                    pair_info, market_data, prev_pair_info, *args, **kwargs
                )
            return None, 0.0, None

        backtester.strategy_instance.check_signal_sync = single_signal_trigger

        await backtester.run_async()

    assert len(backtester.trade_log) == 1
    trade = backtester.trade_log[0]
    assert trade["exit_reason"] == "SL_AT_BE"
    assert trade["exit_price"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_conditional_management_supports_modify_take_profit_action(mocker):
    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        klines = create_test_kline_df(150, 100)
        mock_ta.atr.return_value = pd.Series([1.0] * 150, index=klines.index)

        test_json_config = {
            "min_foundation_weight_threshold": 0,
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {"type": "market_activity", "params": {}},
                    {
                        "type": "price_vs_level",
                        "params": {
                            "price_source": {"source": "candle", "key": "close"},
                            "operator": "gt",
                            "level_source": {"source": "value", "value": 99},
                        },
                    },
                ],
            },
            "initialization": {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 98.0,
                    "tp_type": "fixed_price",
                    "tp_value": 150.0,
                },
            },
            "positionManagement": [
                {
                    "id": "mng_cond",
                    "type": "conditional_management",
                    "if_conditions": {
                        "id": "if_pnl_pos",
                        "type": "AND",
                        "children": [
                            {
                                "id": "pnl_check",
                                "type": "price_vs_level",
                                "params": {
                                    "price_source": {
                                        "source": "position_state",
                                        "key": "unrealized_pnl_pct",
                                    },
                                    "operator": "gt",
                                    "level_source": {"source": "value", "value": 0.5},
                                },
                            }
                        ],
                    },
                    "then_actions": [
                        {
                            "id": "then_tp",
                            "type": "modify_take_profit",
                            "params": {
                                "new_tp_price": {"source": "value", "value": 101.2}
                            },
                        }
                    ],
                }
            ],
        }

        signal_fire_idx = 60
        klines.loc[klines.index[signal_fire_idx], ["close"]] = [100.0]
        klines.loc[klines.index[signal_fire_idx + 1], ["high", "low", "close"]] = [
            101.0,
            100.2,
            100.8,
        ]
        klines.loc[klines.index[signal_fire_idx + 2], ["high", "low", "close"]] = [
            101.4,
            100.4,
            101.1,
        ]

        backtester = DepthSightBacktester(
            strategy_name="VisualBuilderStrategy",
            symbol="TESTUSDT",
            params={"config": test_json_config},
            historical_data={"kline_1m": klines},
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            initial_balance=10000,
            min_trades_required=0,
            risk_params={},
            backtest_risk_params={
                "riskPerTradePercent": 1.0,
                "dailyMaxLossPercent": 1.0,
            },
            execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
            strategy_defaults={"risk_pct_per_trade": 0.01},
            ml_training_config={},
            ml_sim_log_path=None,
            min_foundation_weight_threshold=0.0,
        )

        original_check_signal = backtester.strategy_instance.check_signal_sync
        signal_fired = False

        def single_signal_trigger(
            pair_info, market_data, prev_pair_info, *args, **kwargs
        ):
            nonlocal signal_fired
            if (
                pair_info["current_candle_index"] == signal_fire_idx
                and not signal_fired
            ):
                signal_fired = True
                pair_info["natr"] = 2.0
                return original_check_signal(
                    pair_info, market_data, prev_pair_info, *args, **kwargs
                )
            return None, 0.0, None

        backtester.strategy_instance.check_signal_sync = single_signal_trigger

        await backtester.run_async()

    assert len(backtester.trade_log) == 1
    trade = backtester.trade_log[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["exit_price"] == pytest.approx(101.2)


@pytest.mark.asyncio
async def test_conditional_management_supports_close_position_action(mocker):
    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        klines = create_test_kline_df(150, 100)
        mock_ta.atr.return_value = pd.Series([1.0] * 150, index=klines.index)

        test_json_config = {
            "min_foundation_weight_threshold": 0,
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {"type": "market_activity", "params": {}},
                    {
                        "type": "price_vs_level",
                        "params": {
                            "price_source": {"source": "candle", "key": "close"},
                            "operator": "gt",
                            "level_source": {"source": "value", "value": 99},
                        },
                    },
                ],
            },
            "initialization": {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 98.0,
                    "tp_type": "fixed_price",
                    "tp_value": 150.0,
                },
            },
            "positionManagement": [
                {
                    "id": "mng_cond",
                    "type": "conditional_management",
                    "if_conditions": {
                        "id": "if_pnl_pos",
                        "type": "AND",
                        "children": [
                            {
                                "id": "pnl_check",
                                "type": "price_vs_level",
                                "params": {
                                    "price_source": {
                                        "source": "position_state",
                                        "key": "unrealized_pnl_pct",
                                    },
                                    "operator": "gt",
                                    "level_source": {"source": "value", "value": 0.5},
                                },
                            }
                        ],
                    },
                    "then_actions": [
                        {
                            "id": "then_close",
                            "type": "close_position",
                            "params": {},
                        }
                    ],
                }
            ],
        }

        signal_fire_idx = 60
        klines.loc[klines.index[signal_fire_idx], ["close"]] = [100.0]
        klines.loc[klines.index[signal_fire_idx + 1], ["high", "low", "close"]] = [
            101.0,
            100.2,
            100.8,
        ]

        backtester = DepthSightBacktester(
            strategy_name="VisualBuilderStrategy",
            symbol="TESTUSDT",
            params={"config": test_json_config},
            historical_data={"kline_1m": klines},
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            initial_balance=10000,
            min_trades_required=0,
            risk_params={},
            backtest_risk_params={
                "riskPerTradePercent": 1.0,
                "dailyMaxLossPercent": 1.0,
            },
            execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
            strategy_defaults={"risk_pct_per_trade": 0.01},
            ml_training_config={},
            ml_sim_log_path=None,
            min_foundation_weight_threshold=0.0,
        )

        original_check_signal = backtester.strategy_instance.check_signal_sync
        signal_fired = False

        def single_signal_trigger(
            pair_info, market_data, prev_pair_info, *args, **kwargs
        ):
            nonlocal signal_fired
            if (
                pair_info["current_candle_index"] == signal_fire_idx
                and not signal_fired
            ):
                signal_fired = True
                pair_info["natr"] = 2.0
                return original_check_signal(
                    pair_info, market_data, prev_pair_info, *args, **kwargs
                )
            return None, 0.0, None

        backtester.strategy_instance.check_signal_sync = single_signal_trigger

        await backtester.run_async()

    assert len(backtester.trade_log) == 1
    trade = backtester.trade_log[0]
    assert trade["exit_reason"] == "PM_ACTION_CLOSE"
    assert trade["exit_price"] == pytest.approx(100.8)

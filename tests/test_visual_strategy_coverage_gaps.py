import copy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from bot_module import strategy as strategy_module
from bot_module.depthsight_backtester import DepthSightBacktester
from bot_module.strategy import VisualBuilderStrategy


def create_flat_klines(num_candles: int = 150, price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(
        "2024-01-01 00:00:00", periods=num_candles, freq="1min", tz="UTC"
    )
    df = pd.DataFrame(
        {
            "open": np.full(num_candles, price),
            "high": np.full(num_candles, price + 0.4),
            "low": np.full(num_candles, price - 0.4),
            "close": np.full(num_candles, price),
            "volume": np.full(num_candles, 1000.0),
        },
        index=index,
    )
    return df


def build_market_data_for_unit_tests() -> dict:
    klines = create_flat_klines(200)
    return {
        "kline_1m": klines,
        "depth_trading": {"bids": [], "asks": []},
        "aggTrade": pd.DataFrame(
            {
                "price": [100.0, 100.1],
                "quantity": [1.0, 1.5],
                "is_buyer_maker": [False, True],
            },
            index=pd.date_range("2024-01-01 00:00:00", periods=2, freq="1s", tz="UTC"),
        ),
    }


def build_pair_info(**updates) -> dict:
    pair_info = {
        "symbol": "TESTUSDT",
        "last_price": 100.0,
        "open": 99.9,
        "high": 100.2,
        "low": 99.8,
        "close": 100.0,
        "atr": 1.0,
        "natr": 1.0,
        "relative_volume": 2.0,
        "tick_size": 0.01,
        "current_candle_index": 60,
        "candle_timeframe": "1m",
        "timestamp_dt": datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
        "SMA_10": 101.0,
        "SMA_50": 99.0,
        "RSI_14": 55.0,
        "ADX_14": 25.0,
    }
    pair_info.update(updates)
    return pair_info


@pytest.fixture
def visual_strategy_factory(monkeypatch):
    monkeypatch.setitem(
        strategy_module.STRATEGIES, "VisualBuilderStrategy", VisualBuilderStrategy
    )
    monkeypatch.setattr(strategy_module.config, "FOUNDATION_WEIGHTS", {}, raising=False)
    monkeypatch.setattr(
        strategy_module.config,
        "MIN_TOTAL_FOUNDATION_WEIGHT_THRESHOLD",
        0.0,
        raising=False,
    )

    def _create(config: dict):
        config_copy = copy.deepcopy(config)
        config_copy.setdefault("min_foundation_weight_threshold", 0.0)
        if "initialization" not in config_copy and "action" not in config_copy:
            config_copy["initialization"] = {
                "id": "act1",
                "type": "open_position",
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 95.0,
                    "tp_type": "fixed_price",
                    "tp_value": 110.0,
                },
            }

        instance = strategy_module.create_strategy_instance(
            strategy_name="VisualBuilderStrategy",
            params={"config": config_copy, "enabled": True},
        )
        assert instance is not None
        return instance

    return _create


@pytest.fixture
def register_visual_strategy(monkeypatch):
    monkeypatch.setitem(
        strategy_module.STRATEGIES, "VisualBuilderStrategy", VisualBuilderStrategy
    )
    monkeypatch.setattr(strategy_module.config, "FOUNDATION_WEIGHTS", {}, raising=False)
    monkeypatch.setattr(
        strategy_module.config,
        "MIN_TOTAL_FOUNDATION_WEIGHT_THRESHOLD",
        0.0,
        raising=False,
    )


def make_visual_backtester(
    config_data: dict, historical_data: dict
) -> DepthSightBacktester:
    prepared_history = {}
    for key, value in historical_data.items():
        prepared_history[key] = (
            value.copy() if isinstance(value, pd.DataFrame) else value
        )

    return DepthSightBacktester(
        strategy_name="VisualBuilderStrategy",
        symbol="TESTUSDT",
        params={"config": copy.deepcopy(config_data)},
        historical_data=prepared_history,
        initial_balance=10000.0,
        min_trades_required=0,
        risk_params={"riskPerTradePercent": 1.0, "dailyMaxLossPercent": 5.0},
        backtest_risk_params={"riskPerTradePercent": 1.0, "dailyMaxLossPercent": 5.0},
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        strategy_defaults={"VisualBuilderStrategy": {"risk_pct_per_trade": 0.01}},
        ml_training_config={},
        ml_sim_log_path=None,
        exchange_info={
            "tick_size": 0.01,
            "lot_params": {"stepSize": 0.001},
            "min_notional": 10.0,
        },
        min_foundation_weight_threshold=0.0,
        foundation_weights={},
        include_eod_in_log=True,
    )


def patch_single_signal(
    backtester: DepthSightBacktester, signal_fire_idx: int, pair_info_hook=None
):
    original_check_signal_sync = backtester.strategy_instance.check_signal_sync
    captured = {}
    signal_fired = False

    def single_signal_trigger(pair_info, market_data, prev_pair_info, *args, **kwargs):
        nonlocal signal_fired

        # PATCH: Optionally modify pair_info before calling
        if (
            pair_info_hook is not None
            and pair_info["current_candle_index"] == signal_fire_idx
        ):
            pair_info_hook(pair_info, market_data, prev_pair_info)

        # PATCH: Always call the original to update the internal state of the strategy (e.g., RTL state)
        signal, weight, trace = original_check_signal_sync(
            pair_info,
            market_data,
            prev_pair_info,
            *args,
            **kwargs,
        )

        if pair_info["current_candle_index"] == signal_fire_idx and not signal_fired:
            if signal:
                signal_fired = True
                captured["signal"] = signal
                captured["trace"] = trace
                return signal, weight, trace

        return None, 0.0, trace

    backtester.strategy_instance.check_signal_sync = single_signal_trigger
    return captured


def default_action_config() -> dict:
    return {
        "id": "act1",
        "type": "open_position",
        "params": {
            "direction": "LONG",
            "sl_type": "fixed_price",
            "sl_value": 95.0,
            "tp_type": "fixed_price",
            "tp_value": 140.0,
        },
    }


def test_time_filter_alias_creates_signal(visual_strategy_factory):
    strategy = visual_strategy_factory(
        {
            "filters": {
                "id": "f_root",
                "type": "AND",
                "children": [
                    {
                        "id": "time_alias",
                        "type": "time_filter",
                        "params": {"session": "london"},
                    }
                ],
            },
            "entryConditions": {"id": "e_root", "type": "AND", "children": []},
        }
    )

    signal, _, _ = strategy.check_signal_sync(
        build_pair_info(timestamp_dt=datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)),
        build_market_data_for_unit_tests(),
        None,
    )

    assert signal is not None


def test_stoch_condition_alias_creates_signal(visual_strategy_factory):
    strategy = visual_strategy_factory(
        {
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {
                        "id": "stoch_alias",
                        "type": "stoch_condition",
                        "params": {
                            "operator": "lt",
                            "value": 20,
                            "line": "k",
                            "k_period": 14,
                            "d_period": 3,
                            "smooth_k": 3,
                        },
                    }
                ],
            }
        }
    )

    signal, _, _ = strategy.check_signal_sync(
        build_pair_info(STOCHk_14_3_3=10.0, STOCHd_14_3_3=15.0),
        build_market_data_for_unit_tests(),
        None,
    )

    assert signal is not None


def test_bb_condition_alias_creates_signal(visual_strategy_factory):
    strategy = visual_strategy_factory(
        {
            "entryConditions": {
                "id": "e_root",
                "type": "AND",
                "children": [
                    {
                        "id": "bb_alias",
                        "type": "bb_condition",
                        "params": {
                            "check_type": "price_below_lower",
                            "period": 20,
                            "std_dev": 2.0,
                        },
                    }
                ],
            }
        }
    )

    signal, _, _ = strategy.check_signal_sync(
        build_pair_info(**{"close": 99.0, "BBL_20_2.0": 100.0, "BBU_20_2.0": 102.0}),
        build_market_data_for_unit_tests(),
        None,
    )

    assert signal is not None


@pytest.mark.asyncio
async def test_backtester_covers_open_interest_filter(register_visual_strategy):
    signal_fire_idx = 60
    klines = create_flat_klines()
    open_interest = pd.DataFrame(
        {"open_interest": np.linspace(100.0, 120.0, len(klines))},
        index=klines.index,
    )

    config_data = {
        "filters": {
            "id": "f_root",
            "type": "AND",
            "children": [
                {
                    "id": "oi_filter",
                    "type": "open_interest",
                    "params": {
                        "analyze": "change_pct",
                        "lookback": 5,
                        "operator": "gt",
                        "value": 0.3,
                    },
                }
            ],
        },
        "entryConditions": {"id": "e_root", "type": "AND", "children": []},
        "initialization": default_action_config(),
    }

    backtester = make_visual_backtester(
        config_data, {"kline_1m": klines, "open_interest": open_interest}
    )
    patch_single_signal(backtester, signal_fire_idx)

    await backtester.run_async()

    assert len(backtester.trade_log) == 1


@pytest.mark.asyncio
async def test_backtester_covers_rel_vol_filter(register_visual_strategy):
    signal_fire_idx = 60
    klines = create_flat_klines()

    config_data = {
        "filters": {
            "id": "f_root",
            "type": "AND",
            "children": [
                {
                    "id": "rv_filter",
                    "type": "rel_vol_filter",
                    "params": {"rel_vol_threshold": 1.5},
                }
            ],
        },
        "entryConditions": {"id": "e_root", "type": "AND", "children": []},
        "initialization": default_action_config(),
    }

    backtester = make_visual_backtester(config_data, {"kline_1m": klines})
    patch_single_signal(
        backtester,
        signal_fire_idx,
        pair_info_hook=lambda pair_info, *_: pair_info.update({"relative_volume": 2.5}),
    )

    await backtester.run_async()

    assert len(backtester.trade_log) == 1


@pytest.mark.asyncio
async def test_backtester_covers_price_consolidation(register_visual_strategy):
    signal_fire_idx = 60
    klines = create_flat_klines()
    klines.iloc[
        signal_fire_idx - 10 : signal_fire_idx, klines.columns.get_loc("high")
    ] = 100.2
    klines.iloc[
        signal_fire_idx - 10 : signal_fire_idx, klines.columns.get_loc("low")
    ] = 99.9
    klines.iloc[
        signal_fire_idx - 10 : signal_fire_idx, klines.columns.get_loc("close")
    ] = 100.0
    klines.iloc[
        signal_fire_idx - 10 : signal_fire_idx, klines.columns.get_loc("open")
    ] = 100.0

    config_data = {
        "entryConditions": {
            "id": "e_root",
            "type": "AND",
            "children": [
                {
                    "id": "consolidation",
                    "type": "price_consolidation",
                    "params": {"lookback_period": 10, "max_range_atr": 0.5},
                }
            ],
        },
        "initialization": default_action_config(),
    }

    backtester = make_visual_backtester(config_data, {"kline_1m": klines})
    patch_single_signal(
        backtester,
        signal_fire_idx,
        pair_info_hook=lambda pair_info, *_: pair_info.update({"atr": 1.0}),
    )

    await backtester.run_async()

    assert len(backtester.trade_log) == 1


@pytest.mark.asyncio
async def test_backtester_covers_return_to_level_breakout_retest(
    register_visual_strategy,
):
    signal_fire_idx = 60
    klines = create_flat_klines()
    # Set the price significantly above the level (100.0 + 2.0) so that departure_threshold (1.5 * ATR) is triggered
    klines.iloc[signal_fire_idx - 1, klines.columns.get_loc("close")] = 102.0
    klines.iloc[signal_fire_idx, klines.columns.get_loc("close")] = 100.0

    config_data = {
        "entryConditions": {
            "id": "e_root",
            "type": "AND",
            "children": [
                {
                    "id": "level1",
                    "type": "local_level",
                    "params": {"is_data_provider": True},
                },
                {
                    "id": "returner",
                    "type": "return_to_level",
                    "params": {
                        "level_block_id": "level1",
                        "retest_type": "breakout_retest",
                    },
                },
            ],
        },
        "initialization": default_action_config(),
    }

    backtester = make_visual_backtester(config_data, {"kline_1m": klines})
    backtester.strategy_instance.condition_checkers["local_level"] = lambda **kwargs: (
        True,
        {"detected_level": 100.0},
    )
    patch_single_signal(
        backtester,
        signal_fire_idx,
        pair_info_hook=lambda pair_info, *_: pair_info.update(
            {"atr": 1.0, "last_price": 100.0}
        ),
    )

    await backtester.run_async()

    assert len(backtester.trade_log) == 1


@pytest.mark.asyncio
async def test_backtester_covers_senior_tf_confluence(register_visual_strategy):
    signal_fire_idx = 60
    klines = create_flat_klines()
    kline_1h = (
        klines.resample("1h")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )

    config_data = {
        "entryConditions": {
            "id": "e_root",
            "type": "AND",
            "children": [
                {
                    "id": "htf_root",
                    "type": "senior_tf_confluence",
                    "params": {"timeframe": "1h"},
                    "children": [
                        {
                            "id": "htf_trend",
                            "type": "trend_direction",
                            "params": {"required_trend": "LONG", "timeframe": "1h"},
                        }
                    ],
                }
            ],
        },
        "initialization": default_action_config(),
    }

    backtester = make_visual_backtester(
        config_data, {"kline_1m": klines, "kline_1h": kline_1h}
    )
    called = {}

    def mocked_create_htf_pair_info(pair_info, market_data, htf_timeframe):
        called["timeframe"] = htf_timeframe
        htf_pair_info = pair_info.copy()
        htf_pair_info.update(
            {
                "candle_timeframe": "1h",
                "last_price": 120.0,
                "atr": 1.0,
                "SMA_10": 121.0,
                "SMA_50": 119.0,
                "RSI_14": 55.0,
            }
        )
        return htf_pair_info

    backtester.strategy_instance._create_htf_pair_info = mocked_create_htf_pair_info
    patch_single_signal(backtester, signal_fire_idx)

    await backtester.run_async()

    assert called["timeframe"] == "1h"
    assert len(backtester.trade_log) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block_type",
    ["l2_microstructure", "l2_microstructure_check", "orderbook_imbalance"],
)
async def test_backtester_skips_l2_microstructure_variants_without_l2_data(
    register_visual_strategy, block_type
):
    signal_fire_idx = 60
    klines = create_flat_klines()

    config_data = {
        "entryConditions": {
            "id": "e_root",
            "type": "AND",
            "children": [
                {
                    "id": "l2_guard",
                    "type": block_type,
                    "params": {"single_order_size_usd": 250000.0},
                }
            ],
        },
        "initialization": default_action_config(),
    }

    backtester = make_visual_backtester(config_data, {"kline_1m": klines})
    patch_single_signal(backtester, signal_fire_idx)

    await backtester.run_async()

    assert len(backtester.trade_log) == 1


@pytest.mark.asyncio
async def test_conditional_management_supports_trailing_stop_action(
    register_visual_strategy,
):
    signal_fire_idx = 60
    klines = create_flat_klines()
    klines.iloc[signal_fire_idx, klines.columns.get_loc("close")] = 100.0
    klines.iloc[signal_fire_idx + 1, klines.columns.get_loc("high")] = 104.0
    klines.iloc[signal_fire_idx + 1, klines.columns.get_loc("low")] = 103.2
    klines.iloc[signal_fire_idx + 1, klines.columns.get_loc("close")] = 103.5
    klines.iloc[signal_fire_idx + 2, klines.columns.get_loc("high")] = 103.1
    klines.iloc[signal_fire_idx + 2, klines.columns.get_loc("low")] = 102.8
    klines.iloc[signal_fire_idx + 2, klines.columns.get_loc("close")] = 103.0

    config_data = {
        "entryConditions": {"id": "e_root", "type": "AND", "children": []},
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
                "id": "pm_cond",
                "type": "conditional_management",
                "if_conditions": {
                    "id": "if_root",
                    "type": "AND",
                    "children": [
                        {
                            "id": "pnl_gate",
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
                        "id": "trail_action",
                        "type": "trailing_stop",
                        "params": {"type": "ATR", "value": 1.0},
                    }
                ],
            }
        ],
    }

    backtester = make_visual_backtester(config_data, {"kline_1m": klines})
    patch_single_signal(
        backtester,
        signal_fire_idx,
        pair_info_hook=lambda pair_info, *_: pair_info.update({"atr": 1.0}),
    )

    original_manage_position = backtester.strategy_instance.manage_position

    async def managed_with_atr(position, pair_info, market_data, prev_pair_info):
        pair_info["atr"] = 1.0
        return await original_manage_position(
            position, pair_info, market_data, prev_pair_info
        )

    backtester.strategy_instance.manage_position = managed_with_atr

    await backtester.run_async()

    assert len(backtester.trade_log) == 1
    trade = backtester.trade_log[0]
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["exit_price"] == pytest.approx(103.0)

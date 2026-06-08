# tests/test_strategy_new_conditions.py
import logging
import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta

from bot_module import strategy as strategy_module
from bot_module.strategy import BaseStrategy, VisualBuilderStrategy
from bot_module.datatypes import BasePosition, SignalDirection


@pytest.fixture
def base_strategy():
    return BaseStrategy()


@pytest.fixture
def market_data():
    common_index = pd.to_datetime(
        [datetime.now(timezone.utc) - timedelta(minutes=i) for i in range(59, -1, -1)]
    )

    return {
        "kline_1m_BTCUSDT": pd.DataFrame(
            {"close": [100 + i for i in range(60)]}, index=common_index
        ),
        "kline_1m": pd.DataFrame(
            {"close": [10 + i for i in range(60)]}, index=common_index
        ),
        "open_interest": pd.DataFrame(
            {"open_interest": [1000 + i * 20 for i in range(60)]}, index=common_index
        ),
    }


@pytest.fixture
def pair_info():
    return {"symbol": "ETHUSDT", "candle_timeframe": "1m"}


def test_btc_state_filter(base_strategy, market_data, pair_info):
    node = {"type": "btc_state_filter", "params": {"required_state": "Trending Up"}}
    result, _ = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result

    market_data["kline_1m_BTCUSDT"]["close"] = [100] * 60
    node = {"type": "btc_state_filter", "params": {"required_state": "Consolidation"}}
    result, _ = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result


def test_btc_state_filter_accepts_editor_enum_values(
    base_strategy, market_data, pair_info
):
    node = {"type": "btc_state_filter", "params": {"required_state": "trending_up"}}
    result, _ = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result


def test_open_interest_condition(base_strategy, market_data, pair_info):
    # OI at the end: 1590. OI 5 steps back: 1540.
    # Change = ((1590-1540)/1540)*100 = 3.24%
    node = {
        "type": "open_interest",
        "params": {
            "analyze": "change_pct",
            "lookback": 5,
            "operator": "gt",
            "value": 3.0,
        },
    }
    result, _ = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result


def test_l2_microstructure_alias_skips_without_depth(
    base_strategy, market_data, pair_info
):
    node = {
        "type": "l2_microstructure_check",
        "params": {"check_type": "large_order", "single_order_size_usd": 100000},
    }
    result, trace = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result
    assert (
        trace["details"].get("info")
        == "L2 microstructure check skipped (backtest mode)."
    )


def test_correlation_condition(base_strategy, market_data, pair_info):
    market_data["kline_1m"]["close"] = [100 + i for i in range(60)]
    market_data["kline_1m_BTCUSDT"]["close"] = [100 + i for i in range(60)]

    node = {
        "type": "correlation",
        "params": {"lookback": 20, "operator": "gt", "value": 0.9},
    }
    result, _ = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result


def test_level_touch_analyzer(base_strategy, market_data, pair_info):
    market_data["kline_1m"]["close"] = [
        68,
        69,
        69.5,
        69.2,
        69.8,
        69.1,
        69.7,
        69.3,
        69.9,
        69.4,
    ] * 6
    market_data["kline_1m"]["high"] = market_data["kline_1m"]["close"] + 0.1
    market_data["kline_1m"]["low"] = market_data["kline_1m"]["close"] - 0.3
    market_data["kline_1m"].iloc[
        -18, market_data["kline_1m"].columns.get_loc("high")
    ] = 100.04
    market_data["kline_1m"].iloc[
        -10, market_data["kline_1m"].columns.get_loc("high")
    ] = 100.02
    market_data["kline_1m"].iloc[
        -3, market_data["kline_1m"].columns.get_loc("high")
    ] = 100.03

    node = {
        "type": "level_touch_analyzer",
        "params": {
            "level_source": 100,
            "touch_tolerance_pct": 0.1,
            "lookback_candles": 20,
            "invalidate_on_pierce": True,
            "min_touches": 3,
        },
    }
    result, trace = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result, f"Level touch failed: {trace.get('details')}"
    assert trace["details"]["level"] == 100
    assert trace["details"]["touches_count"] == 3
    assert trace["details"]["is_valid"] is True


def test_level_touch_analyzer_invalidates_deep_pierce(
    base_strategy, market_data, pair_info
):
    market_data["kline_1m"]["close"] = [99] * 60
    market_data["kline_1m"]["high"] = [99.5] * 60
    market_data["kline_1m"]["low"] = [98.5] * 60
    market_data["kline_1m"].iloc[
        -5, market_data["kline_1m"].columns.get_loc("high")
    ] = 100.05
    market_data["kline_1m"].iloc[
        -2, market_data["kline_1m"].columns.get_loc("high")
    ] = 101.0

    node = {
        "type": "level_touch_analyzer",
        "params": {
            "level_source": 100,
            "touch_tolerance_pct": 0.1,
            "lookback_candles": 10,
            "invalidate_on_pierce": True,
            "min_touches": 1,
        },
    }
    result, trace = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert not result
    assert trace["details"]["pierce_detected"] is True
    assert trace["details"]["is_valid"] is False


def test_volatility_squeeze(base_strategy, market_data, pair_info):
    # Creating 100 candles. Volatility drops at the end.
    # BBW = (Upper - Lower) / Middle.
    # If std=0, BBW=0.
    close_prices = []
    for i in range(80):
        close_prices.append(100 + (i % 10))  # High volatility
    for i in range(20):
        close_prices.append(105 + (i % 2) * 0.1)  # Low volatility (squeeze)

    df = pd.DataFrame(
        {"close": close_prices},
        index=pd.to_datetime(
            [
                datetime.now(timezone.utc) - timedelta(minutes=i)
                for i in range(99, -1, -1)
            ]
        ),
    )
    market_data["kline_1m"] = df

    node = {
        "type": "volatility_squeeze",
        "params": {"lookback_candles": 50, "squeeze_ratio": 0.6},
    }
    result, trace = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    assert result, f"Volatility squeeze failed: {trace.get('details')}"
    assert trace["details"]["is_squeezing"] is True
    assert (
        trace["details"]["current_range_pct"]
        <= trace["details"]["past_range_pct"] * 0.6
    )


def test_price_action_analyzer_bullish(base_strategy, market_data, pair_info):
    # Constructing a clear HH + HL structure
    # Peak 1: 30, Trough 1: 10, Peak 2: 40, Trough 2: 20
    prices = (
        list(range(5, 31))
        + list(range(29, 9, -1))
        + list(range(11, 41))
        + list(range(39, 19, -1))
    )
    # Tail up so that the last trough 20 is clearly expressed
    prices += [21, 22]

    df = pd.DataFrame(
        {
            "high": [p + 0.1 for p in prices],
            "low": [p - 0.1 for p in prices],
            "close": prices,
        },
        index=pd.to_datetime(
            [
                datetime.now(timezone.utc) - timedelta(minutes=i)
                for i in range(len(prices) - 1, -1, -1)
            ]
        ),
    )
    market_data["kline_1m"] = df

    node = {
        "type": "price_action_analyzer",
        "params": {
            "structure_type": "higher_lows",
            "lookback_candles": 80,
            "order": 5,
            "min_points": 2,
        },
    }
    result, trace = base_strategy._evaluate_condition_tree(
        node, pair_info, market_data, prev_pair_info=None
    )
    # Expected:
    # Peaks: 30.1, 40.1 (HH)
    # Minimums: 9.9, 19.9 (HL)
    assert result, f"Price action failed: {trace.get('details')}"
    assert trace["details"]["last_high"] == 40.1
    assert trace["details"]["prev_high"] == 30.1
    assert trace["details"]["last_low"] == 19.9
    assert trace["details"]["prev_low"] == 9.9


def test_live_fast_rejection_short_circuits_and(monkeypatch):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    strategy_json = {
        "entryConditions": {
            "id": "root",
            "type": "AND",
            "children": [
                {"id": "first", "type": "first_false"},
                {"id": "second", "type": "must_not_run"},
            ],
        },
        "initialization": {"type": "open_position", "params": {"direction": "LONG"}},
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    calls = []

    def first_false(**kwargs):
        calls.append("first")
        return False, {"reason": "first failed"}

    def must_not_run(**kwargs):
        calls.append("second")
        return True, {}

    strategy.condition_checkers["first_false"] = first_false
    strategy.condition_checkers["must_not_run"] = must_not_run

    signal, weight, trace = strategy._execute_visual_strategy(
        strategy_json,
        {
            "symbol": "TESTUSDT",
            "is_live_mode": True,
            "last_price": 100.0,
            "atr": 1.0,
            "tick_size": 0.01,
        },
        {},
        None,
    )

    assert signal is None
    assert weight == 0.0
    assert calls == ["first"]
    assert strategy._compiled_fast_entry_root is not None
    assert strategy._compiled_fast_entry_root.children[0].checker is first_false
    assert trace["details"]["short_circuit"] == "AND_FALSE"
    assert trace["rejection_reason"] == "entry_conditions"


def test_live_fast_path_restores_state_before_full_trace(monkeypatch):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    strategy_json = {
        "entryConditions": {
            "id": "root",
            "type": "AND",
            "children": [
                {"id": "pass", "type": "stateful_true", "params": {"foo": "bar"}},
            ],
        },
        "initialization": {
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 1.0,
                "tp_type": "rr_multiplier",
                "tp_value": 2.0,
            },
        },
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    saw_marker = []

    def stateful_true(**kwargs):
        saw_marker.append("fast_marker" in strategy._rtl_state)
        strategy._rtl_state["fast_marker"] = {"seen": True}
        return True, {"ok": True}

    strategy.condition_checkers["stateful_true"] = stateful_true

    signal, weight, trace = strategy._execute_visual_strategy(
        strategy_json,
        {
            "symbol": "TESTUSDT",
            "is_live_mode": True,
            "last_price": 100.0,
            "atr": 1.0,
            "tick_size": 0.01,
        },
        {},
        None,
    )

    assert signal is not None
    assert saw_marker == [False, False]
    assert trace["children"][0]["params"] == {"foo": "bar"}


@pytest.mark.parametrize(
    ("pair_flags", "live_fast_enabled", "trace_rejections_enabled"),
    [
        ({}, True, False),
        ({"is_live_mode": True, "is_backtest_mode": True}, True, False),
        ({"is_live_mode": True}, False, False),
        ({"is_live_mode": True}, True, True),
    ],
)
def test_live_fast_path_disabled_conditions_run_full_tree(
    monkeypatch,
    pair_flags,
    live_fast_enabled,
    trace_rejections_enabled,
):
    monkeypatch.setattr(
        strategy_module.config,
        "LIVE_FAST_SIGNAL_CHECK",
        live_fast_enabled,
        raising=False,
    )
    monkeypatch.setattr(
        strategy_module.config,
        "TRACE_REJECTIONS_ENABLED",
        trace_rejections_enabled,
        raising=False,
    )

    strategy_json = {
        "entryConditions": {
            "id": "root",
            "type": "AND",
            "children": [
                {"id": "first", "type": "first_false"},
                {"id": "second", "type": "second_true"},
            ],
        },
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    calls = []

    def first_false(**kwargs):
        calls.append("first")
        return False, {}

    def second_true(**kwargs):
        calls.append("second")
        return True, {}

    strategy.condition_checkers["first_false"] = first_false
    strategy.condition_checkers["second_true"] = second_true

    pair_info_for_check = {
        "symbol": "TESTUSDT",
        "last_price": 100.0,
        "atr": 1.0,
        "tick_size": 0.01,
    }
    pair_info_for_check.update(pair_flags)
    signal, _, trace = strategy._execute_visual_strategy(
        strategy_json, pair_info_for_check, {}, None
    )

    assert signal is None
    assert calls == ["first", "second"]
    assert strategy._compiled_fast_entry_root is None
    assert len(trace["children"]) == 2


def test_live_fast_rejection_short_circuits_or(monkeypatch):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    strategy_json = {
        "entryConditions": {
            "id": "root",
            "type": "OR",
            "children": [
                {"id": "first", "type": "first_true"},
                {"id": "second", "type": "must_not_run"},
            ],
        },
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    calls = []

    def first_true(**kwargs):
        calls.append("first")
        return True, {}

    def must_not_run(**kwargs):
        calls.append("second")
        return False, {}

    strategy.condition_checkers["first_true"] = first_true
    strategy.condition_checkers["must_not_run"] = must_not_run

    signal_possible, weight, trace = strategy._execute_visual_strategy_fast_rejection(
        strategy_json,
        {
            "symbol": "TESTUSDT",
            "is_live_mode": True,
            "last_price": 100.0,
            "atr": 1.0,
            "tick_size": 0.01,
        },
        {},
        None,
    )

    assert signal_possible is True
    assert weight == 0.0
    assert calls == ["first"]
    assert trace["details"]["short_circuit"] == "OR_TRUE"
    assert len(trace["children"]) == 1


def test_live_fast_rejection_by_filters_skips_entry_conditions(monkeypatch):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    strategy_json = {
        "filters": {"id": "filters", "type": "filter_false"},
        "entryConditions": {"id": "entry", "type": "must_not_run"},
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    calls = []

    def filter_false(**kwargs):
        calls.append("filter")
        return False, {"reason": "blocked"}

    def must_not_run(**kwargs):
        calls.append("entry")
        return True, {}

    strategy.condition_checkers["filter_false"] = filter_false
    strategy.condition_checkers["must_not_run"] = must_not_run

    signal, weight, trace = strategy._execute_visual_strategy(
        strategy_json,
        {
            "symbol": "TESTUSDT",
            "is_live_mode": True,
            "last_price": 100.0,
            "atr": 1.0,
            "tick_size": 0.01,
        },
        {},
        None,
    )

    assert signal is None
    assert weight == 0.0
    assert calls == ["filter"]
    assert trace["id"] == "filters"
    assert trace["rejection_reason"] == "filter"


def test_live_fast_compiled_tree_rebuilds_when_strategy_json_object_changes(
    monkeypatch,
):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    first_config = {
        "entryConditions": {
            "id": "root_a",
            "type": "AND",
            "children": [{"id": "a", "type": "checker_a"}],
        }
    }
    second_config = {
        "entryConditions": {
            "id": "root_b",
            "type": "AND",
            "children": [{"id": "b", "type": "checker_b"}],
        }
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": first_config,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    calls = []

    def checker_a(**kwargs):
        calls.append("a")
        return False, {}

    def checker_b(**kwargs):
        calls.append("b")
        return False, {}

    strategy.condition_checkers["checker_a"] = checker_a
    strategy.condition_checkers["checker_b"] = checker_b
    pair_info_for_check = {
        "symbol": "TESTUSDT",
        "is_live_mode": True,
        "last_price": 100.0,
        "atr": 1.0,
        "tick_size": 0.01,
    }

    strategy._execute_visual_strategy_fast_rejection(
        first_config, pair_info_for_check, {}, None
    )
    assert strategy._compiled_fast_config_id == id(first_config)
    assert strategy._compiled_fast_entry_root.children[0].checker is checker_a

    strategy._execute_visual_strategy_fast_rejection(
        second_config, pair_info_for_check, {}, None
    )
    assert calls == ["a", "b"]
    assert strategy._compiled_fast_config_id == id(second_config)
    assert strategy._compiled_fast_entry_root.children[0].checker is checker_b


def test_live_fast_unknown_condition_returns_rejection_trace(monkeypatch):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    strategy_json = {
        "entryConditions": {"id": "unknown_node", "type": "unknown_condition"}
    }
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )

    signal_possible, weight, trace = strategy._execute_visual_strategy_fast_rejection(
        strategy_json,
        {
            "symbol": "TESTUSDT",
            "is_live_mode": True,
            "last_price": 100.0,
            "atr": 1.0,
            "tick_size": 0.01,
        },
        {},
        None,
    )

    assert signal_possible is False
    assert weight == 0.0
    assert trace["id"] == "unknown_node"
    assert trace["rejection_reason"] == "entry_conditions"
    assert "Unknown node_type" in trace["details"]["error"]


def test_live_fast_compiled_evaluator_uses_bound_params(monkeypatch):
    monkeypatch.setattr(
        strategy_module.config, "LIVE_FAST_SIGNAL_CHECK", True, raising=False
    )
    monkeypatch.setattr(
        strategy_module.config, "TRACE_REJECTIONS_ENABLED", False, raising=False
    )

    condition_node = {
        "id": "param_node",
        "type": "param_checker",
        "params": {"value": "compiled"},
    }
    strategy_json = {"entryConditions": condition_node}
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
        }
    )
    seen_values = []

    def param_checker(**kwargs):
        seen_values.append(kwargs["params"]["value"])
        return False, {}

    strategy.condition_checkers["param_checker"] = param_checker
    pair_info_for_check = {
        "symbol": "TESTUSDT",
        "is_live_mode": True,
        "last_price": 100.0,
        "atr": 1.0,
        "tick_size": 0.01,
    }

    strategy._execute_visual_strategy_fast_rejection(
        strategy_json, pair_info_for_check, {}, None
    )
    condition_node["params"] = {"value": "json-replaced"}
    strategy._execute_visual_strategy_fast_rejection(
        strategy_json, pair_info_for_check, {}, None
    )

    assert seen_values == ["compiled", "compiled"]


@pytest.mark.asyncio
async def test_manage_position_noop_does_not_emit_hot_path_info_logs(caplog):
    strategy = VisualBuilderStrategy(params={"config": {}, "enabled": True})
    position = BasePosition(
        symbol="TESTUSDT",
        direction=SignalDirection.LONG,
        entry_price=100.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=datetime.now(timezone.utc).timestamp(),
        strategy="VisualBuilderStrategy",
        initial_stop_loss=90.0,
        current_sl_price=90.0,
        initial_take_profit=110.0,
        client_order_id="test-client-order",
    )
    pair_info_for_check = {
        "symbol": "TESTUSDT",
        "is_live_mode": True,
        "timestamp_dt": datetime.now(timezone.utc),
        "current_candle_index": 1,
        "high": 101.0,
        "low": 99.0,
        "tick_size": 0.01,
    }

    caplog.set_level(logging.INFO, logger="bot_module.strategy")
    caplog.clear()
    updated_position, exit_details = await strategy.manage_position(
        position, pair_info_for_check, {}, None
    )

    hot_path_markers = (
        "manage_position ENTRY",
        "DIAGNOSTIC-STEP",
        "PM_CONFIG_DEBUG",
        "PM CHECK",
        "BE_CHECK_ENTRY",
        "R:R Check",
    )
    captured_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "bot_module.strategy"
    ]

    assert updated_position is position
    assert exit_details is None
    assert not any(
        marker in message
        for marker in hot_path_markers
        for message in captured_messages
    )

import pandas as pd
import pytest
from datetime import datetime, timezone

from bot_module.fast_vector_backtester import FastVectorBacktester
from api.simulation_router import _filter_user_visible_trades
from tasks import _normalize_vector_results, _normalize_vector_trade_records


def _build_single_trade_df() -> pd.DataFrame:
    index = pd.date_range("2024-01-01 00:00:00", periods=25, freq="min")
    rows = []

    for i, ts in enumerate(index):
        row = {
            "open": 100.0,
            "high": 100.4,
            "low": 99.6,
            "close": 99.8,
            "volume": 1000.0,
        }
        if i == 18:
            row.update({"open": 100.0, "high": 101.2, "low": 99.8, "close": 101.0})
        elif i == 19:
            row.update({"open": 100.0, "high": 103.0, "low": 99.9, "close": 102.5})
        rows.append(row)

    return pd.DataFrame(rows, index=index)


def _build_mtf_1m_df() -> pd.DataFrame:
    index = pd.date_range("2024-01-01 00:00:00", periods=260, freq="min")
    rows = []

    for ts in index:
        row = {
            "open": 100.0,
            "high": 100.4,
            "low": 99.6,
            "close": 99.8,
            "volume": 1000.0,
        }
        if ts == pd.Timestamp("2024-01-01 03:10:00"):
            row.update({"open": 100.0, "high": 101.2, "low": 99.8, "close": 101.0})
        elif ts == pd.Timestamp("2024-01-01 03:11:00"):
            row.update({"open": 100.0, "high": 103.0, "low": 99.9, "close": 102.5})
        rows.append(row)

    return pd.DataFrame(rows, index=index)


def _build_mtf_1h_df() -> pd.DataFrame:
    index = pd.date_range("2024-01-01 00:00:00", periods=5, freq="h")
    closes = [100.0, 105.0, 110.0, 115.0, 120.0]
    return pd.DataFrame(
        {
            "open": [price - 1.0 for price in closes],
            "high": [price + 2.0 for price in closes],
            "low": [price - 2.0 for price in closes],
            "close": closes,
            "volume": [10_000.0] * len(closes),
        },
        index=index,
    )


def _build_strategy() -> dict:
    return {
        "entryConditions": {
            "id": "entry_root",
            "type": "value_comparison",
            "params": {
                "leftOperand": {"source": "candle", "key": "close"},
                "rightOperand": {"source": "candle", "key": "open"},
                "operator": "gt",
            },
        },
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "sl_type": "percent_from_price",
                "sl_value": 1.0,
                "tp_type": "rr_multiplier",
                "tp_value": 2.0,
                "max_hold_candles": 5,
            },
        },
    }


def _build_mtf_trend_strategy() -> dict:
    return {
        "entryConditions": {
            "id": "entry_root",
            "type": "AND",
            "children": [
                {
                    "id": "close_above_open",
                    "type": "value_comparison",
                    "params": {
                        "leftOperand": {"source": "candle", "key": "close"},
                        "rightOperand": {"source": "candle", "key": "open"},
                        "operator": "gt",
                    },
                },
                {
                    "id": "h1_trend_up",
                    "type": "trend_direction",
                    "params": {
                        "timeframe": "1h",
                        "sma_fast_period": 2,
                        "sma_slow_period": 3,
                        "rsi_period": 2,
                        "rsi_lower_bound": 40,
                        "rsi_upper_bound": 60,
                        "direction": "long",
                    },
                },
            ],
        },
        "initialization": _build_strategy()["initialization"],
    }


def _build_rsi_strategy() -> dict:
    return {
        "entryConditions": {
            "id": "entry_root",
            "type": "AND",
            "children": [
                {
                    "id": "close_above_open",
                    "type": "value_comparison",
                    "params": {
                        "leftOperand": {"source": "candle", "key": "close"},
                        "rightOperand": {"source": "candle", "key": "open"},
                        "operator": "gt",
                    },
                },
                {
                    "id": "rsi_entry",
                    "type": "rsi_condition",
                    "params": {
                        "period": 14,
                        "operator": "gt",
                        "value": 50,
                    },
                },
            ],
        },
        "initialization": _build_strategy()["initialization"],
    }


def _build_depthsight_kwargs() -> dict:
    return {
        "strategy_name": "VisualBuilderStrategy",
        "symbol": "TESTUSDT",
        "params": {
            "config": _build_strategy(),
            "candle_timeframe": "1m",
        },
        "historical_data": {
            "kline_1m": _build_single_trade_df(),
        },
        "initial_balance": 10_000.0,
        "risk_params": {
            "riskPerTradePercent": 1.0,
            "dailyMaxLossPercent": 100.0,
            "maxConsecutiveLosses": 100,
            "maxDrawdown": 100.0,
            "maxStopDistancePct": 10.0,
            "minRrRatio": 1.0,
        },
        "backtest_risk_params": {
            "riskPerTradePercent": 1.0,
            "dailyMaxLossPercent": 100.0,
            "maxConsecutiveLosses": 100,
            "maxDrawdown": 100.0,
            "maxStopDistancePct": 10.0,
            "minRrRatio": 1.0,
        },
        "execution_config": {
            "commission_pct": 0.001,
            "slippage_pct": 0.0,
        },
        "exchange_info": {
            "lot_params": {"stepSize": 1.0, "minQty": 1.0, "maxQty": 100000.0},
            "min_notional": 1.0,
        },
    }


def test_fast_vector_accepts_depthsight_constructor_contract():
    kwargs = _build_depthsight_kwargs()
    kwargs["actual_trading_start_dt"] = kwargs["historical_data"]["kline_1m"].index[19]

    backtester = FastVectorBacktester(**kwargs)
    results = backtester.run()

    assert backtester.symbol == "TESTUSDT"
    assert backtester.strategy_name == "VisualBuilderStrategy"
    assert backtester.commission_pct == pytest.approx(0.001)
    assert results["total_trades"] == pytest.approx(1.0)
    assert (
        backtester.trade_log[0]["entry_time"]
        >= kwargs["actual_trading_start_dt"].to_pydatetime()
    )


def test_fast_vector_uses_depthsight_style_sizing_and_commission():
    backtester = FastVectorBacktester(**_build_depthsight_kwargs())
    results = backtester.run()

    assert results["total_trades"] == pytest.approx(1.0)

    trade = backtester.trade_log[0]
    assert trade["quantity"] == pytest.approx(1.0, abs=1e-12)
    assert trade["filled_quantity"] == pytest.approx(100.0, abs=1e-12)
    assert trade["commission_usd"] == pytest.approx(20.2, abs=1e-9)
    assert trade["pnl_usd"] == pytest.approx(179.8, abs=1e-9)
    assert trade["decision_trace"]["id"] == "entry_root"
    assert trade["decision_trace"]["result"] is True
    assert [execution["type"] for execution in trade["executions"]] == ["ENTRY", "EXIT"]
    assert results["total_pnl"] == pytest.approx(179.8, abs=1e-9)
    assert results["total_commission"] == pytest.approx(20.2, abs=1e-9)


def test_fast_vector_decision_trace_includes_indicator_details():
    kwargs = _build_depthsight_kwargs()
    kwargs["params"] = {
        **kwargs["params"],
        "config": _build_rsi_strategy(),
    }

    backtester = FastVectorBacktester(**kwargs)
    results = backtester.run()

    assert results["total_trades"] == pytest.approx(1.0)
    trace = backtester.trade_log[0]["decision_trace"]
    rsi_node = next(child for child in trace["children"] if child["id"] == "rsi_entry")

    assert rsi_node["result"] is True
    assert rsi_node["details"]["period"] == 14
    assert rsi_node["details"]["operator"] == "gt"
    assert rsi_node["details"]["threshold"] == pytest.approx(50.0)
    assert isinstance(rsi_node["details"]["rsi"], float)


def test_fast_vector_uses_higher_timeframe_trend_direction_data():
    kwargs = _build_depthsight_kwargs()
    kwargs["params"] = {
        **kwargs["params"],
        "config": _build_mtf_trend_strategy(),
        "candle_timeframe": "1m",
    }
    kwargs["historical_data"] = {
        "kline_1m": _build_mtf_1m_df(),
        "kline_1h": _build_mtf_1h_df(),
    }

    backtester = FastVectorBacktester(**kwargs)
    results = backtester.run()

    assert backtester.is_mtf is True
    assert backtester.data_context["1h"].index.freqstr == "h"
    assert results["total_trades"] == pytest.approx(1.0)

    trade = backtester.trade_log[0]
    trend_node = next(
        child
        for child in trade["decision_trace"]["children"]
        if child["id"] == "h1_trend_up"
    )
    assert trend_node["result"] is True
    assert trend_node["details"]["sma_fast"] == pytest.approx(107.5)
    assert trend_node["details"]["sma_slow"] == pytest.approx(105.0)


def test_fast_vector_returns_depthsight_style_analytics_report():
    backtester = FastVectorBacktester(**_build_depthsight_kwargs())
    results = backtester.run()

    analytics_report = results["analytics_report"]
    event_counters = analytics_report["event_counters"]

    assert event_counters["signals_generated_total"] >= 1
    assert event_counters["trades_opened"] == 1
    assert "rejections" in event_counters
    assert "foundation_trigger_counts" in event_counters
    assert analytics_report["anomalies"] == []


def test_vector_result_normalization_preserves_analytics_and_ms_equity_curve():
    analytics_report = {
        "event_counters": {
            "signals_generated_total": 3,
            "foundation_trigger_counts": {},
            "rejections": {
                "by_global_risk_limit": 0,
                "by_cooldown": 1,
                "by_filter": {"filter_a": 2},
                "by_weight_threshold": 0,
                "by_position_calculation": 0,
                "by_slippage_beyond_sl": 0,
                "by_risk_manager": 0,
                "by_risk_manager_reasons": {},
            },
            "trades_opened": 1,
            "errors": {},
        },
        "anomalies": [],
    }
    raw_results = {
        "equity_curve": [(datetime(2024, 1, 1, tzinfo=timezone.utc), 10000.0)],
        "analytics_report": analytics_report,
        "profit_factor": 1.5,
        "win_rate": 50.0,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.4,
        "consistency_score": 0.5,
        "total_pnl_pct": 2.5,
        "max_dd": 3.0,
    }

    normalized = _normalize_vector_results(
        raw_results=raw_results,
        normalized_trades=[],
        total_commission=0.0,
        initial_balance=10000.0,
    )

    assert normalized["analytics_report"] == analytics_report
    assert normalized["equity_curve"] == [(1704067200000, 10000.0)]


def test_vector_trade_normalization_preserves_trace_and_execution_events():
    raw_trades = [
        {
            "entry_time": datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
            "exit_time": datetime(2024, 1, 1, 2, tzinfo=timezone.utc),
            "entry_price": 100.0,
            "exit_price": 102.0,
            "filled_quantity": 1.5,
            "pnl_usd": 3.0,
            "commission_usd": 0.1,
            "direction": "LONG",
            "exit_reason": "TAKE_PROFIT",
            "decision_trace": {
                "id": "entry_root",
                "type": "AND",
                "result": True,
                "children": [],
            },
            "executions": [
                {
                    "timestamp": datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                    "price": 100.0,
                    "quantity": 1.5,
                    "type": "ENTRY",
                },
                {
                    "timestamp": datetime(2024, 1, 1, 2, tzinfo=timezone.utc),
                    "price": 102.0,
                    "quantity": 1.5,
                    "type": "EXIT",
                },
            ],
        }
    ]

    normalized, total_commission = _normalize_vector_trade_records(
        raw_trades,
        run_id="run-1",
        initial_balance=10000.0,
        commission_pct=0.001,
    )

    assert total_commission == pytest.approx(0.1)
    assert normalized[0]["decision_trace_json"]["id"] == "entry_root"
    assert [execution["type"] for execution in normalized[0]["executions"]] == [
        "ENTRY",
        "EXIT",
    ]
    assert normalized[0]["executions"][0]["timestamp"].tzinfo is not None


def test_vector_result_normalization_excludes_end_of_data_trade_from_stats():
    raw_results = {
        "equity_curve": [(datetime(2024, 1, 1, tzinfo=timezone.utc), 10000.0)],
        "analytics_report": {"event_counters": {}, "anomalies": []},
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.4,
        "consistency_score": 0.5,
    }
    normalized_trades = [
        {
            "timestamp_entry": datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
            "timestamp_exit": datetime(2024, 1, 1, 2, tzinfo=timezone.utc),
            "pnl": 100.0,
            "commission": 5.0,
            "exit_reason": "TAKE_PROFIT",
        },
        {
            "timestamp_entry": datetime(2024, 1, 1, 3, tzinfo=timezone.utc),
            "timestamp_exit": datetime(2024, 1, 1, 4, tzinfo=timezone.utc),
            "pnl": -500.0,
            "commission": 10.0,
            "exit_reason": "END_OF_DATA",
        },
    ]

    normalized = _normalize_vector_results(
        raw_results=raw_results,
        normalized_trades=normalized_trades,
        total_commission=15.0,
        initial_balance=10000.0,
    )

    assert normalized["trades"] == 1
    assert normalized["trades_all"] == 2
    assert normalized["excluded_end_of_data_trades"] == 1
    assert normalized["total_pnl"] == pytest.approx(100.0)
    assert normalized["total_commission"] == pytest.approx(5.0)
    assert normalized["equity_curve"] == [
        (1704067200000, 10000.0),
        (1704074400000, 10100.0),
    ]


def test_simulation_router_hides_end_of_data_trades_from_trade_log():
    filtered = _filter_user_visible_trades(
        [
            {"id": 1, "exit_reason": "TAKE_PROFIT"},
            {"id": 2, "exit_reason": "END_OF_DATA"},
            {"id": 3, "exit_reason": "STOP_LOSS"},
        ]
    )

    assert [trade["id"] for trade in filtered] == [1, 3]


def test_fast_vector_handles_container_filters_without_ndarray_fillna_crash():
    strategy = _build_strategy()
    strategy["filters"] = {
        "id": "filter_root",
        "type": "AND",
        "children": [
            {
                "id": "filter_up",
                "type": "value_comparison",
                "params": {
                    "leftOperand": {"source": "candle", "key": "close"},
                    "rightOperand": {"source": "candle", "key": "open"},
                    "operator": "gt",
                },
            }
        ],
    }

    backtester = FastVectorBacktester(
        strategy_json=strategy,
        **_build_depthsight_kwargs(),
    )
    results = backtester.run()

    assert "analytics_report" in results
    assert results["analytics_report"]["event_counters"]["signals_generated_total"] >= 0

import copy

import numpy as np
import pandas as pd
import pytest

from bot_module.fast_vector_backtester import FastVectorBacktester


pytest.importorskip("pandas_ta")


BTCUSDT_OR_STRATEGY = {
    "strategy_name": "VisualBuilderStrategy",
    "signal_source": "internal",
    "symbol": "BTCUSDT",
    "marketType": "FUTURES",
    "min_foundation_weight_threshold": 0,
    "foundation_weights": None,
    "filters": {
        "id": "filters_root",
        "type": "AND",
        "children": [
            {
                "id": "7e55e681-01d0-42b5-a1ef-21e9edffe759",
                "type": "OR",
                "params": {},
                "children": [
                    {
                        "id": "c0f32bfb-5167-434b-9b7b-6abe28fa8bf5",
                        "type": "trading_session",
                        "params": {"session": "london"},
                    },
                    {
                        "id": "6fd05f20-931b-46e2-9057-4e0c1159117c",
                        "type": "volatility_filter",
                        "params": {"indicator": "ATR", "operator": "gt", "value": 1.5},
                    },
                    {
                        "id": "ed2f2cdb-bdf5-43aa-a388-d60e5849a919",
                        "type": "trend_filter",
                        "params": {"indicator": "ADX", "threshold": 25},
                    },
                    {
                        "id": "573a7fff-9129-44ce-acbc-b99787e3d1a1",
                        "type": "natr_filter",
                        "params": {"natr_threshold": 1},
                    },
                    {
                        "id": "792dd20a-1742-4289-aa5e-028df631ca2e",
                        "type": "rel_vol_filter",
                        "params": {"mode": "relative", "rel_vol_threshold": 1.5},
                    },
                ],
            }
        ],
    },
    "entryTrigger": {"type": "on_candle_close", "timeframe": "1m", "params": {}},
    "entryConditions": {
        "id": "entry_root",
        "type": "AND",
        "children": [
            {
                "id": "d614c7ec-9422-4541-897d-220a94a65fc2",
                "type": "OR",
                "params": {},
                "children": [
                    {
                        "id": "4b492a58-adc3-4645-a903-60be02c368bb",
                        "type": "round_level",
                        "params": {
                            "proximity_type": "percentage",
                            "proximity_value": 0.2,
                        },
                    },
                    {
                        "id": "599012a9-5691-4d33-b90c-6bbadeaa9b40",
                        "type": "significant_level",
                        "params": {
                            "level_type": "daily_high",
                            "proximity_type": "percentage",
                            "proximity_value": 0.2,
                        },
                    },
                    {
                        "id": "79584fd0-16d5-42a2-bfa0-fcde4f34a64e",
                        "type": "volume_confirmation",
                        "params": {"multiplier": 1.5},
                    },
                    {
                        "id": "a984ff47-3d4c-456a-8a70-61afb17198a3",
                        "type": "market_activity",
                        "params": {
                            "mode": "percentile",
                            "natr_threshold": 1,
                            "rel_vol_threshold": 1.5,
                        },
                    },
                    {
                        "id": "1db83f46-ff2a-4bb5-8bf6-97138189a440",
                        "type": "trend_direction",
                        "params": {
                            "timeframe": "15m",
                            "required_trend": "LONG",
                            "fast_period": 10,
                            "slow_period": 50,
                            "rsi_period": 14,
                            "rsi_lower_bound": 40,
                            "rsi_upper_bound": 60,
                        },
                    },
                    {
                        "id": "d014bcfb-40c3-479e-840e-e06e12343199",
                        "type": "classic_pattern",
                        "params": {"pattern_name": "bullish_engulfing"},
                    },
                    {
                        "id": "4d7f6984-6993-4221-ad1c-b6fd5b9fe154",
                        "type": "price_consolidation",
                        "params": {"lookback_period": 10, "max_range_atr": 0.8},
                    },
                    {
                        "id": "47c5b3d0-45a5-48c2-b420-ce1412c525cc",
                        "type": "ma_cross_condition",
                        "params": {
                            "fast_period": 9,
                            "slow_period": 21,
                            "ma_type": "ema",
                            "shift": 0,
                            "operator": "crosses_above",
                        },
                    },
                    {
                        "id": "91497123-0169-4a28-90d8-fcc21c5401d2",
                        "type": "rsi_condition",
                        "params": {
                            "period": 14,
                            "operator": "gt",
                            "value": 70,
                            "shift": 0,
                        },
                    },
                    {
                        "id": "0c269b79-97a3-43d4-b16a-1f376d851061",
                        "type": "macd_condition",
                        "params": {
                            "fast_period": 12,
                            "slow_period": 26,
                            "signal_period": 9,
                            "condition": "macd_cross_above_signal",
                            "shift": 0,
                        },
                    },
                    {
                        "id": "eb6bfe80-d7fb-4042-aa73-170ac71703e0",
                        "type": "bollinger_bands_condition",
                        "params": {
                            "period": 20,
                            "std_dev": 2,
                            "source": "close",
                            "location": "above_upper",
                            "shift": 0,
                        },
                    },
                    {
                        "id": "6a123631-574d-41a1-846c-b38619fab838",
                        "type": "stochastic_condition",
                        "params": {
                            "k_period": 14,
                            "d_period": 3,
                            "smoothing": 3,
                            "condition": "k_cross_above_d",
                            "shift": 0,
                        },
                    },
                ],
            }
        ],
    },
    "initialization": {
        "id": "init_long",
        "type": "open_position",
        "params": {
            "direction": "LONG",
            "risk_type": "fixed_usd",
            "risk_value": 100,
            "sl_type": "percent_from_price",
            "sl_value": 0,
            "tp_type": "percent_from_price",
            "tp_value": 2,
            "partial_exits": [],
            "order_type": "MARKET",
        },
    },
    "positionManagement": [
        {
            "id": "dca_grid_management",
            "type": "dca_management",
            "params": {
                "max_safety_orders": 5,
                "volume_multiplier": 1.5,
                "step_type": "percentage",
                "step_value": 2,
                "step_multiplier": 1,
            },
        }
    ],
    "oracle_regime": None,
    "oracle_confidence": 0,
    "use_ml_confirmation": False,
    "breakeven_on_regime_change": False,
    "enabled": True,
}


def _build_btcusdt_data_context() -> dict[str, pd.DataFrame]:
    periods = 240
    index = pd.date_range("2024-01-01 06:30:00", periods=periods, freq="min")

    close = np.full(periods, 50_000.0)
    open_ = np.full(periods, 50_000.0)
    high = np.full(periods, 51_250.0)
    low = np.full(periods, 49_750.0)
    volume = np.full(periods, 1_000.0)

    dca_entry_idx = 31
    close[dca_entry_idx] = 49_000.0
    high[dca_entry_idx] = 50_500.0
    low[dca_entry_idx] = 48_900.0

    tp_after_dca_idx = dca_entry_idx + 1
    open_[tp_after_dca_idx] = 49_000.0
    close[tp_after_dca_idx] = 51_000.0
    high[tp_after_dca_idx] = 52_000.0
    low[tp_after_dca_idx] = 49_000.0

    pattern_prev_idx = 49
    pattern_idx = 50
    open_[pattern_prev_idx] = 50_100.0
    close[pattern_prev_idx] = 49_900.0
    high[pattern_prev_idx] = 50_200.0
    low[pattern_prev_idx] = 49_800.0
    open_[pattern_idx] = 49_850.0
    close[pattern_idx] = 50_200.0
    high[pattern_idx] = 50_300.0
    low[pattern_idx] = 49_800.0

    volume_spike_idx = 60
    volume[volume_spike_idx] = 4_000.0

    wide_range_idx = 100
    high[wide_range_idx] = 130_000.0
    low[wide_range_idx] = 45_000.0

    df_1m = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )

    df_1m["ATR_14"] = 500.0
    df_1m["ADX_14"] = 20.0
    df_1m.loc[index[volume_spike_idx:], "ADX_14"] = 30.0
    df_1m["NATR_14"] = 0.5
    df_1m.loc[index[volume_spike_idx:], "NATR_14"] = 2.0
    df_1m["relative_volume"] = 1.0
    df_1m.loc[index[volume_spike_idx], "relative_volume"] = 2.0
    df_1m["natr"] = 0.5
    df_1m.loc[index[volume_spike_idx], "natr"] = 1.2
    df_1m["is_volume_spike"] = False
    df_1m.loc[index[volume_spike_idx], "is_volume_spike"] = True

    df_1m["SMA_10"] = 50_100.0
    df_1m["SMA_50"] = 50_000.0
    df_1m["RSI_14"] = 50.0
    df_1m.loc[index[volume_spike_idx:], "RSI_14"] = 75.0

    df_1m["EMA_9"] = 49_900.0
    df_1m["EMA_21"] = 50_000.0
    df_1m.loc[index[70:], "EMA_9"] = 50_100.0

    df_1m["MACD_12_26_9"] = -1.0
    df_1m["MACDs_12_26_9"] = 0.0
    df_1m.loc[index[80:], "MACD_12_26_9"] = 1.0
    df_1m["MACDh_12_26_9"] = df_1m["MACD_12_26_9"] - df_1m["MACDs_12_26_9"]

    df_1m["BBL_20_2.0"] = 49_000.0
    df_1m["BBU_20_2.0"] = 51_000.0
    df_1m["BBB_20_2.0"] = 4.0
    df_1m.loc[index[55], "BBU_20_2.0"] = 49_900.0

    df_1m["STOCHk_14_3_3"] = 40.0
    df_1m["STOCHd_14_3_3"] = 50.0
    df_1m.loc[index[90:], "STOCHk_14_3_3"] = 60.0

    df_1d = pd.DataFrame(
        {
            "open": [49_500.0, 50_000.0],
            "high": [50_000.0, 51_000.0],
            "low": [49_000.0, 49_500.0],
            "close": [49_800.0, 50_000.0],
            "volume": [100_000.0, 100_000.0],
        },
        index=pd.to_datetime(["2023-12-31", "2024-01-01"]),
    )

    return {"1m": df_1m, "1d": df_1d}


def _leaf_nodes(root: dict) -> list[dict]:
    if not isinstance(root, dict):
        return []

    if root.get("type") in {"AND", "OR"}:
        nodes: list[dict] = []
        for child in root.get("children", []) or []:
            nodes.extend(_leaf_nodes(child))
        return nodes

    return [root]


def _node_hit_rows(
    backtester: FastVectorBacktester, root: dict, node_results: dict[str, pd.Series]
) -> list[dict]:
    rows = []
    for node in _leaf_nodes(root):
        node_id = str(node["id"])
        mask = node_results.get(node_id)
        hit_count = (
            int(backtester._coerce_mask_series(mask).fillna(False).sum())
            if mask is not None
            else 0
        )
        rows.append({"id": node_id, "type": node["type"], "hits": hit_count})
    return rows


def _print_hit_report(title: str, rows: list[dict]) -> None:
    triggered = [row for row in rows if row["hits"] > 0]
    never = [row for row in rows if row["hits"] == 0]

    print(f"\n{title}")
    print("  triggered at least once:")
    for row in triggered:
        print(f"    {row['type']} [{row['id']}]: {row['hits']}")

    print("  never triggered:")
    if never:
        for row in never:
            print(f"    {row['type']} [{row['id']}]: 0")
    else:
        print("    none")


def test_btcusdt_visual_builder_or_strategy_reports_filter_and_foundation_hits(capsys):
    strategy = copy.deepcopy(BTCUSDT_OR_STRATEGY)
    data_context = _build_btcusdt_data_context()

    backtester = FastVectorBacktester(
        data_context,
        strategy,
        symbol="BTCUSDT",
        strategy_name="VisualBuilderStrategy",
        initial_balance=10_000.0,
        actual_trading_start_dt=data_context["1m"].index[31],
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        exchange_info={
            "tick_size": 0.1,
            "lot_params": {"stepSize": 0.001, "minQty": 0.001, "maxQty": 1000.0},
            "min_notional": 5.0,
        },
    )

    compatibility_report = FastVectorBacktester.analyze_strategy_compatibility(strategy)
    results = backtester.run()

    filter_rows = _node_hit_rows(
        backtester,
        strategy["filters"],
        backtester._filter_node_results,
    )
    foundation_rows = _node_hit_rows(
        backtester,
        strategy["entryConditions"],
        backtester._entry_node_results,
    )
    filter_never = [row for row in filter_rows if row["hits"] == 0]
    foundation_never = [row for row in foundation_rows if row["hits"] == 0]

    with capsys.disabled():
        _print_hit_report("FastVectorBacktester BTCUSDT OR filters", filter_rows)
        _print_hit_report(
            "FastVectorBacktester BTCUSDT OR entry foundations", foundation_rows
        )
        if compatibility_report["unsupported_features"]:
            print("\nCompatibility warnings:")
            for item in compatibility_report["unsupported_features"]:
                print(f"  {item}")

    assert compatibility_report["unsupported_conditions"] == []
    assert compatibility_report["unsupported_position_management"] == []
    assert backtester.symbol == "BTCUSDT"
    assert results["trades_all"] > 0
    assert any(trade["entry_count"] > 1 for trade in backtester.trade_log)
    assert filter_never == []
    assert foundation_never == []

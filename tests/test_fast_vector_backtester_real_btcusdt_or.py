import copy
import os
from pathlib import Path

import pandas as pd
import pytest

from bot_module.fast_vector_backtester import FastVectorBacktester
from tests.test_fast_vector_backtester_visual_builder_or import (
    BTCUSDT_OR_STRATEGY,
    _node_hit_rows,
    _print_hit_report,
)


pytest.importorskip("pandas_ta")


RUN_REAL_ENV = "RUN_REAL_BTCUSDT_FVB"
DEFAULT_DATA_ROOT = Path("data_storage/binance/futures/BTCUSDT")


pytestmark = pytest.mark.skipif(
    os.getenv(RUN_REAL_ENV) != "1",
    reason=f"Set {RUN_REAL_ENV}=1 to run the real BTCUSDT parquet backtest.",
)


def _load_real_btcusdt_context() -> dict[str, pd.DataFrame]:
    data_root = Path(os.getenv("REAL_BTCUSDT_DATA_ROOT", str(DEFAULT_DATA_ROOT)))
    path_1m = data_root / "kline_1m.parquet"
    path_15m = data_root / "kline_15m.parquet"

    if not path_1m.exists() or not path_15m.exists():
        pytest.skip(f"Real BTCUSDT parquet files not found under {data_root}.")

    df_1m = pd.read_parquet(
        path_1m,
        columns=[
            "open",
            "high",
            "low",
            "close",
            "volume",
            "relative_volume",
            "is_volume_spike",
        ],
    )
    df_15m = pd.read_parquet(
        path_15m,
        columns=["open", "high", "low", "close", "volume"],
    )
    return {"1m": df_1m, "15m": df_15m}


def test_real_btcusdt_visual_builder_or_blocks_trigger_at_least_once(capsys):
    strategy = copy.deepcopy(BTCUSDT_OR_STRATEGY)
    data_context = _load_real_btcusdt_context()

    compatibility_report = FastVectorBacktester.analyze_strategy_compatibility(strategy)
    backtester = FastVectorBacktester(
        data_context,
        strategy,
        symbol="BTCUSDT",
        strategy_name="VisualBuilderStrategy",
        initial_balance=10_000.0,
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        exchange_info={
            "tick_size": 0.1,
            "lot_params": {"stepSize": 0.001, "minQty": 0.001, "maxQty": 1000.0},
            "min_notional": 5.0,
        },
    )
    results = backtester.run()

    filter_rows = _node_hit_rows(
        backtester, strategy["filters"], backtester._filter_node_results
    )
    foundation_rows = _node_hit_rows(
        backtester,
        strategy["entryConditions"],
        backtester._entry_node_results,
    )
    filter_never = [row for row in filter_rows if row["hits"] == 0]
    foundation_never = [row for row in foundation_rows if row["hits"] == 0]
    dca_trades = sum(
        1 for trade in backtester.trade_log if trade.get("entry_count", 1) > 1
    )

    with capsys.disabled():
        print("\nLoaded real BTCUSDT data:")
        for timeframe, df in data_context.items():
            print(
                f"  {timeframe} rows: {len(df)} range: {df.index.min()} -> {df.index.max()}"
            )
        _print_hit_report("REAL BTCUSDT OR filters", filter_rows)
        _print_hit_report("REAL BTCUSDT OR entry foundations", foundation_rows)
        print("\nBacktest summary:")
        print(
            "  signals_generated_total:",
            results["analytics_report"]["event_counters"]["signals_generated_total"],
        )
        for key in [
            "trades_all",
            "total_trades",
            "excluded_end_of_data_trades",
            "total_pnl",
            "total_pnl_pct",
            "max_dd",
        ]:
            print(f"  {key}: {results.get(key)}")
        print("  dca_trades:", dca_trades)
        print("  trade_log_len:", len(backtester.trade_log))
        if compatibility_report["unsupported_features"]:
            print("\nCompatibility warnings:")
            for item in compatibility_report["unsupported_features"]:
                print(f"  {item}")

    assert compatibility_report["unsupported_conditions"] == []
    assert compatibility_report["unsupported_position_management"] == []
    assert results["trades_all"] > 0
    assert dca_trades > 0
    assert filter_never == []
    assert foundation_never == []

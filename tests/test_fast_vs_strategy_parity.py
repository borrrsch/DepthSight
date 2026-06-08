import numpy as np
import pandas as pd
import pytest

# pandas_ta<=0.3.14b0 expects numpy.NaN; numpy>=2 removed this alias.
# Keep this in test bootstrap so imports remain stable across environments.
if not hasattr(np, "NaN"):
    np.NaN = np.nan

from bot_module.datatypes import BasePosition
from bot_module.fast_vector_backtester import FastVectorBacktester
from bot_module.strategy import SignalDirection, VisualBuilderStrategy


FAST_SLIPPAGE_PCT = 0.0006
FAST_COMMISSION_PCT = 0.0012


def _build_parity_dataset(rows: int = 400, trend: float = 0.0005) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="1min", tz="UTC")

    open_vals = np.zeros(rows, dtype=float)
    close_vals = np.zeros(rows, dtype=float)
    high_vals = np.zeros(rows, dtype=float)
    low_vals = np.zeros(rows, dtype=float)

    open_vals[0] = 100.0
    for i in range(rows):
        if i > 0:
            open_vals[i] = close_vals[i - 1]
        close_vals[i] = open_vals[i] * (1.0 + trend)
        high_vals[i] = max(open_vals[i], close_vals[i]) * (1.0 + 0.0004)
        low_vals[i] = min(open_vals[i], close_vals[i]) * (1.0 - 0.0002)

    return pd.DataFrame(
        {
            "open": open_vals,
            "high": high_vals,
            "low": low_vals,
            "close": close_vals,
            "volume": 1000.0,
            # Precomputed fields so both engines consume identical inputs.
            "ATR_14": open_vals * 0.001,
            "NATR_14": 1.5,
            "natr": 1.5,
            "relative_volume": 2.0,
            "is_volume_spike": False,
        },
        index=idx,
    )


def _build_parity_strategy(direction: str = "LONG") -> dict:
    operator = "gt" if direction == "LONG" else "lt"
    return {
        "filters": {
            "id": "w_natr",
            "type": "natr_filter",
            "params": {"period": 14, "operator": "gt", "value": 1.0},
        },
        "entryConditions": {
            "id": "w_price_signal",
            "type": "value_comparison",
            "params": {
                "leftOperand": {"source": "candle", "key": "close"},
                "rightOperand": {"source": "candle", "key": "open"},
                "operator": operator,
            },
        },
        "initialization": {
            "id": "init",
            "type": "open_position",
            "params": {
                "direction": direction,
                "sl_type": "percent_from_price",
                "sl_value": 0.1,
                "tp_type": "rr_multiplier",
                "tp_value": 1.5,
            },
        },
    }


def _to_utc_ts(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _compute_fast_style_sl_tp(
    entry_price: float, direction: SignalDirection, init_params: dict
) -> tuple[float, float]:
    sl_value = float(init_params.get("sl_value", 1.0))
    tp_value = float(init_params.get("tp_value", 2.0))

    sl_distance = entry_price * (sl_value / 100.0)
    if direction == SignalDirection.SHORT:
        sl_price = entry_price + sl_distance
        tp_price = entry_price - abs(entry_price - sl_price) * tp_value
    else:
        sl_price = entry_price - sl_distance
        tp_price = entry_price + abs(entry_price - sl_price) * tp_value

    return sl_price, tp_price


async def _run_strategy_replay(
    df_live: pd.DataFrame, strategy_json: dict
) -> list[dict]:
    strategy = VisualBuilderStrategy(
        params={
            "config": strategy_json,
            "enabled": True,
            "min_total_foundation_weight_threshold": 0.0,
            "foundation_weights": {"w_natr": 50.0, "w_price_up": 50.0},
        }
    )
    market_data = {"kline_1m": df_live}
    init_params = strategy_json["initialization"]["params"]

    trade_log: list[dict] = []
    prev_pair_info = None
    pending_signal = None
    position = None

    # Last bar cannot be used for entry (fast engine also requires next candle).
    for i, (ts, row) in enumerate(df_live.iloc[:-1].iterrows()):
        pair_info = {
            **row.to_dict(),
            "symbol": "TESTUSDT",
            "last_price": float(row["close"]),
            "tick_size": 1e-8,
            "candle_timeframe": "1m",
            "timestamp_dt": ts.to_pydatetime(),
            "current_candle_index": i,
            "is_live_mode": False,
        }

        # Execute pending entry on the next candle open (same as fast backtester).
        if pending_signal is not None:
            entry_raw = float(row["open"])
            if pending_signal.direction == SignalDirection.SHORT:
                entry_price = entry_raw * (1.0 - FAST_SLIPPAGE_PCT)
            else:
                entry_price = entry_raw * (1.0 + FAST_SLIPPAGE_PCT)

            sl_price, tp_price = _compute_fast_style_sl_tp(
                entry_price=entry_price,
                direction=pending_signal.direction,
                init_params=init_params,
            )

            position = BasePosition(
                symbol=pending_signal.symbol,
                direction=pending_signal.direction,
                entry_price=entry_price,
                initial_quantity=1.0,
                remaining_quantity=1.0,
                entry_time=ts.to_pydatetime(),
                strategy=pending_signal.strategy_name,
                initial_stop_loss=sl_price,
                current_sl_price=sl_price,
                initial_take_profit=tp_price,
                move_sl_to_be_enabled=False,
                signal_details=pending_signal.details or {},
            )
            position.partial_targets = []
            position.partial_fills = []
            position.executions = []
            pending_signal = None

        closed_this_candle = False
        if position is not None:
            position, exit_details = await strategy.manage_position(
                position, pair_info, market_data, prev_pair_info
            )
            if exit_details:
                exit_raw = float(exit_details.get("exit_price", row["close"]))
                if position.direction == SignalDirection.SHORT:
                    exit_price = exit_raw * (1.0 + FAST_SLIPPAGE_PCT)
                    gross_pnl_pct = (
                        position.entry_price - exit_price
                    ) / position.entry_price
                else:
                    exit_price = exit_raw * (1.0 - FAST_SLIPPAGE_PCT)
                    gross_pnl_pct = (
                        exit_price - position.entry_price
                    ) / position.entry_price

                net_pnl_pct = gross_pnl_pct - (FAST_COMMISSION_PCT * 2.0)
                trade_log.append(
                    {
                        "entry_time": position.entry_time,
                        "exit_time": ts.to_pydatetime(),
                        "direction": position.direction.name,
                        "exit_reason": str(exit_details.get("reason", "UNKNOWN")),
                        "pnl_pct": float(net_pnl_pct),
                    }
                )
                position = None
                closed_this_candle = True

        # Fast engine skips entry signals on a candle where a position was just closed.
        if position is None and pending_signal is None and not closed_this_candle:
            signal, _, _ = await strategy.check_signal(
                pair_info,
                market_data,
                prev_pair_info,
                analysis_level="second_bar_trigger",
            )
            if signal is not None:
                pending_signal = signal

        prev_pair_info = pair_info

    return trade_log


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "direction, trend",
    [
        ("LONG", 0.0005),
        ("SHORT", -0.0005),
    ],
)
async def test_fast_vector_backtester_matches_strategy_replay_baseline(
    direction, trend
):
    strategy_json = _build_parity_strategy(direction=direction)
    df_live = _build_parity_dataset(trend=trend)
    df_fast = df_live.copy()
    df_fast.index = df_fast.index.tz_convert(None)

    fast_bt = FastVectorBacktester(
        df_fast,
        strategy_json,
        execution_config={
            "commission_pct": FAST_COMMISSION_PCT,
            "slippage_pct": FAST_SLIPPAGE_PCT,
        },
        risk_params={
            "daily_max_loss_pct": 100.0,  # 100%
            "max_consecutive_losses": 1000,
            "max_drawdown_pct": 100.0,
        },
    )
    fast_bt.run()
    strategy_trades = await _run_strategy_replay(df_live, strategy_json)

    assert len(fast_bt.trade_log) > 0
    assert len(strategy_trades) > 0
    assert abs(len(fast_bt.trade_log) - len(strategy_trades)) <= 1

    compare_count = min(len(fast_bt.trade_log), len(strategy_trades))
    for i in range(compare_count):
        fast_trade = fast_bt.trade_log[i]
        strategy_trade = strategy_trades[i]

        assert fast_trade["direction"] == strategy_trade["direction"]
        assert fast_trade["exit_reason"] == strategy_trade["exit_reason"]
        assert _to_utc_ts(fast_trade["entry_time"]) == _to_utc_ts(
            strategy_trade["entry_time"]
        )
        assert _to_utc_ts(fast_trade["exit_time"]) == _to_utc_ts(
            strategy_trade["exit_time"]
        )
        assert float(fast_trade["pnl_pct"]) == pytest.approx(
            strategy_trade["pnl_pct"], abs=1e-12
        )

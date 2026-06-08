# tests/test_backtester_scenarios.py

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock
import math

from bot_module.depthsight_backtester import DepthSightBacktester
from bot_module.strategy import (
    StrategySignal,
    SignalDirection,
    OrderMode,
    PartialTarget,
    BaseStrategy,
)
from bot_module import strategy as strategy_module


def create_base_kline_data(num_rows=100, start_price=100.0, trend=0.1):
    data = {
        "open": np.full(num_rows, start_price) + np.arange(num_rows) * trend,
        "high": np.full(num_rows, start_price + 0.5) + np.arange(num_rows) * trend,
        "low": np.full(num_rows, start_price - 0.5) + np.arange(num_rows) * trend,
        "close": np.full(num_rows, start_price) + np.arange(num_rows) * trend,
        "volume": np.full(num_rows, 100),
    }
    df = pd.DataFrame(data)
    df["high"] = df[["open", "close"]].max(axis=1) + 0.5
    df["low"] = df[["open", "close"]].min(axis=1) - 0.5
    df.index = pd.to_datetime(
        pd.date_range(start="2023-01-01", periods=num_rows, freq="1min", tz="UTC")
    )
    return df


@pytest.fixture
def base_backtester_setup(tmp_path, mocker):
    class MockStrategy(BaseStrategy):
        NAME = "MockStrategy"

    mocker.patch.dict(strategy_module.STRATEGIES, {"MockStrategy": MockStrategy})

    historical_data = {"kline_1m": create_base_kline_data()}
    mock_config = MagicMock()
    mock_config.FOUNDATION_WEIGHTS = {"market_activity": 100.0}
    mock_config.MIN_TOTAL_FOUNDATION_WEIGHT_THRESHOLD = 50.0
    mock_config.BACKTEST_MIN_STOP_DISTANCE_PCT = 0.0005
    # Increasing the limit so that the commission doesn't block the trade
    mock_config.BACKTEST_MAX_POSITION_SIZE_PCT_BALANCE = 1.95
    mock_config.STRATEGY_SYMBOL_PERFORMANCE_ADJUSTMENT_ENABLED = False
    mock_config.SYMBOL_COOLDOWN_SECONDS = 300.0
    mock_config.BE_SL_OFFSET_TICKS = 1
    mock_config.ALLOW_SHORT_POSITIONS = True

    with patch("bot_module.depthsight_backtester.ta", autospec=True) as mock_ta:
        kline_df = historical_data["kline_1m"]
        mock_ta.atr.return_value = pd.Series(
            np.full(len(kline_df), 1.0), index=kline_df.index
        )
        macd_df = pd.DataFrame(
            {"MACD_12_26_9": 0, "MACDs_12_26_9": 0, "MACDh_12_26_9": 0},
            index=kline_df.index,
        )
        mock_ta.macd.return_value = macd_df
        bbands_df = pd.DataFrame(
            {"BBU_20_2.0_2.0": 0, "BBM_20_2.0_2.0": 0, "BBL_20_2.0_2.0": 0},
            index=kline_df.index,
        )
        mock_ta.bbands.return_value = bbands_df
        stoch_df = pd.DataFrame(
            {"STOCHk_14_3_3": 50, "STOCHd_14_3_3": 50}, index=kline_df.index
        )
        mock_ta.stoch.return_value = stoch_df
        adx_df = pd.DataFrame({"ADX_14": 25}, index=kline_df.index)
        mock_ta.adx.return_value = adx_df

        backtester = DepthSightBacktester(
            strategy_name="MockStrategy",
            symbol="TESTUSDT",
            params={},
            historical_data=historical_data,
            initial_balance=20000.0,
            min_trades_required=1,
            risk_params={
                "risk_pct_per_trade": 0.01,
                "max_stop_distance_pct": 0.05,
                "daily_max_loss_pct": 0.10,
            },
            backtest_risk_params={},
            execution_config={"commission_pct": 0.001, "slippage_pct": 0.0},
            strategy_defaults={"MockStrategy": {"candle_timeframe": "1m"}},
            ml_training_config={},
            ml_sim_log_path=None,
            exchange_info={
                "tick_size": 0.01,
                "lot_params": {"stepSize": 0.001},
                "min_notional": 10.0,
            },
            _config_override=mock_config,
            l2_storage_path=None,
        )

        backtester.strategy_instance.check_signal = AsyncMock(
            return_value=(None, 0.0, {})
        )

        # The assess_signal method returns (is_approved, size, risk_usd, reason)
        with patch(
            "bot_module.depthsight_backtester.RiskManager.assess_signal",
            side_effect=lambda signal, *args, **kwargs: (True, 1.0, 100.0, None),
        ):
            yield backtester


def test_limit_order_fill_and_win(base_backtester_setup):
    bt = base_backtester_setup
    signal_fire_idx = 60
    limit_entry_price = 101.0

    test_signal = StrategySignal(
        "MockStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        mode=OrderMode.LIMIT_RETEST,
        entry_price=limit_entry_price,
        trigger_price=102.0,
        stop_loss=100.0,
        take_profit=103.0,
    )
    # Removing the analysis_level check
    bt.strategy_instance.check_signal.side_effect = (
        lambda pi, md, prev, analysis_level=None: (
            (test_signal, 100.0, {})
            if pi["current_candle_index"] == signal_fire_idx
            else (None, 0.0, {})
        )
    )

    bt.klines.loc[bt.klines.index[signal_fire_idx + 2], "open"] = (
        limit_entry_price + 0.5
    )
    bt.klines.loc[bt.klines.index[signal_fire_idx + 2], "low"] = limit_entry_price - 0.5
    bt.klines.loc[bt.klines.index[signal_fire_idx + 4], "high"] = 105.0
    bt.kline_data_array = bt.klines[list(bt.kline_index_map.keys())].to_numpy()

    results = bt.run()

    assert results["trades"] == 1
    assert results["wins"] == 1
    trade = bt.trade_log[0]
    assert math.isclose(trade["entry_price"], limit_entry_price)
    assert trade["exit_reason"] == "TAKE_PROFIT"


def test_partial_take_profits_and_be(base_backtester_setup):
    bt = base_backtester_setup
    signal_fire_idx = 60

    test_signal = StrategySignal(
        "MockStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        mode=OrderMode.MARKET,
        trigger_price=102.0,
        stop_loss=101.0,
        take_profit=104.0,
        partial_targets=[PartialTarget(price=103.0, fraction=0.5)],
        move_sl_to_be_on_first_tp=True,
    )
    mock_foundations_result = ({"market_activity": True}, [])
    bt.strategy_instance.check_foundations = MagicMock(
        return_value=mock_foundations_result
    )
    bt.strategy_instance.check_signal.side_effect = (
        lambda pi, md, prev, analysis_level=None: (
            (test_signal, 100.0, {})
            if pi["current_candle_index"] == signal_fire_idx
            else (None, 0.0, {})
        )
    )

    bt.klines.loc[bt.klines.index[signal_fire_idx], "close"] = 102.0

    # Candle between entry and first TP. Ensuring it doesn't trigger anything.
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "high"] = 102.5
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "low"] = 101.5

    # Candle where the first and only partial TP triggers and SL is moved to BE
    bt.klines.loc[bt.klines.index[signal_fire_idx + 2], "high"] = 103.1
    bt.klines.loc[bt.klines.index[signal_fire_idx + 2], "low"] = 102.5

    # Candle after partial TP - here the SL change to BE is not yet applied to the check
    # (since SL is checked BEFORE the manage_position call)
    bt.klines.loc[bt.klines.index[signal_fire_idx + 3], "low"] = (
        102.1  # Above BE SL (102.02)
    )
    bt.klines.loc[bt.klines.index[signal_fire_idx + 3], "high"] = 102.5

    # Candle where SL at BE ACTUALLY triggers (102.02)
    # By this point is_stop_at_be is already True from the previous iteration
    bt.klines.loc[bt.klines.index[signal_fire_idx + 4], "low"] = (
        101.9  # Below BE SL (102.02)
    )
    bt.klines.loc[bt.klines.index[signal_fire_idx + 4], "high"] = 102.3

    bt.kline_data_array = bt.klines[list(bt.kline_index_map.keys())].to_numpy()

    results = bt.run()

    assert results["trades"] == 1
    # PnL can be around zero or slightly negative due to commissions,
    # since we closed 50% with profit ~1.0, and the remaining 50% at BE
    # The main thing is that the partial TP + BE mechanism worked
    trade = bt.trade_log[0]
    assert trade["num_partial_tp_hits"] == 1
    assert trade["moved_to_be"] is True
    assert trade["exit_reason"] == "SL_AT_BE"


def test_short_position_win(base_backtester_setup):
    bt = base_backtester_setup
    signal_fire_idx = 60

    test_signal = StrategySignal(
        "MockStrategy",
        "TESTUSDT",
        SignalDirection.SHORT,
        mode=OrderMode.MARKET,
        trigger_price=102.0,
        stop_loss=103.0,
        take_profit=100.0,
    )
    mock_foundations_result = ({"market_activity": True}, [])
    bt.strategy_instance.check_foundations = MagicMock(
        return_value=mock_foundations_result
    )
    bt.strategy_instance.check_signal.side_effect = (
        lambda pi, md, prev, analysis_level=None: (
            (test_signal, 100.0, {})
            if pi["current_candle_index"] == signal_fire_idx
            else (None, 0.0, {})
        )
    )

    bt.klines.loc[bt.klines.index[signal_fire_idx], "close"] = 102.0
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "high"] = 102.8
    bt.klines.loc[bt.klines.index[signal_fire_idx + 2], "high"] = 100.5
    bt.klines.loc[bt.klines.index[signal_fire_idx + 2], "low"] = 99.9

    bt.kline_data_array = bt.klines[list(bt.kline_index_map.keys())].to_numpy()

    results = bt.run()

    assert results["trades"] == 1
    assert results["wins"] == 1
    assert results["total_pnl"] > 0
    assert bt.trade_log[0]["direction"] == "SHORT"
    assert bt.trade_log[0]["exit_reason"] == "TAKE_PROFIT"

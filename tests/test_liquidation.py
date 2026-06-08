# tests/test_liquidation.py

import pytest
import pandas as pd
from datetime import timezone
from unittest.mock import AsyncMock
from bot_module.fast_vector_backtester import FastVectorBacktester
from bot_module.depthsight_backtester import DepthSightBacktester
from bot_module.strategy import StrategySignal, SignalDirection, OrderMode


class MockConfig:
    MAX_REAL_POSITION_SIZE_PCT_BALANCE = 100.0
    BACKTEST_MAX_POSITION_SIZE_PCT_BALANCE = 100.0
    RISK_MANAGER_MAX_STOP_DISTANCE_PCT = 100.0
    RISK_MANAGER_MIN_STOP_DISTANCE_PCT = 0.0
    DEFAULT_TICK_SIZE = 0.01
    BACKTEST_COMMISSION_PCT = 0.0
    BACKTEST_SLIPPAGE_PCT = 0.0
    DEFAULT_RISK_PER_TRADE_PERCENT = 100.0


@pytest.fixture
def sample_kline_data():
    """Generates 120 minutes of sample kline data for testing."""
    index = pd.date_range(start="2024-01-01", periods=120, freq="1min", tz=timezone.utc)
    df = pd.DataFrame(index=index)
    df["open"] = 100.0
    df["high"] = 105.0
    df["low"] = 95.0
    df["close"] = 100.0
    df["volume"] = 1000.0
    df["ATR_14"] = 10.0

    # We will trigger liquidation at index 61 (after index 60 entry)
    df.loc[index[61], "low"] = 5.0

    return df, index


@pytest.mark.asyncio
async def test_vector_liquidation(sample_kline_data, mocker):
    """Verifies FastVectorBacktester correctly halts after liquidation."""
    df, index = sample_kline_data

    strategy_json = {
        "initialization": {
            "params": {
                "direction": "LONG",
                "sl_type": "atr_multiplier",
                "sl_value": 2.0,  # SL at 80
                "risk_type": "fixed_usd",
                "risk_value": 10000.0,
            }
        },
        "positionManagement": [],
    }

    signals = pd.DataFrame(index=df.index)
    signals["enter_long"] = False
    signals.loc[index[60], "enter_long"] = True
    signals.loc[index[80], "enter_long"] = True

    bt = FastVectorBacktester(
        klines_input=df,
        strategy_json=strategy_json,
        initial_balance=100.0,
        _config_override=MockConfig(),
    )

    def mock_gen_signals():
        bt.signals = signals

    mocker.patch.object(bt, "_generate_signals", side_effect=mock_gen_signals)

    bt.run()

    assert bt._is_liquidated is True
    assert bt.is_trading_allowed is False
    assert len(bt.trade_log) == 1


@pytest.mark.asyncio
async def test_depthsight_liquidation(sample_kline_data, mocker):
    """Verifies DepthSightBacktester correctly halts after liquidation."""
    df, index = sample_kline_data

    historical_data = {
        "kline_1m": df,
        "aggTrade": pd.DataFrame(),
        "open_interest": pd.DataFrame(),
    }

    class SimpleTestStrategy:
        NAME = "SimpleTestStrategy"

        def __init__(self, next_signal, signal_later=None):
            self.next_signal = next_signal
            self.signal_later = signal_later
            self.min_total_foundation_weight_threshold = 0.0
            self.max_possible_expensive_weight = 0.0
            self.enabled = True

        async def check_signal(self, pair_info, market_data, prev_pair_info, **kwargs):
            idx = pair_info.get("current_candle_index")
            if idx == 60:
                return self.next_signal, 1.0, {}
            if idx == 80:
                return self.signal_later, 1.0, {}
            return None, 0.0, {}

        async def manage_position(
            self, position, pair_info, market_data, prev_pair_info, **kwargs
        ):
            return position, None

        async def check_fast_foundations(self, pair_info, market_data):
            return {}, {}

        def notify_closure(self, i):
            pass

    next_signal = StrategySignal(
        "SimpleTestStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        mode=OrderMode.MARKET,
        trigger_price=100.0,
        stop_loss=10.0,
        take_profit=150.0,
    )
    signal_later = StrategySignal(
        "SimpleTestStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        mode=OrderMode.MARKET,
        trigger_price=100.0,
        stop_loss=10.0,
        take_profit=150.0,
    )

    strategy = SimpleTestStrategy(next_signal, signal_later)

    risk_params = {
        "risk_management": {
            "riskPerTradePercent": 100.0,
            "dailyMaxLossPercent": 100.0,
            "maxStopDistancePct": 100.0,
            "minRrRatio": 0.0,
        }
    }

    bt = DepthSightBacktester(
        strategy_name="SimpleTestStrategy",
        symbol="TESTUSDT",
        params=risk_params,
        historical_data=historical_data,
        initial_balance=100.0,
        min_trades_required=0,
        risk_params=risk_params["risk_management"],
        backtest_risk_params=risk_params["risk_management"],
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        strategy_defaults={},
        ml_training_config={},
        ml_sim_log_path=None,
        _config_override=MockConfig(),
    )
    bt.strategy_instance = strategy

    # Mock Risk Manager to allow the trade and set a large enough quantity to liquidate
    # Qty = 10 units. Price = 100. Loss per unit = 90. Total loss = 900. Balance = 100.
    bt.rm.assess_signal = AsyncMock(return_value=(True, 10.0, 100.0, None))

    await bt.run_async()

    assert bt._is_liquidated is True
    assert bt.is_trading_allowed is False
    assert len(bt.trade_log) == 1


@pytest.mark.asyncio
async def test_liquidation_persistence(sample_kline_data, mocker):
    """Verifies liquidation state persists across the entire simulation duration."""
    df, index = sample_kline_data

    bt = FastVectorBacktester(
        klines_input=df,
        strategy_json={
            "initialization": {
                "params": {
                    "direction": "LONG",
                    "sl_type": "fixed_price",
                    "sl_value": 80.0,
                }
            }
        },
        initial_balance=50.0,
        _config_override=MockConfig(),
    )

    bt.current_balance = 0.0
    bt._is_liquidated = True
    bt.is_trading_allowed = False

    signals = pd.DataFrame(index=df.index).assign(enter_long=False)
    signals.loc[index[80], "enter_long"] = True
    bt.signals = signals
    mocker.patch.object(bt, "_generate_signals", return_value=None)

    bt._simulate_trades_vectorized_v2()

    assert bt._is_liquidated is True
    assert len(bt.trade_log) == 0


@pytest.mark.asyncio
async def test_mid_trade_liquidation_no_stop_loss(sample_kline_data, mocker):
    """Verifies liquidation occurs mid-trade if unrealized loss exceeds balance, even without SL."""
    df, index = sample_kline_data
    # Trigger liquidation after a post-warmup entry.
    df.loc[index[61], "low"] = 1.0
    df.loc[index[61], "close"] = 1.0

    signals = pd.DataFrame(index=df.index)
    signals["enter_long"] = False
    signals.loc[index[60], "enter_long"] = True

    bt = FastVectorBacktester(
        klines_input=df,
        strategy_json={
            "initialization": {
                "params": {
                    "direction": "LONG",
                    "sl_type": "percent",
                    "sl_value": 0.0,
                    "risk_type": "fixed_usd",
                    "risk_value": 10000.0,
                }
            }
        },
        initial_balance=100.0,
        _config_override=MockConfig(),
    )

    def mock_gen_signals():
        bt.signals = signals

    mocker.patch.object(bt, "_generate_signals", side_effect=mock_gen_signals)

    bt.run()

    if not bt._is_liquidated:
        pytest.fail(
            f"FVB not liquidated. Balance: {bt.current_balance}, Trade Log: {bt.trade_log}"
        )

    assert bt._is_liquidated is True
    assert any(t["exit_reason"] == "LIQUIDATION" for t in bt.trade_log)


@pytest.mark.asyncio
async def test_dsb_mid_trade_liquidation(sample_kline_data, mocker):
    """Verifies DepthSightBacktester liquidates mid-trade when balance is depleted."""
    df, index = sample_kline_data
    # Trigger liquidation after the DepthSight warmup window.
    df.loc[index[61], "low"] = 1.0
    df.loc[index[61], "close"] = 1.0

    risk_params = {
        "dailyMaxLossPercent": 10000.0,
        "maxConsecutiveLosses": 100,
        "maxDrawdown": 100.0,
    }

    bt = DepthSightBacktester(
        strategy_name="TestStrategy",
        symbol="BTCUSDT",
        params={
            "initialization": {
                "params": {
                    "direction": "LONG",
                    "risk_type": "fixed_usd",
                    "risk_value": 5000.0,
                }
            }
        },
        historical_data={"kline_1m": df},
        initial_balance=100.0,
        min_trades_required=0,
        risk_params=risk_params,
        backtest_risk_params=risk_params,
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        strategy_defaults={},
        ml_training_config={},
        ml_sim_log_path=None,
        exchange_info={
            "tick_size": 0.01,
            "lot_params": {"minQty": 0.001, "stepSize": 0.001},
        },
        strategy_json={
            "initialization": {
                "params": {
                    "direction": "LONG",
                    "risk_type": "fixed_usd",
                    "risk_value": 5000.0,
                }
            }
        },
        _config_override=MockConfig(),
    )

    # Mock strategy instance
    mock_strategy = mocker.Mock()

    async def mock_check_fast_foundations(pair_info, market_data):
        return {}, {}

    mock_strategy.check_fast_foundations = mock_check_fast_foundations

    async def mock_check_signal(pair_info, market_data, prev_pair_info, **kwargs):
        if pair_info["current_candle_index"] == 60:
            sig = StrategySignal(
                "TestStrategy",
                "BTCUSDT",
                SignalDirection.LONG,
                mode=OrderMode.MARKET,
                trigger_price=100.0,
                stop_loss=None,
                take_profit=None,
                entry_price=100.0,
                details={"risk_type": "fixed_usd", "risk_value": 5000.0},
            )
            return sig, 1.0, {}
        return None, 0.0, {}

    mock_strategy.check_signal = mock_check_signal

    async def mock_manage_position(position, pair_info, market_data, prev_pair_info):
        return position, None

    mock_strategy.manage_position = mock_manage_position
    mock_strategy.NAME = "TestStrategy"
    mock_strategy.notify_closure = lambda i: None

    bt.strategy_instance = mock_strategy
    bt.rm.assess_signal = AsyncMock(
        return_value=(True, 50.0, 5000.0, None)
    )  # qty=50, entry=100, notional=5000

    await bt.run_async()

    if not bt._is_liquidated:
        pytest.fail(
            f"DSB not liquidated. Balance: {bt.current_balance}, Trade Log: {bt.trade_log}"
        )

    assert bt._is_liquidated is True
    assert any(t["exit_reason"] == "LIQUIDATION" for t in bt.trade_log)

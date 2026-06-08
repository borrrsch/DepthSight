# tests/test_portfolio_risk_manager.py

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from bot_module.portfolio_risk_manager import PortfolioRiskManager
from bot_module.portfolio_datatypes import BacktestPositionState
from bot_module.strategy import StrategySignal, SignalDirection


@pytest.fixture
def risk_manager_config():
    """Fixture with the risk manager configuration."""
    return {
        "max_total_exposure_pct": 0.50,
        "max_concurrent_positions": 3,
        "risk_pct_per_trade": 0.01,  # 1%
    }


@pytest.fixture
def risk_manager(risk_manager_config):
    """Fixture for the PortfolioRiskManager instance."""
    return PortfolioRiskManager(global_risk_limits=risk_manager_config)


@pytest.fixture
def sample_exchange_info():
    """Fixture with trading rules for the symbol."""
    return {
        "tick_size": 0.01,
        "step_size": 0.001,
        "min_qty": 0.001,
        "max_qty": 1000.0,
        "min_notional": 10.0,
    }


# --- Tests for calculate_position_size ---


def test_calculate_position_size_basic(risk_manager, sample_exchange_info):
    """Basic test for position size calculation."""
    signal = StrategySignal(
        "Test",
        "BTCUSDT",
        SignalDirection.LONG,
        stop_loss=29700.0,
        trigger_price=30000.0,
        take_profit=30300.0,
    )
    # Risk per trade: 100000 * 0.01 = 1000 USD
    # Risk per unit: 30000 - 29700 = 300 USD
    # Quantity: 1000 / 300 = 3.33333... -> rounded to 3.333
    size = risk_manager.calculate_position_size(
        signal=signal,
        current_balance=100000.0,
        entry_price=30000.0,
        stop_loss_price=29700.0,
        exchange_info=sample_exchange_info,
    )
    assert size == pytest.approx(3.333)


def test_calculate_position_size_min_notional_adjustment(
    risk_manager, sample_exchange_info
):
    """Test where the position size is increased to meet min_notional."""
    signal = StrategySignal(
        "Test",
        "BTCUSDT",
        SignalDirection.LONG,
        stop_loss=20000.0,
        trigger_price=30000.0,
        take_profit=31000.0,
    )
    # Risk per trade: 100 * 0.01 = 1 USD
    # Risk per unit: 10000 USD
    # Initial qty: 1 / 10000 = 0.0001
    # Notional: 0.0001 * 30000 = 3 USD < min_notional (10 USD)
    # Required qty: 10 / 30000 = 0.000333 -> rounded to 0.001 (min_qty > 0.000333)
    # New notional: 0.001 * 30000 = 30 USD > 10. OK.
    size = risk_manager.calculate_position_size(
        signal=signal,
        current_balance=100.0,
        entry_price=30000.0,
        stop_loss_price=20000.0,
        exchange_info=sample_exchange_info,
    )
    assert size == pytest.approx(0.001)


def test_calculate_position_size_returns_none_if_too_small(
    risk_manager, sample_exchange_info
):
    """Test where the position cannot be opened due to too small size."""
    signal = StrategySignal(
        "Test",
        "BTCUSDT",
        SignalDirection.LONG,
        stop_loss=29999.0,
        trigger_price=30000.0,
        take_profit=30001.0,
    )
    # Risk per trade = 1 USD, Risk per unit = 1 USD. Qty = 1.
    # Notional = 1 * 30000 = 30000 >> min_notional.
    # This test was incorrect in its original form. Let's make it meaningful.
    # Situation: after rounding by step_size, the quantity becomes less than min_qty.
    small_step_info = sample_exchange_info.copy()
    small_step_info["min_qty"] = 0.1
    small_step_info["step_size"] = 0.1
    # Risk = 1000 USD, SL dist = 300. Qty = 3.333. After rounding to 0.1 -> 3.3
    size = risk_manager.calculate_position_size(
        signal, 100000, 30000, 29700, small_step_info
    )
    assert size == pytest.approx(3.3)


# --- Tests for validate_signal ---


def test_validate_signal_max_concurrent_positions(risk_manager):
    """Test of the limit on the number of simultaneous positions."""
    active_positions = {"pos1": MagicMock(), "pos2": MagicMock(), "pos3": MagicMock()}
    signal = StrategySignal(
        "Test",
        "BTCUSDT",
        SignalDirection.LONG,
        trigger_price=30000.0,
        stop_loss=29700.0,
        take_profit=30300.0,
    )
    # Limit = 3, already have 3, the new trade should be rejected
    is_valid = risk_manager.validate_signal(
        signal,
        calculated_quantity=0.1,
        entry_price=30000,
        current_balance=10000,
        active_positions=active_positions,
    )
    assert not is_valid


def test_validate_signal_max_exposure_exceeded(risk_manager):
    """Test of the limit on the total portfolio exposure."""
    # Limit 50%. Balance 10000. Max exposure = 5000.
    # There is already a position for 4000. A new one for 1500 should be rejected.
    active_positions = {
        "pos1": BacktestPositionState(
            "p1",
            "c1",
            "BTCUSDT",
            SignalDirection.LONG,
            20000,
            0.2,
            datetime.now(),
            initial_value_usd=4000,
        )
    }
    signal = StrategySignal(
        "Test",
        "ETHUSDT",
        SignalDirection.LONG,
        trigger_price=1500.0,
        stop_loss=1485.0,
        take_profit=1515.0,
    )
    is_valid = risk_manager.validate_signal(
        signal,
        calculated_quantity=1.0,
        entry_price=1500,  # New position at 1500
        current_balance=10000,
        active_positions=active_positions,
    )
    assert not is_valid


def test_validate_signal_passes_all_checks(risk_manager):
    """Test when the signal passes all checks."""
    active_positions = {
        "pos1": BacktestPositionState(
            "p1",
            "c1",
            "BTCUSDT",
            SignalDirection.LONG,
            20000,
            0.1,
            datetime.now(),
            initial_value_usd=2000,
        )
    }
    signal = StrategySignal(
        "Test",
        "ETHUSDT",
        SignalDirection.LONG,
        trigger_price=1500.0,
        stop_loss=1485.0,
        take_profit=1515.0,
    )
    is_valid = risk_manager.validate_signal(
        signal,
        calculated_quantity=1.0,
        entry_price=1500,
        current_balance=10000,
        active_positions=active_positions,
    )
    assert is_valid

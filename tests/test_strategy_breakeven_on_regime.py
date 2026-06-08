from bot_module.strategy import BaseStrategy
from bot_module.datatypes import BasePosition, SignalDirection


class TestStrategyBreakevenOnRegime:
    def test_strategy_init_param(self):
        """Check that the parameter is initialized correctly."""
        # Case 1: Default is False
        strategy = BaseStrategy(params={})
        assert strategy.breakeven_on_regime_change is False

        # Case 2: Explicitly True
        strategy_true = BaseStrategy(params={"breakeven_on_regime_change": True})
        assert strategy_true.breakeven_on_regime_change is True

    def test_check_on_screener_update_no_change(self):
        """Check that nothing happens if the mode has not changed or the flag is disabled."""
        strategy = BaseStrategy(params={"breakeven_on_regime_change": True})

        position = BasePosition(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            entry_price=50000,
            initial_quantity=1,
            remaining_quantity=1,
            entry_time=1000,
            strategy="BaseStrategy",
            initial_stop_loss=49000,
            current_sl_price=49000,
            initial_take_profit=51000,
        )
        position.signal_details = {"oracle_regime": 1}

        # Screener update with the same mode
        screener_data = {"symbol": "BTCUSDT", "oracle_regime": 1, "close": 50500}

        action, price = strategy.check_on_screener_update(position, screener_data)
        assert action == "NONE"
        assert price is None

    def test_check_on_screener_update_trigger_winning(self):
        """Check break-even transfer triggering when the mode changes (at a profit)."""
        strategy = BaseStrategy(params={"breakeven_on_regime_change": True})

        position = BasePosition(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            entry_price=50000,
            initial_quantity=1,
            remaining_quantity=1,
            entry_time=1000,
            strategy="BaseStrategy",
            initial_stop_loss=49000,
            current_sl_price=49000,
            initial_take_profit=51000,
        )
        position.signal_details = {"oracle_regime": 1}

        # Mode changed to 0, price is above entry (50500 > 50000)
        screener_data = {"symbol": "BTCUSDT", "oracle_regime": 0, "close": 50500}

        action, price = strategy.check_on_screener_update(position, screener_data)

        assert action == "MOVE_SL"
        assert price == 50000.0

    def test_check_on_screener_update_trigger_losing(self):
        """Check position closure triggering when the mode changes (at a loss)."""
        strategy = BaseStrategy(params={"breakeven_on_regime_change": True})

        position = BasePosition(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            entry_price=50000,
            initial_quantity=1,
            remaining_quantity=1,
            entry_time=1000,
            strategy="BaseStrategy",
            initial_stop_loss=49000,
            current_sl_price=49000,
            initial_take_profit=51000,
        )
        position.signal_details = {"oracle_regime": 1}

        # Mode changed to 0, price is below entry (49500 < 50000)
        screener_data = {"symbol": "BTCUSDT", "oracle_regime": 0, "close": 49500}

        action, price = strategy.check_on_screener_update(position, screener_data)

        assert action == "CLOSE_POSITION"
        assert price is None

    def test_check_on_screener_update_disabled(self):
        """Check that when the flag is disabled, the mode change is ignored."""
        strategy = BaseStrategy(params={"breakeven_on_regime_change": False})

        position = BasePosition(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            entry_price=50000,
            initial_quantity=1,
            remaining_quantity=1,
            entry_time=1000,
            strategy="BaseStrategy",
            initial_stop_loss=49000,
            current_sl_price=49000,
            initial_take_profit=51000,
        )
        position.signal_details = {"oracle_regime": 1}

        screener_data = {"symbol": "BTCUSDT", "oracle_regime": 0, "close": 50500}

        action, price = strategy.check_on_screener_update(position, screener_data)
        assert action == "NONE"
        assert price is None

    def test_check_on_screener_update_already_at_be(self):
        """Check that if the stop is already at BE or better, we do not move it."""
        strategy = BaseStrategy(params={"breakeven_on_regime_change": True})

        position = BasePosition(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            entry_price=50000,
            initial_quantity=1,
            remaining_quantity=1,
            entry_time=1000,
            strategy="BaseStrategy",
            initial_stop_loss=50100,  # Already in profit
            current_sl_price=50100,
            initial_take_profit=52000,
            is_stop_at_be=True,  # Flag is already set
        )
        position.signal_details = {"oracle_regime": 1}

        screener_data = {"symbol": "BTCUSDT", "oracle_regime": 0, "close": 50500}

        action, price = strategy.check_on_screener_update(position, screener_data)
        assert action == "NONE"
        assert price is None

import numpy as np

# pandas_ta<=0.3.14b0 expects numpy.NaN; numpy>=2 removed this alias.
if not hasattr(np, "NaN"):
    np.NaN = np.nan

from bot_module.controller import ActivePositionMap, LivePosition
from bot_module.strategy import SignalDirection


def _position(symbol: str, market_type: str) -> LivePosition:
    return LivePosition(
        symbol=symbol,
        direction=SignalDirection.LONG,
        entry_price=100.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=1.0,
        strategy="test",
        initial_stop_loss=90.0,
        initial_take_profit=120.0,
        current_sl_price=90.0,
        status="OPEN",
        market_type=market_type,
    )


def test_active_position_map_keeps_spot_and_futures_same_symbol_independent():
    positions = ActivePositionMap()
    futures_position = _position("BTCUSDT", "futures_usdtm")
    spot_position = _position("BTCUSDT", "spot")

    positions[futures_position.symbol] = futures_position
    positions[spot_position.symbol] = spot_position

    assert len(positions) == 2
    assert positions.get_by_symbol("BTCUSDT", "futures_usdtm") is futures_position
    assert positions.get_by_symbol("BTCUSDT", "spot") is spot_position
    assert positions.get("BTCUSDT") is None


def test_active_position_map_legacy_symbol_lookup_when_unambiguous():
    positions = ActivePositionMap()
    futures_position = _position("ETHUSDT", "futures")

    positions["ETHUSDT"] = futures_position

    assert "ETHUSDT" in positions
    assert positions["ETHUSDT"] is futures_position
    assert positions.get("ETHUSDT") is futures_position

# tests/test_execution_simulator.py
import pytest
from bot_module.execution_simulator import simulate_market_order_execution, FillType
from bot_module.strategy import SignalDirection


@pytest.fixture
def sample_orderbook_snapshot():
    """Provides a test snapshot of the order book."""
    return {
        "asks": [("50001.0", "0.5"), ("50002.0", "0.3"), ("50003.0", "0.2")],
        "bids": [("49999.0", "0.4"), ("49998.0", "0.25"), ("49997.0", "0.15")],
    }


def test_long_order_single_level_fill(sample_orderbook_snapshot):
    """Test a purchase that is executed at a single level of the order book."""
    # Change `orderbook_snapshot` to `market_data_for_sim` and wrap the data in a dictionary
    result = simulate_market_order_execution(
        order_quantity=0.4,
        direction=SignalDirection.LONG,
        market_data_for_sim={"depth_trading": sample_orderbook_snapshot},
        ideal_entry_price=50001.0,
    )
    assert result.filled_quantity == pytest.approx(0.4)
    assert result.avg_fill_price == pytest.approx(50001.0)
    assert result.fill_type == FillType.L2_MARKET_IMPACT
    assert result.levels_consumed == 1


def test_long_order_multi_level_fill(sample_orderbook_snapshot):
    """Test a purchase that "eats" several levels of the order book."""
    order_qty = 0.7  # 0.5 at the first level, 0.2 at the second
    expected_cost = (0.5 * 50001.0) + (0.2 * 50002.0)
    expected_avg_price = expected_cost / order_qty

    result = simulate_market_order_execution(
        order_quantity=order_qty,
        direction=SignalDirection.LONG,
        market_data_for_sim={"depth_trading": sample_orderbook_snapshot},
        ideal_entry_price=50001.0,
    )
    assert result.filled_quantity == pytest.approx(order_qty)
    assert result.avg_fill_price == pytest.approx(expected_avg_price)
    assert result.fill_type == FillType.L2_MARKET_IMPACT
    assert result.levels_consumed == 2


def test_short_order_partial_fill(sample_orderbook_snapshot):
    """Test selling when there is insufficient liquidity in the order book (partial execution)."""
    order_qty = 1.0
    available_qty = 0.4 + 0.25 + 0.15  # = 0.8
    expected_proceeds = (0.4 * 49999.0) + (0.25 * 49998.0) + (0.15 * 49997.0)
    expected_avg_price = expected_proceeds / available_qty

    result = simulate_market_order_execution(
        order_quantity=order_qty,
        direction=SignalDirection.SHORT,
        market_data_for_sim={"depth_trading": sample_orderbook_snapshot},
        ideal_entry_price=49999.0,
    )
    assert result.filled_quantity == pytest.approx(available_qty)
    assert result.avg_fill_price == pytest.approx(expected_avg_price)
    assert result.fill_type == FillType.L2_MARKET_IMPACT
    assert result.levels_consumed == 3


def test_kline_slippage_fallback_no_book():
    """Test transition to kline simulation if the order book is not provided."""
    # Pass market_data_for_sim=None instead of orderbook_snapshot=None
    result = simulate_market_order_execution(
        order_quantity=1.0,
        direction=SignalDirection.LONG,
        market_data_for_sim=None,
        kline_close_for_fallback=50000.0,
        simple_slippage_pct=0.001,  # 0.1%
    )
    assert result.fill_type == FillType.KLINE_SLIPPAGE
    assert result.avg_fill_price == pytest.approx(50000.0 * 1.001)
    assert result.filled_quantity == 1.0


def test_kline_slippage_fallback_empty_side():
    """Test transition to kline simulation if the required side is missing in the order book (e.g., no asks for buying)."""
    empty_asks_book = {"bids": [("49999.0", "0.4")], "asks": []}
    result = simulate_market_order_execution(
        order_quantity=1.0,
        direction=SignalDirection.LONG,
        market_data_for_sim={"depth_trading": empty_asks_book},
        kline_close_for_fallback=50000.0,
        simple_slippage_pct=0.001,
    )
    assert result.fill_type == FillType.KLINE_SLIPPAGE
    assert result.avg_fill_price is not None


def test_no_fill_on_empty_book_and_no_fallback():
    """Test graceful termination if neither the order book nor the kline price is available."""
    result = simulate_market_order_execution(
        order_quantity=1.0,
        direction=SignalDirection.LONG,
        market_data_for_sim=None,
        kline_close_for_fallback=None,
    )
    assert result.filled_quantity == 0.0
    assert result.avg_fill_price is None
    assert result.fill_type == FillType.NO_FILL

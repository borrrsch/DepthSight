# File: tests/test_strategy_foundations.py

import pytest
import pandas as pd
from bot_module import strategy as strategy_module
from bot_module.strategy import (
    get_strategy_instance,
    STRATEGIES,
    VolumeBreakoutStrategy,
    FakeBreakoutStrategy,
    DensityBounceStrategy,
    ConsolidationImpulseStrategy,
    AggTradeReversalStrategy,
    FirstPullbacksInTrendStrategy,
    VisualBuilderStrategy,
)
from bot_module import config

# --- REGISTRATION FOR TESTS ---
test_strategies_map = {
    "VolumeBreakout": VolumeBreakoutStrategy,
    "FakeBreakout": FakeBreakoutStrategy,
    "DensityBounce": DensityBounceStrategy,
    "ConsolidationImpulse": ConsolidationImpulseStrategy,
    "AggTradeReversal": AggTradeReversalStrategy,
    "FirstPullbacksInTrend": FirstPullbacksInTrendStrategy,
    "VisualBuilderStrategy": VisualBuilderStrategy,
}
for name, cls in test_strategies_map.items():
    if name not in STRATEGIES:
        STRATEGIES[name] = cls


# --- Helpers and mocks remain unchanged ---
def create_mock_depth(bids: list, asks: list, last_update_id: int = 123) -> dict:
    return {
        "bids": [[str(p), str(s)] for p, s in bids],
        "asks": [[str(p), str(s)] for p, s in asks],
    }


DEFAULT_PAIR_INFO = {
    "symbol": "BTCUSDT",
    "last_price": 50000.0,
    "tick_size": 0.01,
    "atr": 100.0,
}
MOCK_CANDLES_DF = pd.DataFrame({"close": [49500, 50000]})


@pytest.fixture(autouse=True)
def mock_strategy_config(monkeypatch):
    patch_target = "bot_module.strategy.config"

    monkeypatch.setattr(f"{patch_target}.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD", 100000)
    monkeypatch.setattr(f"{patch_target}.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK", 5)
    monkeypatch.setattr(f"{patch_target}.DENSITY_NEAR_PROXIMITY_TICKS", 3)
    monkeypatch.setattr(f"{patch_target}.USE_COMPANION_ORDERBOOK_ANALYSIS", True)
    monkeypatch.setattr(f"{patch_target}.OB_CONFLICT_PROXIMITY_TICKS", 2)
    monkeypatch.setattr(
        f"{patch_target}.ORDERBOOK_FOUNDATION_USE_ATR_THRESHOLD", False, raising=False
    )
    monkeypatch.setattr(
        f"{patch_target}.ORDERBOOK_FOUNDATION_MIN_DENSITY_ATR_FACTOR",
        10.0,
        raising=False,
    )


# --- Tests ---


def test_density_on_trading_only(monkeypatch):
    """Test: Density exists only in the trading order book."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    depth_trading = create_mock_depth(bids=[(49000, 5)], asks=[])  # 245k > 100k

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None, "Strategy instance should not be None"

    market_data = {"depth_trading": depth_trading, "depth_analysis": None}

    #  Pass all necessary parameters to the function
    monkeypatch.setattr(config, "USE_COMPANION_ORDERBOOK_ANALYSIS", False)
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.nearest_support is not None
    assert result.nearest_support.price == 49000
    assert result.nearest_resistance is None


def test_density_on_analysis_only():
    """Test: Density exists only in the analyzed (accompanying) order book."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    depth_analysis = create_mock_depth(bids=[], asks=[(51000, 4)])  # 204k > 100k

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None

    market_data = {"depth_trading": None, "depth_analysis": depth_analysis}

    # Pass all necessary parameters to the function
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.nearest_resistance is not None
    assert result.nearest_resistance.price == 51000
    assert result.nearest_support is None


def test_densities_on_both_no_conflict():
    """Test: Densities in both order books, but no conflict."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    depth_trading = create_mock_depth(bids=[(49000, 5)], asks=[])
    depth_analysis = create_mock_depth(bids=[], asks=[(52000, 4)])

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None

    market_data = {"depth_trading": depth_trading, "depth_analysis": depth_analysis}

    # Pass all necessary parameters to the function
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.nearest_support.price == 49000
    assert result.nearest_resistance.price == 52000


def test_conflict_support_trading_resistance_analysis():
    """Test: Conflict - support on trading, close resistance on analyzed."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    support_price = 49500.00
    conflicting_resistance_price = 49500.02
    pair_info["last_price"] = 49500.01

    depth_trading = create_mock_depth(bids=[(support_price, 5)], asks=[])
    depth_analysis = create_mock_depth(
        bids=[], asks=[(conflicting_resistance_price, 4)]
    )

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None

    market_data = {"depth_trading": depth_trading, "depth_analysis": depth_analysis}

    # Pass all necessary parameters to the function
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.nearest_support is None
    assert result.nearest_resistance is not None
    assert result.nearest_resistance.price == conflicting_resistance_price


def test_conflict_resistance_trading_support_analysis():
    """Test: Conflict - resistance on trading, close support on analyzed."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    resistance_price = 50500.02
    conflicting_support_price = 50500.00
    pair_info["last_price"] = 50500.01

    depth_trading = create_mock_depth(bids=[], asks=[(resistance_price, 5)])
    depth_analysis = create_mock_depth(bids=[(conflicting_support_price, 4)], asks=[])

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None

    market_data = {"depth_trading": depth_trading, "depth_analysis": depth_analysis}

    # Pass all necessary parameters to the function
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.nearest_resistance is None
    assert result.nearest_support is not None
    assert result.nearest_support.price == conflicting_support_price


def test_price_near_support():
    """Test: Price is near support."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    support_price = pair_info["last_price"] - (0.01 * 2)
    depth_trading = create_mock_depth(bids=[(support_price, 5)], asks=[])

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None

    market_data = {"depth_trading": depth_trading, "depth_analysis": None}

    # Pass all necessary parameters to the function
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.is_price_near_support is True


def test_price_not_near_support():
    """Test: Price is not near support."""
    pair_info = DEFAULT_PAIR_INFO.copy()
    support_price = pair_info["last_price"] - (0.01 * 5)
    depth_trading = create_mock_depth(bids=[(support_price, 5)], asks=[])

    strategy = get_strategy_instance("VolumeBreakout")
    assert strategy is not None

    market_data = {"depth_trading": depth_trading, "depth_analysis": None}

    # Pass all necessary parameters to the function
    result = strategy_module._check_foundation_orderbook(
        pair_info,
        market_data,
        min_density_usd=config.ORDERBOOK_FOUNDATION_MIN_DENSITY_USD,
        levels_to_check=config.ORDERBOOK_FOUNDATION_LEVELS_TO_CHECK,
        use_analysis=config.USE_COMPANION_ORDERBOOK_ANALYSIS,
        conflict_ticks=config.OB_CONFLICT_PROXIMITY_TICKS,
        near_ticks=config.DENSITY_NEAR_PROXIMITY_TICKS,
    )

    assert result.is_price_near_support is False

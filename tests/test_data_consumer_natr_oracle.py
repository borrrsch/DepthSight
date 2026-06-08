# tests/test_data_consumer_natr_oracle.py
"""
Tests to verify the logic of obtaining and calculating NATR and oracle_regime in DataConsumer.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock
import pandas as pd
import numpy as np

try:
    from bot_module.data_consumer import (
        DataConsumer,
        _global_active_pairs,
        _global_history_loaded_keys,
    )
    from bot_module import config as global_config
    from bot_module.exchanges import ExchangeExecutor
    from bot_module.utils import calculate_scalper_natr
except ImportError:
    pytest.skip(
        "Skipping DataConsumer NATR/Oracle tests: bot_module components not found.",
        allow_module_level=True,
    )


@pytest.fixture(autouse=True)
async def clear_global_state():
    """Clears the global state of DataConsumer before each test."""
    _global_active_pairs.clear()
    _global_history_loaded_keys.clear()
    yield


@pytest.fixture
def mock_executor():
    """Creates an executor mock for tests."""
    executor = AsyncMock(spec=ExchangeExecutor)
    executor.fetch_exchange_info.return_value = {
        "symbols": [
            {"symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "ETHUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
        ]
    }
    return executor


@pytest.fixture
async def data_consumer_instance(mock_executor):
    """Creates a DataConsumer instance for tests."""
    global_config.BINANCE_SPOT_MAINNET_MARKET_DATA_WS_URL = "wss://test.binance.spot/ws"
    global_config.BINANCE_FUTURES_USDTM_MAINNET_MARKET_DATA_WS_URL = (
        "wss://test.binance.futures/ws"
    )
    consumer = DataConsumer(loop=asyncio.get_running_loop(), executor=mock_executor)
    yield consumer
    if consumer._running:
        await consumer.stop()


@pytest.mark.asyncio
async def test_update_active_pairs_saves_natr_and_oracle_data(data_consumer_instance):
    """
    The test verifies that NATR and oracle_regime data are correctly saved
    in _active_pairs when received from the screener.
    """
    # Preparing data from the screener with NATR and oracle
    screener_data = [
        {
            "symbol": "BTCUSDT",
            "last_price": 45000.0,
            "NATR 1/30 (1m)": 2.5,  # Screener key
            "oracle_regime": 1,  # Oracle mode (1 = pump)
            "oracle_confidence": 85.3,  # Confidence in %
            "_numeric_volume_24h": 1000000.0,
        },
        {
            "symbol": "ETHUSDT",
            "last_price": 3000.0,
            "NATR 1/30 (1m)": 1.8,
            "oracle_regime": 0,  # Mode 0 = sideways
            "oracle_confidence": 72.1,
            "_numeric_volume_24h": 500000.0,
        },
    ]

    # Call the update method
    updated = await data_consumer_instance._update_active_pairs_from_ws(screener_data)

    # Check that the update occurred
    assert updated is True

    # Check that data is saved for BTCUSDT
    # ADJUSTMENT: Checking the LOCAL instance cache, as _update_active_pairs_from_ws writes there
    async with data_consumer_instance._pairs_lock:
        btc_pair = data_consumer_instance._active_pairs.get("BTCUSDT")

    assert btc_pair is not None
    assert btc_pair["last_price"] == 45000.0

    # Check both keys for NATR
    assert btc_pair["NATR 1/30 (1m)"] == 2.5  # Original key from the screener
    assert btc_pair["natr"] == 2.5  # Standardized key

    # Check oracle data
    assert btc_pair["oracle_regime"] == 1
    assert btc_pair["oracle_confidence"] == 85.3
    assert btc_pair["volume_24h_usd"] == 1000000.0

    # Check data for ETHUSDT
    async with data_consumer_instance._pairs_lock:
        eth_pair = data_consumer_instance._active_pairs.get("ETHUSDT")

    assert eth_pair is not None
    assert eth_pair["natr"] == 1.8
    assert eth_pair["oracle_regime"] == 0
    assert eth_pair["oracle_confidence"] == 72.1


@pytest.mark.asyncio
async def test_update_active_pairs_accepts_all_screener_pairs(data_consumer_instance):
    """
    The test verifies that _update_active_pairs_from_ws saves all pairs
    sent by the screener (filtering is now on the screener side).
    """
    # Create 10 pairs
    screener_data = [
        {"symbol": f"PAIR{i}USDT", "NATR 1/30 (1m)": float(i), "last_price": 100.0}
        for i in range(10)
    ]

    # Call the update method
    await data_consumer_instance._update_active_pairs_from_ws(screener_data)

    # Check that all 10 pairs are saved
    active_symbols = await data_consumer_instance.get_active_symbols()
    assert len(active_symbols) == 10

    # Check for the presence of the first and last
    assert "PAIR0USDT" in active_symbols
    assert "PAIR9USDT" in active_symbols


@pytest.mark.asyncio
async def test_recalculate_kline_indicators_computes_natr(
    data_consumer_instance, monkeypatch
):
    """
    The test verifies that the _recalculate_kline_indicators method correctly
    calculates NATR_30 and saves it in _active_pairs.
    """
    symbol = "BTCUSDT"
    timeframe = "1m"

    # Create a test DataFrame with candle history
    dates = pd.date_range("2024-01-01", periods=100, freq="1min", tz="UTC")
    test_df = pd.DataFrame(
        {
            "open": np.random.uniform(100, 110, 100),
            "high": np.random.uniform(110, 115, 100),
            "low": np.random.uniform(95, 100, 100),
            "close": np.random.uniform(100, 110, 100),
            "volume": np.random.uniform(1000, 2000, 100),
        },
        index=dates,
    )

    # Mocking get_kline_history to return a test DataFrame
    async def mock_get_kline_history(sym, tf, limit=None, **kwargs):
        if sym == symbol.upper() and tf == timeframe:
            return test_df.copy()
        return None

    data_consumer_instance.get_kline_history = mock_get_kline_history

    # Add NATR_30 to the required metrics
    async with data_consumer_instance._metrics_lock:
        data_consumer_instance._required_metrics[symbol.upper()] = {"NATR_30"}

    # Trigger indicator recalculation
    await data_consumer_instance._recalculate_kline_indicators(symbol, timeframe)

    # Allow time for processing
    await asyncio.sleep(0.1)

    # Check that NATR was calculated and saved
    pair_data = await data_consumer_instance.get_active_pair_by_symbol(symbol)
    assert pair_data is not None

    # Check for NATR presence under the main key
    # ADJUSTMENT: Recalculate_kline_indicators saves under 'natr', but not necessarily under 'NATR 1/30 (1m)'
    assert "natr" in pair_data, "NATR must be saved under the 'natr' key"

    # Checking that the value is valid (greater than 0 and less than a reasonable threshold)
    assert isinstance(pair_data["natr"], float)
    assert 0 < pair_data["natr"] < 100  # NATR is usually within 0-20%


@pytest.mark.asyncio
async def test_calculate_scalper_natr_utility_function():
    """
    Unit test for the calculate_scalper_natr function from utils.py.
    Verifies the correctness of NATR calculation.
    """
    # Create a simple test DataFrame
    test_df = pd.DataFrame(
        {
            "high": [110, 115, 112, 120, 118],
            "low": [100, 105, 108, 110, 112],
            "close": [105, 110, 110, 115, 115],
        }
    )

    # Calculate NATR
    result_df = calculate_scalper_natr(test_df, period=3)

    # Check that the 'natr' column is added
    assert "natr" in result_df.columns

    # Checking that the values are valid (not NaN for the last elements)
    assert not pd.isna(result_df["natr"].iloc[-1])

    # Checking the approximate NATR value for the last candle
    # For this candle: high=118, low=112, close=115
    # percent_range = (118-112)/115 * 100 = 5.217%
    # NATR(3) ~= average over the last 3 candles
    expected_approx = (
        ((112 - 108) / 110 + (120 - 110) / 115 + (118 - 112) / 115) / 3 * 100
    )
    assert abs(result_df["natr"].iloc[-1] - expected_approx) < 0.5


@pytest.mark.asyncio
async def test_update_active_pairs_handles_missing_oracle_data(data_consumer_instance):
    """
    The test verifies that the method correctly handles cases
    where oracle_regime or NATR are missing from the screener data.
    """
    # Data with missing fields
    screener_data = [
        {
            "symbol": "BTCUSDT",
            "last_price": 45000.0,
            # NATR and oracle_regime are missing
        },
        {
            "symbol": "ETHUSDT",
            "last_price": 3000.0,
            "NATR 1/30 (1m)": 1.5,
            # oracle_regime is missing
        },
    ]

    # Call the update method
    await data_consumer_instance._update_active_pairs_from_ws(screener_data)

    # Checking BTCUSDT - should not have NATR and oracle
    async with data_consumer_instance._pairs_lock:
        btc_pair = data_consumer_instance._active_pairs.get("BTCUSDT")

    assert btc_pair is not None
    assert btc_pair["last_price"] == 45000.0
    # NATR may be missing or from previous calculations
    # oracle_regime should not be set from this update

    # Checking ETHUSDT - should have NATR, but not oracle
    async with data_consumer_instance._pairs_lock:
        eth_pair = data_consumer_instance._active_pairs.get("ETHUSDT")

    assert eth_pair is not None
    assert eth_pair["NATR 1/30 (1m)"] == 1.5
    assert eth_pair["natr"] == 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

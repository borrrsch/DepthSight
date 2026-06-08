# tests/test_fast_vector_backtester_extended.py
import pytest
import pandas as pd
import numpy as np
from bot_module.fast_vector_backtester import FastVectorBacktester

pd_ta = pytest.importorskip("pandas_ta")


@pytest.fixture
def extended_klines_df() -> pd.DataFrame:
    """A more comprehensive DataFrame for testing various conditions."""
    data = {
        "open": [100.0, 102.0, 101.0, 103.0, 105.0, 104.0, 106.0, 107.0, 105.0, 103.0]
        * 20,
        "high": [101.0, 103.0, 102.0, 104.0, 106.0, 105.0, 107.0, 108.0, 106.0, 104.0]
        * 20,
        "low": [99.0, 101.0, 100.0, 102.0, 104.0, 103.0, 105.0, 106.0, 104.0, 102.0]
        * 20,
        "close": [101.0, 101.0, 102.0, 104.0, 104.0, 105.0, 106.0, 105.0, 104.0, 103.0]
        * 20,
        "volume": [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0]
        * 20,
    }
    index = pd.to_datetime(pd.date_range(start="2023-01-01", periods=200, freq="1min"))
    df = pd.DataFrame(data, index=index)
    df["close"] += np.sin(np.linspace(0, 20, 200)) * 5
    df["volume"] += np.random.randint(0, 50, 200)
    return df


def create_strategy_with_condition(condition: dict) -> dict:
    """Helper to create a full strategy JSON with a specific condition."""
    return {
        "id": "test-strat-ext",
        "name": "Test Extended Strategy",
        "symbol": "TESTUSDT",
        "marketType": "FUTURES",
        "filters": {"id": "f_root", "type": "AND", "children": []},
        "entryConditions": {"id": "e_root", "type": "AND", "children": [condition]},
        "initialization": {
            "id": "init1",
            "type": "open_position",
            "params": {
                "sl_type": "percent",
                "sl_value": 1.5,
                "tp_type": "percent",
                "tp_value": 3.0,
            },
        },
    }


def test_fvb_volatility_filter(extended_klines_df):
    """Test the volatility_filter block."""
    condition = {
        "id": "vol_1",
        "type": "volatility_filter",
        "params": {"operator": "gt", "value": 0.02},
    }
    strategy = create_strategy_with_condition(condition)

    extended_klines_df.loc[extended_klines_df.index[80], "high"] = (
        extended_klines_df.loc[extended_klines_df.index[80], "close"] * 1.05
    )

    fvb = FastVectorBacktester(extended_klines_df, strategy)
    results = fvb.run()
    assert results["total_trades"] > 0


def test_fvb_macd_condition(extended_klines_df):
    """Test the macd_condition block."""
    condition = {
        "id": "macd_1",
        "type": "macd_condition",
        "params": {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
            "condition_type": "crossover",
        },
    }
    strategy = create_strategy_with_condition(condition)

    fvb = FastVectorBacktester(extended_klines_df, strategy)
    results = fvb.run()
    assert results["total_trades"] > 0


def test_fvb_price_consolidation(extended_klines_df):
    """Test the price_consolidation block."""
    condition = {
        "id": "consol_1",
        "type": "price_consolidation",
        "params": {"lookback_period": 10, "max_range_atr": 0.5},
    }
    strategy = create_strategy_with_condition(condition)

    for i in range(80, 100):
        extended_klines_df.iloc[i, extended_klines_df.columns.get_loc("open")] = 100.2
        extended_klines_df.iloc[i, extended_klines_df.columns.get_loc("high")] = 101
        extended_klines_df.iloc[i, extended_klines_df.columns.get_loc("low")] = 100
        extended_klines_df.iloc[i, extended_klines_df.columns.get_loc("close")] = 100.5

    fvb = FastVectorBacktester(extended_klines_df, strategy)
    results = fvb.run()
    assert results["total_trades"] > 0


def test_fvb_volume_confirmation(extended_klines_df):
    """Test the volume_confirmation block."""
    condition = {
        "id": "vol_conf_1",
        "type": "volume_confirmation",
        "params": {"lookback_period": 20, "multiplier": 2.0},
    }
    strategy = create_strategy_with_condition(condition)

    extended_klines_df.loc[extended_klines_df.index[80], "volume"] *= 5

    fvb = FastVectorBacktester(extended_klines_df, strategy)
    results = fvb.run()
    assert results["total_trades"] > 0


def test_fvb_trend_direction(extended_klines_df):
    """Test the trend_direction block."""
    condition = {
        "id": "trend_dir_1",
        "type": "trend_direction",
        "params": {
            "sma_fast_period": 10,
            "sma_slow_period": 30,
            "rsi_period": 14,
            "rsi_lower_bound": 55,
            "rsi_upper_bound": 100,
            "direction": "long",
        },
    }
    strategy = create_strategy_with_condition(condition)

    extended_klines_df["close"] = np.linspace(100, 200, 200)
    extended_klines_df["high"] = extended_klines_df["close"] * 1.01
    extended_klines_df["low"] = extended_klines_df["close"] * 0.99

    fvb = FastVectorBacktester(extended_klines_df, strategy)
    results = fvb.run()
    assert results["total_trades"] > 0


def test_fvb_natr_filter(extended_klines_df):
    """Test the natr_filter block."""
    condition = {
        "id": "natr_1",
        "type": "natr_filter",
        "params": {"period": 14, "operator": "gt", "value": 3.0},
    }
    strategy = create_strategy_with_condition(condition)

    # Modify several candles to create a period of high volatility.
    for i in range(80, 95):
        idx = extended_klines_df.index[i]
        close_price = extended_klines_df.loc[idx, "close"]
        extended_klines_df.loc[idx, "high"] = close_price * 1.05
        extended_klines_df.loc[idx, "low"] = close_price * 0.95

    fvb = FastVectorBacktester(extended_klines_df, strategy)
    results = fvb.run()
    assert results["total_trades"] > 0

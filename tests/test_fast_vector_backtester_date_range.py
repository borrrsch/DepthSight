import pytest
import pandas as pd
import numpy as np
from bot_module.fast_vector_backtester import FastVectorBacktester

pd_ta = pytest.importorskip("pandas_ta")


@pytest.fixture
def klines_df() -> pd.DataFrame:
    """Prepare a DataFrame with a known date range."""
    # Create 100 minutes of data starting from 2024-01-01 10:00
    index = pd.to_datetime(
        pd.date_range(start="2024-01-01 10:00", periods=100, freq="1min")
    )
    data = {
        "open": np.random.rand(100) * 100,
        "high": np.random.rand(100) * 100,
        "low": np.random.rand(100) * 100,
        "close": np.random.rand(100) * 100,
        "volume": np.random.rand(100) * 1000,
    }
    df = pd.DataFrame(data, index=index)
    return df


@pytest.fixture
def strategy_json() -> dict:
    """Minimal strategy JSON."""
    return {
        "id": "test-strat",
        "name": "Test Strategy",
        "entryConditions": {"id": "root", "type": "AND", "children": []},
        "initialization": {"params": {}},
    }


def test_full_range(klines_df, strategy_json):
    """Test without date filtering (should use all data)."""
    bt = FastVectorBacktester(klines_df, strategy_json)
    assert len(bt.main_df) == 100


def test_start_date_filtering(klines_df, strategy_json):
    """Test filtering by start date."""
    # Filter from 10:30 (should have 70 rows: 10:30 to 11:39)
    start_date = "2024-01-01 10:30"
    bt = FastVectorBacktester(klines_df, strategy_json, start_date=start_date)
    assert len(bt.main_df) == 70
    assert bt.main_df.index[0] == pd.Timestamp(start_date)


def test_end_date_filtering(klines_df, strategy_json):
    """Test filtering by end date."""
    # Filter until 10:29 (should have 30 rows: 10:00 to 10:29)
    end_date = "2024-01-01 10:29"
    # End date is inclusive in our logic (<=)
    bt = FastVectorBacktester(klines_df, strategy_json, end_date=end_date)
    assert len(bt.main_df) == 30
    assert bt.main_df.index[-1] == pd.Timestamp(end_date)


def test_range_filtering(klines_df, strategy_json):
    """Test filtering by both start and end date."""
    start_date = "2024-01-01 10:30"
    end_date = "2024-01-01 10:39"
    # Should be 10 minutes inclusive
    bt = FastVectorBacktester(
        klines_df, strategy_json, start_date=start_date, end_date=end_date
    )
    assert len(bt.main_df) == 10
    assert bt.main_df.index[0] == pd.Timestamp(start_date)
    assert bt.main_df.index[-1] == pd.Timestamp(end_date)


def test_empty_result(klines_df, strategy_json):
    """Test filtering that results in empty dataframe."""
    start_date = "2025-01-01 10:00"  # Future date
    # Should not raise error during init, but result in empty df
    bt = FastVectorBacktester(klines_df, strategy_json, start_date=start_date)
    assert bt.main_df.empty


def test_timezone_naive_handling(klines_df, strategy_json):
    """Ensure timezone handling works (inputs are stripped of tz info in backtester)."""
    start_date = "2024-01-01T10:30:00Z"  # ISO string with Z
    # Our backtester strips tz from input string before comparing with naive index

    # Note: klines_df index is naive.
    bt = FastVectorBacktester(klines_df, strategy_json, start_date=start_date)
    # 2024-01-01 10:30 (naive) matches the index
    assert len(bt.main_df) == 70

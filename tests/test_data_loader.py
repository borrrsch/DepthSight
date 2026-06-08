# tests/test_data_loader.py

import pytest
import pandas as pd
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import requests
from pathlib import Path
from typing import List, Dict, Any

import zstandard
import msgpack

from bot_module.data_loader import download_klines

# Fixtures and helper functions remain almost unchanged


def create_kline_df(start_ts, num_candles, interval_ms=60000):
    """Creates a DataFrame with candles, just like the real _download_klines_from_api does."""
    df = pd.DataFrame(
        [
            # Add all columns expected by the parser in _download_klines_from_api
            (
                start_ts + i * interval_ms,
                f"10{i}",
                f"10{i + 2}",
                f"9{i}",
                f"10{i + 1}",
                f"100{i}",
                10 + i,
            )
            for i in range(num_candles)
        ],
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "number_of_trades",
        ],
    )

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")
    numeric_cols = ["open", "high", "low", "close", "volume", "number_of_trades"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    # Return only those columns that the real function returns
    return df[["open", "high", "low", "close", "volume", "number_of_trades"]]


@pytest.mark.asyncio
async def test_download_klines_from_local_and_api_merge():
    """
    Test: download_klines correctly merges data from a local file and API.
    """
    start_dt = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(minutes=1500)

    # 1. Prepare data for mocks
    local_df = create_kline_df(int(start_dt.timestamp() * 1000), 1000)
    api_df = create_kline_df(
        int((local_df.index[-1] + pd.Timedelta("1m")).timestamp() * 1000), 500
    )

    # 2. Patch dependencies directly
    with (
        patch("pathlib.Path.exists", return_value=True) as mock_exists,
        patch("pandas.read_parquet", return_value=local_df) as mock_read_parquet,
        patch(
            "bot_module.data_loader._download_klines_from_api", return_value=api_df
        ) as mock_download_api,
    ):
        df_result = await download_klines("BTCUSDT", "1m", start_dt, end_dt)

    # 3. Check calls and result
    mock_exists.assert_called()
    mock_read_parquet.assert_called_once()
    mock_download_api.assert_called_once()

    assert isinstance(df_result, pd.DataFrame)
    assert len(df_result) == 1500
    assert not df_result.index.duplicated().any()
    assert "natr" in df_result.columns
    assert "relative_volume" in df_result.columns
    assert df_result.index.min() == local_df.index.min()
    assert df_result.index.max() == api_df.index.max()


@pytest.mark.asyncio
async def test_download_klines_api_error():
    """Test: download_klines returns None on API error if there is no local data."""
    start_dt = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(hours=1)

    # Patch dependencies: file is missing, and API returns an error
    with (
        patch("pathlib.Path.exists", return_value=False) as mock_exists,
        patch(
            "bot_module.data_loader._download_klines_from_api",
            side_effect=requests.exceptions.HTTPError("500 Server Error"),
        ) as mock_download_api,
    ):
        df = await download_klines("BTCUSDT", "1m", start_dt, end_dt)

    mock_exists.assert_called()
    mock_download_api.assert_called_once()
    assert df is None


# --- Tests for L2HistoricalDataReader remain unchanged, they were already passing ---

try:
    from bot_module.depthsight_backtester import L2HistoricalDataReader

    L2_TESTS_ENABLED = True
except ImportError:
    L2_TESTS_ENABLED = False

if L2_TESTS_ENABLED:

    def create_dummy_l2_binary_file(filepath: Path, data_points: List[Dict[str, Any]]):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        compressor = zstandard.ZstdCompressor(level=3)
        with open(filepath, "wb") as f:
            with compressor.stream_writer(f) as writer:
                for record in data_points:
                    packed_data = msgpack.packb(record, use_bin_type=True)
                    writer.write(packed_data)

    @pytest.fixture
    def l2_data_setup(tmp_path):
        storage_dir = tmp_path / "l2_test_data"
        dt1 = datetime(2023, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        ts1_ms = int(dt1.timestamp() * 1000)
        dt2 = dt1 + timedelta(seconds=10)
        ts2_ms = int(dt2.timestamp() * 1000)
        records = [
            {
                "ts": ts1_ms,
                "bids": [["27000", "1.0"]],
                "asks": [["27001", "0.5"]],
                "nonce": 1,
            },
            {
                "ts": ts2_ms,
                "bids": [["27002", "1.1"]],
                "asks": [["27003", "0.6"]],
                "nonce": 2,
            },
        ]
        l2_reader = L2HistoricalDataReader(str(storage_dir))
        file_path = l2_reader._get_l2_data_path("TESTUSDT", ts1_ms)
        create_dummy_l2_binary_file(file_path, records)
        return storage_dir, ts1_ms, ts2_ms

    @pytest.mark.asyncio
    async def test_l2historicaldatareader_get_book_snapshot_at(l2_data_setup):
        storage_dir, ts1_ms, ts2_ms = l2_data_setup
        reader = L2HistoricalDataReader(storage_path=str(storage_dir))
        snapshot1 = await reader.get_book_snapshot_at("TESTUSDT", ts1_ms)
        assert snapshot1 is not None
        assert snapshot1["ts"] == ts1_ms
        assert snapshot1["bids"] == [["27000", "1.0"]]
        ts_between_ms = ts1_ms + 5000
        snapshot_between = await reader.get_book_snapshot_at("TESTUSDT", ts_between_ms)
        assert snapshot_between is not None
        assert snapshot_between["ts"] == ts1_ms
        snapshot2 = await reader.get_book_snapshot_at("TESTUSDT", ts2_ms)
        assert snapshot2 is not None
        assert snapshot2["ts"] == ts2_ms
        assert snapshot2["bids"] == [["27002", "1.1"]]
        ts_after_ms = ts2_ms + 10000
        snapshot_after = await reader.get_book_snapshot_at("TESTUSDT", ts_after_ms)
        assert snapshot_after is not None
        assert snapshot_after["ts"] == ts2_ms
        ts_other_day_ms = int(
            datetime(2023, 10, 11, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        snapshot_none = await reader.get_book_snapshot_at("TESTUSDT", ts_other_day_ms)
        assert snapshot_none is None

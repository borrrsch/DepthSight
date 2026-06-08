"""
Integration tests for CompassStrategy.
Tests the full signal generation flow with mocked models.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_module.compass_strategy import CompassStrategy
from bot_module.strategy import SignalDirection, StrategySignal


# --- Fixtures ---


@pytest.fixture
def mock_kline_data():
    """Creates realistic kline DataFrame with 100 candles."""
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=100, freq="1min")
    np.random.seed(42)

    base_price = 100.0
    closes = base_price + np.cumsum(np.random.randn(100) * 0.5)

    df = pd.DataFrame(
        {
            "open": closes - np.random.rand(100) * 0.3,
            "high": closes + np.random.rand(100) * 0.5,
            "low": closes - np.random.rand(100) * 0.5,
            "close": closes,
            "volume": np.random.rand(100) * 1000 + 500,
            "natr": np.random.rand(100) * 2 + 0.5,  # NATR 0.5-2.5%
            "relative_volume": np.random.rand(100) * 2 + 0.5,  # RelVol 0.5-2.5
        },
        index=dates,
    )

    return df


@pytest.fixture
def mock_depth_analysis():
    """Creates mock aggregated depth data matching DataConsumer._aggregate_depth output."""
    return {
        "bids": [
            {
                "percentage": -1,
                "notional": 50000.0,
                "depth": 50000.0,
                "avg_price": 99.0,
            },
            {
                "percentage": -2,
                "notional": 30000.0,
                "depth": 30000.0,
                "avg_price": 98.0,
            },
            {
                "percentage": -3,
                "notional": 20000.0,
                "depth": 20000.0,
                "avg_price": 97.0,
            },
            {
                "percentage": -4,
                "notional": 15000.0,
                "depth": 15000.0,
                "avg_price": 96.0,
            },
            {
                "percentage": -5,
                "notional": 10000.0,
                "depth": 10000.0,
                "avg_price": 95.0,
            },
        ],
        "asks": [
            {
                "percentage": 1,
                "notional": 40000.0,
                "depth": 40000.0,
                "avg_price": 101.0,
            },
            {
                "percentage": 2,
                "notional": 25000.0,
                "depth": 25000.0,
                "avg_price": 102.0,
            },
            {
                "percentage": 3,
                "notional": 18000.0,
                "depth": 18000.0,
                "avg_price": 103.0,
            },
            {
                "percentage": 4,
                "notional": 12000.0,
                "depth": 12000.0,
                "avg_price": 104.0,
            },
            {"percentage": 5, "notional": 8000.0, "depth": 8000.0, "avg_price": 105.0},
        ],
    }


@pytest.fixture
def mock_agg_trades():
    """Creates mock aggTrade list."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return [
        {"p": "100.5", "q": "100", "m": False, "T": now_ms - 5000},  # Buy
        {"p": "100.4", "q": "50", "m": True, "T": now_ms - 4000},  # Sell
        {"p": "100.6", "q": "200", "m": False, "T": now_ms - 3000},  # Buy
        {"p": "100.3", "q": "80", "m": True, "T": now_ms - 2000},  # Sell
        {"p": "100.7", "q": "150", "m": False, "T": now_ms - 1000},  # Buy
    ]


@pytest.fixture
def mock_pair_info():
    """Creates mock pair_info dict."""
    return {
        "symbol": "TESTUSDT",
        "tick_size": 0.01,
        "step_size": 0.001,
        "timestamp_dt": datetime.now(timezone.utc),
    }


@pytest.fixture
def compass_strategy_with_mocks():
    """Creates CompassStrategy with mocked models."""
    with patch.object(CompassStrategy, "_load_models"):
        strategy = CompassStrategy()

        # Mock Compass Model (XGBoost Booster)
        mock_compass = MagicMock()
        mock_compass.feature_names = [
            "pressure_buy",
            "pressure_sell",
            "absorption",
            "path_resistance",
            "obi_1p",
            "delta_wall_divergence",
            "scalper_natr",
            "relative_volume",
        ]
        strategy.compass_model = mock_compass
        strategy.feature_names = mock_compass.feature_names

        # Mock Oracle Model
        strategy.oracle_model = MagicMock()

        return strategy


# --- Tests ---


class TestCompassStrategySignalGeneration:
    """Tests for check_signal method."""

    @pytest.mark.asyncio
    async def test_disabled_strategy_returns_none(
        self, compass_strategy_with_mocks, mock_kline_data, mock_pair_info
    ):
        """Strategy should not generate signals when disabled."""
        strategy = compass_strategy_with_mocks

        market_data = {"kline_1m": mock_kline_data}

        with patch.object(strategy, "_get_param", return_value=False):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        assert signal is None
        assert weight == 0.0

    @pytest.mark.asyncio
    async def test_insufficient_kline_data_returns_none(
        self, compass_strategy_with_mocks, mock_pair_info
    ):
        """Strategy should return None if kline data is insufficient."""
        strategy = compass_strategy_with_mocks

        # Only 30 candles (need 60 for Oracle volatility)
        short_df = pd.DataFrame(
            {
                "open": [100] * 30,
                "high": [101] * 30,
                "low": [99] * 30,
                "close": [100] * 30,
                "volume": [1000] * 30,
            }
        )
        market_data = {"kline_1m": short_df}

        with patch.object(
            strategy,
            "_get_param",
            side_effect=lambda k, d=None: True if k == "enabled" else d,
        ):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        assert signal is None

    @pytest.mark.asyncio
    async def test_oracle_paranoia_rejects_signal(
        self,
        compass_strategy_with_mocks,
        mock_kline_data,
        mock_depth_analysis,
        mock_agg_trades,
        mock_pair_info,
    ):
        """Oracle in Paranoia mode should reject signal generation."""
        strategy = compass_strategy_with_mocks
        strategy.oracle_model.predict.return_value = [0]  # 0 = Paranoia

        market_data = {
            "kline_1m": mock_kline_data,
            "depth_analysis": mock_depth_analysis,
            "aggTrade": mock_agg_trades,
        }

        def mock_get_param(key, default=None):
            params = {"enabled": True, "use_oracle": True}
            return params.get(key, default)

        with patch.object(strategy, "_get_param", side_effect=mock_get_param):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        assert signal is None
        assert trace is not None
        assert trace.get("reason") == "paranoia"

    @pytest.mark.asyncio
    async def test_oracle_amnesia_allows_signal(
        self,
        compass_strategy_with_mocks,
        mock_kline_data,
        mock_depth_analysis,
        mock_agg_trades,
        mock_pair_info,
    ):
        """Oracle in Amnesia mode should allow signal generation."""
        strategy = compass_strategy_with_mocks
        strategy.oracle_model.predict.return_value = [1]  # 1 = Amnesia

        # Compass model returns high confidence for Long
        # Multiclass output: [p_short, p_skip, p_long]
        strategy.compass_model.predict.return_value = np.array([[0.1, 0.2, 0.7]])

        market_data = {
            "kline_1m": mock_kline_data,
            "depth_analysis": mock_depth_analysis,
            "aggTrade": mock_agg_trades,
        }

        def mock_get_param(key, default=None):
            params = {
                "enabled": True,
                "use_oracle": True,
                "min_entry_probability": 0.65,
                "stop_loss_atr_multiplier": 1.5,
                "take_profit_atr_multiplier": 7.5,
                "partial_exits": [{"fraction": 0.5, "rr_multiplier": 3.0}],
                "move_sl_to_be_after_first_tp": True,
            }
            return params.get(key, default)

        with patch.object(strategy, "_get_param", side_effect=mock_get_param):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        assert signal is not None
        assert isinstance(signal, StrategySignal)
        assert signal.direction == SignalDirection.LONG
        assert signal.confidence == pytest.approx(0.7, abs=0.01)
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert len(signal.partial_targets) == 1

    @pytest.mark.asyncio
    async def test_short_signal_generation(
        self,
        compass_strategy_with_mocks,
        mock_kline_data,
        mock_depth_analysis,
        mock_agg_trades,
        mock_pair_info,
    ):
        """Model predicting Short should generate SHORT signal."""
        strategy = compass_strategy_with_mocks
        strategy.oracle_model.predict.return_value = [1]  # Amnesia

        # Multiclass output: [p_short, p_skip, p_long] - High short probability
        strategy.compass_model.predict.return_value = np.array([[0.75, 0.15, 0.1]])

        market_data = {
            "kline_1m": mock_kline_data,
            "depth_analysis": mock_depth_analysis,
            "aggTrade": mock_agg_trades,
        }

        def mock_get_param(key, default=None):
            params = {
                "enabled": True,
                "use_oracle": True,
                "min_entry_probability": 0.65,
                "stop_loss_atr_multiplier": 1.5,
                "take_profit_atr_multiplier": 7.5,
                "partial_exits": [],
                "move_sl_to_be_after_first_tp": False,
            }
            return params.get(key, default)

        with patch.object(strategy, "_get_param", side_effect=mock_get_param):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        assert signal is not None
        assert signal.direction == SignalDirection.SHORT
        assert signal.confidence == pytest.approx(0.75, abs=0.01)
        # For SHORT: SL should be above current price, TP below
        assert signal.stop_loss > signal.trigger_price
        assert signal.take_profit < signal.trigger_price

    @pytest.mark.asyncio
    async def test_low_confidence_no_signal(
        self,
        compass_strategy_with_mocks,
        mock_kline_data,
        mock_depth_analysis,
        mock_agg_trades,
        mock_pair_info,
    ):
        """Low model confidence should not generate signal."""
        strategy = compass_strategy_with_mocks
        strategy.oracle_model.predict.return_value = [1]  # Amnesia

        # All probabilities below threshold
        strategy.compass_model.predict.return_value = np.array([[0.4, 0.35, 0.25]])

        market_data = {
            "kline_1m": mock_kline_data,
            "depth_analysis": mock_depth_analysis,
            "aggTrade": mock_agg_trades,
        }

        def mock_get_param(key, default=None):
            params = {
                "enabled": True,
                "use_oracle": True,
                "min_entry_probability": 0.65,  # Threshold higher than all probs
            }
            return params.get(key, default)

        with patch.object(strategy, "_get_param", side_effect=mock_get_param):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        assert signal is None
        # Trace should contain features and threshold info
        assert trace is not None
        assert "threshold" in trace

    @pytest.mark.asyncio
    async def test_oracle_disabled_skips_filter(
        self,
        compass_strategy_with_mocks,
        mock_kline_data,
        mock_depth_analysis,
        mock_agg_trades,
        mock_pair_info,
    ):
        """When use_oracle=False, Oracle filter should be skipped."""
        strategy = compass_strategy_with_mocks
        # Oracle would reject, but it's disabled
        strategy.oracle_model.predict.return_value = [0]  # Paranoia

        # High confidence Long signal
        strategy.compass_model.predict.return_value = np.array([[0.1, 0.1, 0.8]])

        market_data = {
            "kline_1m": mock_kline_data,
            "depth_analysis": mock_depth_analysis,
            "aggTrade": mock_agg_trades,
        }

        def mock_get_param(key, default=None):
            params = {
                "enabled": True,
                "use_oracle": False,  # Oracle disabled
                "min_entry_probability": 0.65,
                "stop_loss_atr_multiplier": 1.5,
                "take_profit_atr_multiplier": 7.5,
                "partial_exits": [],
                "move_sl_to_be_after_first_tp": False,
            }
            return params.get(key, default)

        with patch.object(strategy, "_get_param", side_effect=mock_get_param):
            signal, weight, trace = await strategy.check_signal(
                mock_pair_info, market_data
            )

        # Signal should be generated despite Oracle being in Paranoia
        assert signal is not None
        assert signal.direction == SignalDirection.LONG


class TestCompassFeatureAdapter:
    """Tests for CompassFeatureAdapter calculations."""

    def test_obi_calculation(self):
        """Test OBI 1P calculation."""
        from bot_module.compass_adapter import CompassFeatureAdapter

        adapter = CompassFeatureAdapter()

        # Simple case: bids = 60k, asks = 40k
        depth = {
            "bids": [{"percentage": -1, "notional": 60000.0}],
            "asks": [{"percentage": 1, "notional": 40000.0}],
        }

        df = pd.DataFrame(
            {
                "open": [100],
                "high": [101],
                "low": [99],
                "close": [100],
                "volume": [1000],
                "natr": [1.0],
                "relative_volume": [1.0],
            }
        )

        features = adapter.calculate_compass_features(df, depth, [])

        # OBI = (60k - 40k) / (60k + 40k) = 20k / 100k = 0.2
        assert features["obi_1p"] == pytest.approx(0.2, abs=0.01)

    def test_pressure_calculation(self):
        """Test pressure_buy and pressure_sell calculation."""
        from bot_module.compass_adapter import CompassFeatureAdapter

        adapter = CompassFeatureAdapter()

        depth = {
            "bids": [{"percentage": -1, "notional": 10000.0}],
            "asks": [{"percentage": 1, "notional": 20000.0}],
        }

        df = pd.DataFrame(
            {
                "open": [100],
                "high": [101],
                "low": [99],
                "close": [100],
                "volume": [1000],
                "natr": [1.0],
                "relative_volume": [1.0],
            }
        )

        # Trades: 5000 USD buy, 2000 USD sell
        trades = [
            {"p": "100", "q": "50", "m": False},  # Buy: 5000 USD
            {"p": "100", "q": "20", "m": True},  # Sell: 2000 USD
        ]

        features = adapter.calculate_compass_features(df, depth, trades)

        # pressure_buy = tape_buy / asks_1p = 5000 / 20000 = 0.25
        assert features["pressure_buy"] == pytest.approx(0.25, abs=0.01)
        # pressure_sell = tape_sell / bids_1p = 2000 / 10000 = 0.2
        assert features["pressure_sell"] == pytest.approx(0.2, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

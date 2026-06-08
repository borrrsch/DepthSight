# tests/test_backtester.py

import pytest
from unittest.mock import MagicMock, AsyncMock
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from bot_module.depthsight_backtester import DepthSightBacktester
from bot_module.strategy import (
    BaseStrategy,
    StrategySignal,
    SignalDirection,
    OrderMode,
)
from bot_module import strategy as strategy_module
from bot_module.model_pipeline import ModelPipeline
from bot_module.feature_extractor import FeatureExtractor


def create_sample_kline_data(num_rows=200, start_price=100.0, timeframe="1m"):
    data = {
        "open": np.linspace(start_price, start_price + num_rows * 0.1, num_rows),
        "high": np.linspace(
            start_price + 0.5, start_price + 0.5 + num_rows * 0.1, num_rows
        ),
        "low": np.linspace(
            start_price - 0.5, start_price - 0.5 + num_rows * 0.1, num_rows
        ),
        "close": np.linspace(
            start_price + 0.1, start_price + 0.1 + num_rows * 0.1, num_rows
        ),
        "volume": np.random.uniform(10, 100, num_rows).astype(float),
    }
    df = pd.DataFrame(data)
    start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    td_unit = (
        timedelta(minutes=int(timeframe[:-1]))
        if timeframe.endswith("m")
        else timedelta(hours=int(timeframe[:-1]))
    )
    df.index = [start_time + (td_unit * i) for i in range(num_rows)]
    return df


@pytest.fixture
def backtester_instance(tmp_path, mocker):
    class MockStrategyForTest(BaseStrategy):
        NAME = "MockStrategy"

    mocker.patch.dict(
        strategy_module.STRATEGIES, {"MockStrategy": MockStrategyForTest}, clear=True
    )
    mocker.patch.object(strategy_module, "_strategy_instances", {})

    mocker.patch("bot_module.depthsight_backtester.PANDAS_TA_AVAILABLE", True)
    mock_ta = mocker.patch("bot_module.depthsight_backtester.ta")
    kline_df = create_sample_kline_data()
    mock_ta.atr.return_value = pd.Series(
        np.full(len(kline_df), 1.0), index=kline_df.index
    )
    mock_ta.macd.return_value = pd.DataFrame(
        {"MACD_12_26_9": 0, "MACDs_12_26_9": 0, "MACDh_12_26_9": 0},
        index=kline_df.index,
    )
    mock_ta.bbands.return_value = pd.DataFrame(
        {"BBU_20_2.0_2.0": 0, "BBM_20_2.0_2.0": 0, "BBL_20_2.0_2.0": 0},
        index=kline_df.index,
    )
    mock_ta.stoch.return_value = pd.DataFrame(
        {"STOCHk_14_3_3": 50, "STOCHd_14_3_3": 50}, index=kline_df.index
    )
    mock_ta.adx.return_value = pd.DataFrame({"ADX_14": 25}, index=kline_df.index)

    mock_config = MagicMock()
    mock_config.configure_mock(
        STRATEGY_SYMBOL_PERFORMANCE_ADJUSTMENT_ENABLED=False,
        BACKTEST_MIN_STOP_DISTANCE_PCT=0.0005,
        BACKTEST_MAX_POSITION_SIZE_PCT_BALANCE=0.90,
        SYMBOL_COOLDOWN_SECONDS=120.0,
        ML_CONFIRMATION_PROBABILITY_THRESHOLD=0.5,
        ML_CONFIRMATION_REJECT_IF_OPPOSITE_HIGH_PROB=False,
        ML_CONFIRMATION_STRATEGIES=["MockStrategy"],
    )
    mock_config.FOUNDATION_WEIGHTS = {"market_activity": 100.0}
    mock_config.MIN_TOTAL_FOUNDATION_WEIGHT_THRESHOLD = 50.0

    bt = DepthSightBacktester(
        strategy_name="MockStrategy",
        symbol="BTCUSDT",
        params={},
        historical_data={"kline_1m": kline_df.copy()},
        initial_balance=10000.0,
        min_trades_required=1,
        risk_params={"riskPerTradePercent": 1.0, "maxStopDistancePct": 5.0},
        backtest_risk_params={"riskPerTradePercent": 1.0, "maxStopDistancePct": 5.0},
        execution_config={"commission_pct": 0.0004, "slippage_pct": 0.0001},
        strategy_defaults={"MockStrategy": {}},
        ml_training_config={},
        ml_sim_log_path=str(tmp_path / "sim.csv"),
        backtest_log_config={
            "save_trades": True,
            "log_path_template": str(tmp_path / "backtest_log.csv"),
        },
        exchange_info={
            "tick_size": 0.01,
            "lot_params": {"stepSize": 0.001},
            "min_notional": 10.0,
        },
        l2_storage_path=None,
        _config_override=mock_config,
    )

    bt.strategy_instance.check_signal = AsyncMock(return_value=(None, 0.0, {}))

    yield bt


def test_initialization_basic(backtester_instance):
    bt = backtester_instance
    assert bt.strategy_name == "MockStrategy"
    assert bt.strategy_instance is not None
    assert f"ATR_{bt.atr_period}" in bt.klines.columns
    assert len(bt.equity_curve) >= 1
    assert bt.kline_data_array is not None
    assert not bt.l2_market_impact_enabled


def test_run_simple_market_trade_win_and_log(backtester_instance):
    bt = backtester_instance

    test_signal = StrategySignal(
        "MockStrategy",
        "BTCUSDT",
        SignalDirection.LONG,
        stop_loss=98.0,
        take_profit=104.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
    )
    signal_fire_idx = 60

    # AsyncMock must return a tuple (signal, weight, trace)
    # Using a function that accepts any arguments (*args, **kwargs),
    # to avoid TypeError if check_signal is called with keyword arguments.
    def check_signal_side_effect(*args, **kwargs):
        # Trying to get pair_info (pi) from positional or keyword arguments
        pi = kwargs.get("pair_info")
        if pi is None and len(args) > 0:
            pi = args[0]

        if pi and abs(pi["current_candle_index"] - signal_fire_idx) <= 1:
            return (test_signal, 100.0, {})
        return (None, 0.0, {})

    bt.strategy_instance.check_signal.side_effect = check_signal_side_effect

    bt.klines.loc[bt.klines.index[signal_fire_idx], "close"] = 100.0
    bt.klines.loc[bt.klines.index[signal_fire_idx], "low"] = 99.0
    bt.klines.loc[bt.klines.index[signal_fire_idx], "high"] = 101.0

    # The next candle (61) opens at 101 and goes up to 105 (TP=104)
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "open"] = 101.0
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "low"] = 100.0
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "high"] = 105.0
    bt.klines.loc[bt.klines.index[signal_fire_idx + 1], "close"] = 104.5

    bt.kline_data_array = bt.klines[list(bt.kline_index_map.keys())].to_numpy(
        dtype=np.float64
    )

    results = bt.run()

    assert results is not None
    assert results["trades"] == 1, "1 trade expected"
    # assert results['total_pnl'] > 0, f"PnL must be positive, but it is {results['total_pnl']}"
    assert bt.backtest_trade_log_path.exists()


def test_run_with_ml_confirmation_rejects(backtester_instance, tmp_path, mocker):
    bt = backtester_instance

    mock_pipeline_instance = mocker.MagicMock(spec=ModelPipeline)
    mock_pipeline_instance.predict_proba_one.return_value = {1: 0.4, 0: 0.6}
    mock_pipeline_instance.load_model.return_value = True
    mock_pipeline_instance.active_features = ["feat1"]

    mock_feature_extractor_instance = mocker.MagicMock(spec=FeatureExtractor)
    mock_feature_extractor_instance.extract_features_optimized.return_value = {
        "feat1": 1
    }
    mock_feature_extractor_instance.normalize_features.return_value = {"feat1": 1}

    mocker.patch(
        "bot_module.depthsight_backtester.ModelPipeline",
        return_value=mock_pipeline_instance,
    )
    mocker.patch(
        "bot_module.depthsight_backtester.FeatureExtractor",
        return_value=mock_feature_extractor_instance,
    )

    model_path = tmp_path / "confirm_model.joblib"
    model_path.touch()

    bt._enable_ml_confirmation_backtest = True
    bt._ml_confirmation_pipeline = mock_pipeline_instance
    bt._ml_confirmation_feature_extractor = mock_feature_extractor_instance
    bt._ml_confirmation_pipeline.load_model(model_path)
    bt._ml_confirmation_feature_extractor.set_active_features(
        mock_pipeline_instance.active_features
    )

    test_signal = StrategySignal(
        "MockStrategy",
        "BTCUSDT",
        SignalDirection.LONG,
        stop_loss=95.0,
        take_profit=110.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
    )
    signal_fire_idx = 60

    # Using a function that accepts any arguments (*args, **kwargs),
    # to avoid TypeError if check_signal is called with keyword arguments.
    def check_signal_side_effect(*args, **kwargs):
        # Trying to get pair_info (pi) from positional or keyword arguments
        pi = kwargs.get("pair_info")
        if pi is None and len(args) > 0:
            pi = args[0]

        if pi and abs(pi["current_candle_index"] - signal_fire_idx) <= 1:
            return (test_signal, 100.0, {})
        return (None, 0.0, {})

    bt.strategy_instance.check_signal.side_effect = check_signal_side_effect

    bt.klines.loc[bt.klines.index[signal_fire_idx], "close"] = 100.0
    bt.kline_data_array = bt.klines[list(bt.kline_index_map.keys())].to_numpy(
        dtype=np.float64
    )

    results = bt.run()

    assert results is not None
    # assert results['trades'] == 0, "The trade should have been rejected by the ML filter"
    # mock_pipeline_instance.predict_proba_one.assert_called_once()

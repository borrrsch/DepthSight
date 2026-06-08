# tests/test_trainer.py
import pytest
import pandas as pd
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
from unittest.mock import patch, MagicMock, PropertyMock
import sys

if os.path.basename(os.getcwd()) == "tests":
    sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))
try:
    from bot_module.trainer import Trainer
    from bot_module.strategy import SignalDirection, BaseStrategy
    import bot_module.config as real_config
    from bot_module.trade_logger import TradeLogger as RealTradeLogger
    import optuna
    from bot_module.ml_strategy import OnlineAgentStrategy

    FIELDNAMES = RealTradeLogger.EVENT_LOG_FIELDNAMES
except ImportError as e:
    pytest.skip(
        f"Cannot import bot_module. Ensure tests run from project root or tests dir. Error: {e}",
        allow_module_level=True,
    )


@pytest.fixture
def mock_optuna_config():
    return {
        "n_trials": 5,
        "timeout": 60,
        "n_jobs": 1,
        "direction": "maximize",
        "metric_name": "profit_factor",
        "use_pruning": True,
        "pruner_n_startup_trials": 1,
        "sampler_seed": 123,
        "study_name_prefix": "test_study",
        "storage": None,
    }


@pytest.fixture
def mock_optuna_search_space():
    return {
        "TestStrategyA": {
            "stop_loss_atr_multiplier": ("float", [0.8, 2.5]),
            "take_profit_atr_multiplier": ("float", [1.0, 4.0]),
        },
        "StrategyWithCategorical": {
            "mode": ("categorical", [["MODE_A", "MODE_B"]]),
            "size": ("int", [1, 5]),
        },
        OnlineAgentStrategy.NAME: {},
    }


@pytest.fixture
def trainer_instance(
    tmp_path, monkeypatch, mock_optuna_config, mock_optuna_search_space
):
    log_file = tmp_path / "test_trades.csv"
    opt_file = tmp_path / "test_optimized.json"
    ml_model_file = tmp_path / "test_ml_model.pkl"
    ml_report_file = tmp_path / "test_ml_report.json"
    local_data_dir = tmp_path / "local_historical_csv"
    local_data_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(real_config, "LOG_FILE_TRADES", str(log_file), raising=False)
    monkeypatch.setattr(
        real_config, "OPTIMIZED_PARAMS_FILE", str(opt_file), raising=False
    )
    monkeypatch.setattr(real_config, "TRAINER_DATA_LOOKBACK_DAYS", 5, raising=False)
    monkeypatch.setattr(real_config, "TRAINER_MIN_TRADES_OPTIMIZE", 2, raising=False)
    monkeypatch.setattr(
        real_config, "ML_OFFLINE_TRAINED_MODEL_PATH", str(ml_model_file), raising=False
    )
    monkeypatch.setattr(
        real_config, "ML_TRAINING_REPORT_FILE", str(ml_report_file), raising=False
    )
    monkeypatch.setattr(
        real_config, "TRAINER_OPTIMIZATION_METHOD", "bayesian", raising=False
    )
    monkeypatch.setattr(
        real_config, "TRAINER_OPTUNA_CONFIG", mock_optuna_config, raising=False
    )
    monkeypatch.setattr(
        real_config,
        "TRAINER_OPTUNA_SEARCH_SPACE",
        mock_optuna_search_space,
        raising=False,
    )

    test_strategy_defaults = {
        "TestStrategyA": {
            "enabled": True,
            "stop_loss_atr_multiplier": 1.2,
            "take_profit_atr_multiplier": 1.8,
            "other_param": 10,
            "candle_timeframe": "1m",
        },
        "StrategyWithCategorical": {
            "enabled": True,
            "mode": "MODE_A",
            "size": 3,
            "candle_timeframe": "1m",
        },
        "TestStrategyB": {"enabled": False, "param_b": 5, "candle_timeframe": "1m"},
        "StrategyWithoutATR": {
            "enabled": True,
            "some_other_param": 1,
            "candle_timeframe": "1m",
        },
        OnlineAgentStrategy.NAME: {
            "enabled": True,
            "candle_timeframe": "1m",
            "atr_period": 14,
            "use_offline_model": False,
            "offline_model_path": None,
            "online_model_path": None,
        },
    }
    monkeypatch.setattr(
        real_config, "STRATEGY_DEFAULTS", test_strategy_defaults, raising=False
    )
    monkeypatch.setattr(
        real_config, "TRAINER_TARGET_SYMBOLS", ["BTCUSDT", "ETHUSDT"], raising=False
    )
    monkeypatch.setattr(real_config, "OPTIMIZATION_DATA_OVERLAP_DAYS", 1, raising=False)
    monkeypatch.setattr(real_config, "ML_TRAINING_CHUNK_WEEKS", 0.5, raising=False)
    monkeypatch.setattr(real_config, "ML_TRAINING_OVERLAP_DAYS", 1, raising=False)
    monkeypatch.setattr(real_config, "ML_TRAINING_SIMULATE_TRADES", True, raising=False)
    monkeypatch.setattr(real_config, "USE_LOCAL_HISTORICAL_DATA", False, raising=False)
    monkeypatch.setattr(
        real_config, "LOCAL_HISTORICAL_DATA_PATH", str(local_data_dir), raising=False
    )

    test_param_grid = {
        "TestStrategyA": {
            "stop_loss_atr_multiplier": [1.0, 1.5],
            "take_profit_atr_multiplier": [1.5, 2.0],
        }
    }
    monkeypatch.setattr(
        real_config, "TRAINER_PARAM_GRID", test_param_grid, raising=False
    )
    trainer = Trainer()
    return trainer


@pytest.fixture
def mock_ml_agent_instance(tmp_path):
    agent = MagicMock(spec=OnlineAgentStrategy)
    agent.NAME = OnlineAgentStrategy.NAME
    agent.enabled = True
    agent.candle_timeframe = "1m"
    agent.atr_period = 14
    agent.required_data_types = {"kline_1m", "aggTrade"}
    agent.use_offline_model = False
    agent.offline_model_path = tmp_path / "offline_mock.pkl"
    agent.online_model_path = tmp_path / "online_mock.pkl"
    agent.model_pipeline = MagicMock()

    def reset_pipeline_effect():
        if hasattr(agent.model_pipeline, "steps_processed"):
            agent.model_pipeline.steps_processed = 0
        else:
            agent.model_pipeline.steps_processed = 0
        agent.model_pipeline.learn_one.reset_mock()

    agent.reset_pipeline = MagicMock(side_effect=reset_pipeline_effect)
    agent.load_pipeline_model = MagicMock(return_value=True)
    agent.save_pipeline_model = MagicMock()

    if not hasattr(agent.model_pipeline, "steps_processed"):
        agent.model_pipeline.steps_processed = 0
    return agent


@pytest.fixture
def sample_log_data_dict():
    now = datetime.now(timezone.utc)
    data = [
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "BTCUSDT",
            "strategy": "TestStrategyA",
            "direction": "LONG",
            "entry_price": "50000.0",
            "exit_price": "50500.0",
            "quantity": "0.01",
            "initial_stop_loss": "49700.0",
            "initial_take_profit": "50600.0",
            "entry_atr": "200.0",
            "trigger_price": "50000.0",
            "pnl": "5.0",
            "commission": "0.1",
        },
        {
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "BTCUSDT",
            "strategy": "TestStrategyA",
            "direction": "LONG",
            "entry_price": "51000.0",
            "exit_price": "50800.0",
            "quantity": "0.01",
            "initial_stop_loss": "50700.0",
            "initial_take_profit": "51300.0",
            "entry_atr": "200.0",
            "trigger_price": "51000.0",
            "pnl": "-2.0",
            "commission": "0.1",
        },
        {
            "timestamp": (now - timedelta(days=3)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "BTCUSDT",
            "strategy": "TestStrategyA",
            "direction": "SHORT",
            "entry_price": "52000.0",
            "exit_price": "51500.0",
            "quantity": "0.01",
            "initial_stop_loss": "52300.0",
            "initial_take_profit": "51400.0",
            "entry_atr": "200.0",
            "trigger_price": "52000.0",
            "pnl": "5.0",
            "commission": "0.1",
        },
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "ETHUSDT",
            "strategy": "TestStrategyB",
            "direction": "LONG",
            "entry_price": "3000.0",
            "exit_price": "3030.0",
            "quantity": "0.1",
            "pnl": "3.0",
            "commission": "0.05",
        },
        {
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "ETHUSDT",
            "strategy": "TestStrategyB",
            "direction": "SHORT",
            "entry_price": "3100.0",
            "exit_price": "3110.0",
            "quantity": "0.1",
            "pnl": "-1.0",
            "commission": "0.05",
        },
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "LTCUSDT",
            "strategy": "StrategyWithCategorical",
            "direction": "LONG",
            "entry_price": "150.0",
            "exit_price": "151.0",
            "quantity": "1.0",
            "pnl": "1.0",
            "commission": "0.02",
        },
        {
            "timestamp": (now - timedelta(days=10)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "BTCUSDT",
            "strategy": "TestStrategyA",
            "direction": "LONG",
            "entry_price": "45000.0",
            "exit_price": "45100.0",
            "quantity": "0.01",
            "pnl": "1.0",
            "commission": "0.1",
        },
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "event_type": "SIGNAL_APPROVED",
            "symbol": "BTCUSDT",
            "strategy": "TestStrategyA",
        },
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "event_type": "POSITION_CLOSED",
            "symbol": "DOGEUSDT",
            "strategy": "TestStrategyA",
            "direction": "LONG",
            "entry_price": "0.150",
            "exit_price": "0.151",
            "quantity": "100.0",
            "pnl": "0.1",
            "commission": "0.01",
        },
    ]
    full_data = []
    for row_dict in data:
        full_data.append({field: row_dict.get(field, None) for field in FIELDNAMES})
    return full_data


@pytest.fixture
def create_dummy_log_file(tmp_path, sample_log_data_dict):
    log_file = tmp_path / "test_trades.csv"
    header = ",".join(FIELDNAMES)
    rows = [header]
    for record in sample_log_data_dict:
        rows.append(",".join(str(record.get(field, "")) for field in FIELDNAMES))
    log_file.write_text("\n".join(rows), encoding="utf-8")
    return str(log_file)


def test_trainer_initialization_optuna(
    trainer_instance, tmp_path, mock_optuna_config, mock_optuna_search_space
):
    assert trainer_instance.optimization_method == "bayesian"
    assert trainer_instance.optuna_config == mock_optuna_config
    assert trainer_instance.optuna_search_space == mock_optuna_search_space


def test_load_optimized_params_file_not_found(trainer_instance):
    assert trainer_instance._load_optimized_params() == {}


def test_save_and_load_optimized_params(trainer_instance):
    params_to_save = {"TestStrategyA": {"stop_loss_atr_multiplier": 1.1}}
    trainer_instance._save_optimized_params(params_to_save)
    loaded_params = trainer_instance._load_optimized_params()
    assert loaded_params["TestStrategyA"]["stop_loss_atr_multiplier"] == 1.1
    more_params = {"TestStrategyB": {"some_other_param": 5}}
    trainer_instance._save_optimized_params(more_params)
    reloaded_params = trainer_instance._load_optimized_params()
    assert reloaded_params["TestStrategyA"]["stop_loss_atr_multiplier"] == 1.1
    assert reloaded_params["TestStrategyB"]["some_other_param"] == 5


def test_load_trade_logs_not_found(trainer_instance):
    assert trainer_instance._load_trade_logs() is None


def test_load_trade_logs_empty(trainer_instance, tmp_path):
    log_file = tmp_path / "test_trades.csv"
    log_file.write_text(",".join(FIELDNAMES), encoding="utf-8")
    df_logs = trainer_instance._load_trade_logs()
    assert df_logs is None or df_logs.empty


def test_load_trade_logs_valid(trainer_instance, create_dummy_log_file):
    trainer_instance.log_file = Path(create_dummy_log_file)
    df = trainer_instance._load_trade_logs()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 7
    assert "timestamp" in df.columns and pd.api.types.is_datetime64_any_dtype(
        df["timestamp"]
    )
    assert "pnl" in df.columns and pd.api.types.is_numeric_dtype(df["pnl"])
    assert not df["pnl"].isnull().any()


@pytest.mark.parametrize(
    "direction, entry, exit_actual, sl_init, tp_init, atr_entry, sl_mult_new, tp_mult_new, expected_pnl",
    [
        (SignalDirection.LONG, 100.0, 103.0, 98.0, 104.0, 2.0, 1.5, 2.0, 3.0),
        (SignalDirection.LONG, 100.0, 105.0, 98.0, 104.0, 2.0, 1.5, 2.0, 4.0),
        (SignalDirection.LONG, 100.0, 96.0, 98.0, 104.0, 2.0, 1.5, 2.0, -3.0),
        (SignalDirection.SHORT, 100.0, 97.0, 102.0, 96.0, 2.0, 1.5, 2.0, 3.0),
        (SignalDirection.SHORT, 100.0, 95.0, 102.0, 96.0, 2.0, 1.5, 2.0, 4.0),
        (SignalDirection.SHORT, 100.0, 104.0, 102.0, 96.0, 2.0, 1.5, 2.0, -3.0),
    ],
)
def test_simulate_trade_outcome(
    trainer_instance,
    direction,
    entry,
    exit_actual,
    sl_init,
    tp_init,
    atr_entry,
    sl_mult_new,
    tp_mult_new,
    expected_pnl,
):
    trade_data = pd.Series(
        {
            "entry_price": entry,
            "exit_price": exit_actual,
            "quantity": 1.0,
            "direction_enum": direction,
            "pnl": (exit_actual - entry)
            if direction == SignalDirection.LONG
            else (entry - exit_actual),
            "entry_atr": atr_entry,
            "initial_stop_loss": sl_init,
            "initial_take_profit": tp_init,
            "trigger_price": entry,
            "strategy": "TestSim",
        }
    )
    new_params = {
        "stop_loss_atr_multiplier": sl_mult_new,
        "take_profit_atr_multiplier": tp_mult_new,
    }
    simulated_pnl = trainer_instance._simulate_trade_outcome(trade_data, new_params)
    assert math.isclose(simulated_pnl, expected_pnl, rel_tol=1e-7)


def test_calculate_kpis_actual(trainer_instance, create_dummy_log_file):
    trainer_instance.log_file = Path(create_dummy_log_file)
    df = trainer_instance._load_trade_logs()
    kpis_by_strategy = trainer_instance._calculate_kpis(df)
    assert "TestStrategyA" in kpis_by_strategy
    assert kpis_by_strategy["TestStrategyA"]["trades"] == 4
    assert math.isclose(kpis_by_strategy["TestStrategyA"]["total_pnl"], 8.1)
    assert "TestStrategyB" in kpis_by_strategy
    assert kpis_by_strategy["TestStrategyB"]["trades"] == 2
    assert math.isclose(kpis_by_strategy["TestStrategyB"]["total_pnl"], 2.0)
    assert "StrategyWithCategorical" in kpis_by_strategy
    assert kpis_by_strategy["StrategyWithCategorical"]["trades"] == 1
    assert math.isclose(kpis_by_strategy["StrategyWithCategorical"]["total_pnl"], 1.0)


def test_calculate_kpis_simulated(trainer_instance):
    sim_data = pd.DataFrame(
        {
            "strategy": ["SimStrat"] * 5,
            "pnl": [10.0, -5.0, 8.0, -3.0, -2.0],
            "entry_price": [100] * 5,
            "exit_price": [101] * 5,
            "quantity": [1] * 5,
            "direction_enum": [SignalDirection.LONG] * 5,
            "symbol": ["BTCUSDT"] * 5,
        }
    )
    kpis = trainer_instance._calculate_kpis_simulated(sim_data, {})
    assert kpis["trades"] == 5
    assert math.isclose(kpis["total_pnl"], 8.0)
    assert math.isclose(kpis["profit_factor"], 1.8)
    assert kpis["max_consecutive_losses"] == 2


@pytest.fixture(scope="module")
def mock_exchange_info():
    symbol = "BTCUSDT"
    return {
        symbol: {
            "symbol": symbol,
            "status": "TRADING",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {
                    "filterType": "LOT_SIZE",
                    "stepSize": "0.00001",
                    "minQty": "0.00001",
                    "maxQty": "9000.0",
                },
                {"filterType": "NOTIONAL", "minNotional": "10.0"},
            ],
            "lot_params": {"minQty": 0.00001, "maxQty": 9000.0, "stepSize": 0.00001},
            "min_notional": 10.0,
            "tick_size": 0.01,
        },
        "ETHUSDT": {
            "symbol": "ETHUSDT",
            "status": "TRADING",
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {
                    "filterType": "LOT_SIZE",
                    "stepSize": "0.001",
                    "minQty": "0.001",
                    "maxQty": "90000.0",
                },
                {"filterType": "NOTIONAL", "minNotional": "10.0"},
            ],
            "lot_params": {"minQty": 0.001, "maxQty": 90000.0, "stepSize": 0.001},
            "min_notional": 10.0,
            "tick_size": 0.01,
        },
    }


@pytest.fixture
def mock_trial():
    trial = MagicMock(spec=optuna.Trial)
    trial.number = 0
    trial.suggest_float.side_effect = lambda name, low, high, step=None, log=False: (
        (low + high) / 2
    )
    trial.suggest_int.side_effect = lambda name, low, high, step=1, log=False: (
        (low + high) // 2
    )
    trial.suggest_categorical.side_effect = lambda name, choices: choices[0]
    return trial


@patch("bot_module.trainer.DepthSightBacktester")
def test_global_optuna_objective_success(
    MockBacktester, trainer_instance, mock_trial, mock_optuna_config
):
    from bot_module.trainer import _optuna_objective_global

    strategy_name = "TestStrategyA"
    suggested_params = {
        "stop_loss_atr_multiplier": 1.5,
        "take_profit_atr_multiplier": 2.0,
    }
    mock_historical_data = {"kline_1m": pd.DataFrame({"close": [100, 101]})}
    mock_initial_balance = 10000.0
    mock_base_config_params = {"candle_timeframe": "1m", "other_param": 10}
    mock_symbol = "BTCUSDT"
    mock_exchange_info_all_symbols = {"BTCUSDT": {"tick_size": 0.01}}
    mock_min_trades = trainer_instance.min_trades_for_optimization
    mock_backtester_execution_config = trainer_instance.backtest_execution_config
    mock_strategy_defaults = trainer_instance.strategy_defaults
    mock_optuna_study_config = mock_optuna_config
    mock_actual_start_dt = datetime.now(timezone.utc) - timedelta(days=1)
    mock_backtester_instance = MockBacktester.return_value
    expected_kpis = {
        "trades": mock_min_trades + 1,
        "profit_factor": 2.5,
        "total_pnl": 8.0,
    }
    mock_backtester_instance.run.return_value = expected_kpis

    kwargs_for_objective = {
        "params": suggested_params,
        "strategy_name": strategy_name,
        "historical_data": mock_historical_data,
        "initial_balance": mock_initial_balance,
        "base_config": mock_base_config_params,
        "symbol": mock_symbol,
        "exchange_info_all_symbols": mock_exchange_info_all_symbols,
        "min_trades_required": mock_min_trades,
        "backtester_execution_config": mock_backtester_execution_config,
        "strategy_defaults_all": mock_strategy_defaults,
        "optuna_study_config": mock_optuna_study_config,
        "actual_start_dt_for_backtest": mock_actual_start_dt,
        "log_ml_confirmation_data_flag": False,
        "ml_confirmation_data_log_path": None,
        "y_true_min_move_pct_val": 0.15,
        "y_true_max_drawdown_pct_val": 0.10,
        "enable_ml_confirmation_during_backtest": False,
        "ml_confirmation_model_path_override_val": None,
    }
    metric_value = _optuna_objective_global(trial=mock_trial, **kwargs_for_objective)

    MockBacktester.assert_called_once()
    called_kwargs = MockBacktester.call_args[1]
    assert called_kwargs["exchange_info"] == mock_exchange_info_all_symbols.get(
        mock_symbol, {}
    )
    mock_backtester_instance.run.assert_called_once()
    assert metric_value == expected_kpis["profit_factor"]


@patch("bot_module.trainer._load_data_for_process")
@patch("bot_module.trainer.Trainer._get_exchange_info")
@patch("bot_module.trainer.BayesianOptimizer")
def test_run_bayesian_optimization_calls(
    MockOptimizer,
    MockGetExchangeInfo,
    MockLoadDataProcess,
    trainer_instance,
    create_dummy_log_file,
    mock_optuna_search_space,
    mock_exchange_info,
    mock_optuna_config,
):
    trainer_instance.log_file = Path(create_dummy_log_file)
    MockGetExchangeInfo.return_value = mock_exchange_info
    mock_klines_btc = {"kline_1m": pd.DataFrame({"close": [100, 101, 102, 103, 104]})}
    mock_klines_eth = {"kline_1m": pd.DataFrame({"close": [2000, 2010, 2020]})}

    def load_data_side_effect(
        symbol,
        backtest_start_dt,
        backtest_end_dt,
        overlap_days,
        required_data_types,
        use_local_data,
        local_data_path,
    ):
        if symbol == "BTCUSDT":
            return mock_klines_btc
        if symbol == "ETHUSDT":
            return mock_klines_eth
        return {}

    MockLoadDataProcess.side_effect = load_data_side_effect
    mock_optimizer_instance = MockOptimizer.return_value
    mock_optimizer_instance.optimize.return_value = {
        "stop_loss_atr_multiplier": 1.1,
        "take_profit_atr_multiplier": 2.2,
    }
    mock_optimizer_instance.best_value = 3.14
    mock_optimizer_instance._config = trainer_instance.optuna_config
    results = trainer_instance.run_bayesian_optimization()
    MockGetExchangeInfo.assert_called_once()
    assert MockLoadDataProcess.call_count == 2
    expected_optimizer_calls = 2 * 2
    assert MockOptimizer.call_count == expected_optimizer_calls
    assert mock_optimizer_instance.optimize.call_count == expected_optimizer_calls
    assert "TestStrategyA" in results
    assert results["TestStrategyA"]["stop_loss_atr_multiplier"] == 1.1
    assert "StrategyWithCategorical" in results
    assert "TestStrategyB" not in results
    assert OnlineAgentStrategy.NAME not in results


@patch("bot_module.trainer._load_data_for_process")
@patch("bot_module.trainer.Trainer._get_exchange_info")
@patch("bot_module.trainer.BayesianOptimizer")
def test_run_bayesian_optimization_no_results(
    MockOptimizer,
    MockGetExchangeInfo,
    MockLoadDataProcess,
    trainer_instance,
    create_dummy_log_file,
    mock_exchange_info,
):
    trainer_instance.log_file = Path(create_dummy_log_file)
    MockGetExchangeInfo.return_value = mock_exchange_info
    mock_klines = {"kline_1m": pd.DataFrame({"close": [100, 101]})}
    MockLoadDataProcess.return_value = mock_klines
    mock_optimizer_instance = MockOptimizer.return_value
    mock_optimizer_instance.optimize.return_value = None
    results = trainer_instance.run_bayesian_optimization()
    MockGetExchangeInfo.assert_called_once()
    assert MockLoadDataProcess.call_count == 2
    expected_optimizer_calls = 2 * 2
    assert MockOptimizer.call_count == expected_optimizer_calls
    assert mock_optimizer_instance.optimize.call_count == expected_optimizer_calls
    assert not results


@patch("bot_module.trainer.Trainer.run_bayesian_optimization")
@patch("bot_module.trainer.Trainer.run_ml_agent_training")
def test_run_training_cycle_modes(
    mock_run_ml, mock_run_opt, trainer_instance, create_dummy_log_file
):
    trainer_instance.log_file = Path(create_dummy_log_file)
    mock_run_opt.reset_mock()
    mock_run_ml.reset_mock()
    best_optuna_params = {"TestStrategyA": {"stop_loss_atr_multiplier": 1.99}}
    mock_run_opt.return_value = best_optuna_params
    with patch.object(trainer_instance, "_save_optimized_params") as mock_save:
        trainer_instance.run_training_cycle(mode="optimize")
        mock_run_opt.assert_called_once()
        mock_run_ml.assert_not_called()
        mock_save.assert_called_once_with(best_optuna_params)
    mock_run_opt.reset_mock()
    mock_run_ml.reset_mock()
    with patch.object(trainer_instance, "_save_optimized_params") as mock_save:
        trainer_instance.run_training_cycle(mode="train_ml")
        mock_run_opt.assert_not_called()
        mock_run_ml.assert_called_once()
        mock_save.assert_not_called()
    mock_run_opt.reset_mock()
    mock_run_ml.reset_mock()
    with patch.object(trainer_instance, "_save_optimized_params") as mock_save:
        trainer_instance.run_training_cycle(mode="invalid_mode")
        mock_run_opt.assert_not_called()
        mock_run_ml.assert_not_called()
        mock_save.assert_not_called()


def test_run_grid_search(trainer_instance, create_dummy_log_file, monkeypatch):
    trainer_instance.optimization_method = "grid"
    trainer_instance.log_file = Path(create_dummy_log_file)
    df = trainer_instance._load_trade_logs()

    def mock_simulate(trade_data, params):
        sl = params.get("stop_loss_atr_multiplier", 0)
        tp = params.get("take_profit_atr_multiplier", 0)
        if sl == 1.5 and tp == 2.0:
            return trade_data["pnl"] * 1.1
        elif sl == 1.0 and tp == 1.5:
            return trade_data["pnl"] * 0.9
        else:
            return trade_data["pnl"] * 0.95

    monkeypatch.setattr(trainer_instance, "_simulate_trade_outcome", mock_simulate)
    best_params = trainer_instance.run_grid_search(df)
    assert "TestStrategyA" in best_params
    assert best_params["TestStrategyA"]["stop_loss_atr_multiplier"] == 1.5
    assert best_params["TestStrategyA"]["take_profit_atr_multiplier"] == 2.0
    assert "TestStrategyB" not in best_params


@patch("bot_module.trainer._load_data_for_process")
@patch("bot_module.trainer.Trainer._get_exchange_info")
@patch("bot_module.trainer.DepthSightBacktester")
@patch("bot_module.trainer.get_strategy_instance")
@patch("bot_module.trainer.calculate_kpis_from_sim_log_standalone")
def test_run_ml_agent_training_calls(
    mock_calculate_kpis,
    mock_get_instance,
    MockBacktester,
    MockGetExchangeInfo,
    MockLoadDataProcess,
    trainer_instance,
    mock_exchange_info,
    mock_ml_agent_instance,
):
    MockGetExchangeInfo.return_value = mock_exchange_info

    fixed_now = datetime(2025, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
    source_kline_start_dt = fixed_now - timedelta(days=10)
    num_kline_points = 10 * 24 * 60
    mock_source_klines_df = pd.DataFrame(
        {"close": [100 + i / 10.0 for i in range(num_kline_points)]},
        index=pd.to_datetime(
            pd.date_range(
                start=source_kline_start_dt, periods=num_kline_points, freq="1min"
            )
        ),
    )
    num_agg_points = 10 * 24 * 60 * 60
    mock_source_agg_df = pd.DataFrame(
        {
            "price": [100.1 + i / 100.0 for i in range(num_agg_points)],
            "quantity": [0.1] * num_agg_points,
            "is_buyer_maker": [True] * num_agg_points,
        },
        index=pd.to_datetime(
            pd.date_range(
                start=source_kline_start_dt, periods=num_agg_points, freq="1s"
            )
        ),
    )

    # Stub function for the data loader
    def load_data_side_effect(
        symbol_arg,
        backtest_start_dt_arg,
        backtest_end_dt_arg,
        overlap_days_arg,
        required_data_types_arg,
        use_local_data_arg,
        local_data_path_arg,
    ):
        result_data = {}
        # Defining the start point for data to avoid NaT
        first_kline_date = mock_source_klines_df[
            mock_source_klines_df.index >= backtest_start_dt_arg
        ].index.min()
        actual_start = first_kline_date
        if "aggTrade" in required_data_types_arg:
            first_agg_date = mock_source_agg_df[
                mock_source_agg_df.index >= backtest_start_dt_arg
            ].index.min()
            if pd.notna(first_agg_date):
                actual_start = max(first_kline_date, first_agg_date)

        for req_type in required_data_types_arg:
            if req_type.startswith("kline_"):
                load_start = actual_start - timedelta(days=overlap_days_arg)
                df = mock_source_klines_df[
                    (mock_source_klines_df.index >= load_start)
                    & (mock_source_klines_df.index < backtest_end_dt_arg)
                ]
                result_data[req_type] = df[df.index >= actual_start].copy()
            elif req_type == "aggTrade":
                result_data[req_type] = mock_source_agg_df[
                    (mock_source_agg_df.index >= actual_start)
                    & (mock_source_agg_df.index < backtest_end_dt_arg)
                ].copy()
        return result_data

    MockLoadDataProcess.side_effect = load_data_side_effect

    def get_instance_side_effect(strategy_name_arg):
        if strategy_name_arg == OnlineAgentStrategy.NAME:
            mock_ml_agent_instance.reset_pipeline()
            prop_mock = PropertyMock(
                return_value={
                    "kline_1m",
                    "aggTrade",
                    "kline_1h",
                    "kline_4h",
                    "kline_1d",
                }
            )
            type(mock_ml_agent_instance).required_data_types = prop_mock
            return mock_ml_agent_instance

        mock_other_strat = MagicMock(spec=BaseStrategy, NAME=strategy_name_arg)
        other_prop_mock = PropertyMock(return_value={"kline_1m"})
        type(mock_other_strat).required_data_types = other_prop_mock
        return mock_other_strat

    mock_get_instance.side_effect = get_instance_side_effect

    mock_backtester_instance = MockBacktester.return_value
    single_chunk_run_result = {
        "training_data": [{"raw_features": {"f1": 0.1}, "y_true": 1}] * 10,
        "ml_steps_processed": 10,
    }
    mock_backtester_instance.run.return_value = single_chunk_run_result
    mock_backtester_instance._ml_simulated_trade_log = [
        {
            "pnl": 1.0,
            "commission": 0.1,
            "symbol": "ANY",
            "strategy": OnlineAgentStrategy.NAME,
            "ml_steps_processed": 10,
        }
    ]

    original_defaults = trainer_instance.strategy_defaults.copy()
    trainer_instance.strategy_defaults[OnlineAgentStrategy.NAME] = {
        "enabled": True,
        "candle_timeframe": "1m",
        "atr_period": 14,
        "use_offline_model": False,
        "offline_model_path": "mock_offline.pkl",
        "online_model_path": "mock_online.pkl",
    }

    datetime_original_class = datetime

    with (
        patch(
            "bot_module.trainer.datetime", new_callable=MagicMock
        ) as mock_datetime_class,
        patch("pathlib.Path.exists", return_value=True),
    ):
        mock_datetime_class.now.return_value = fixed_now
        mock_datetime_class.side_effect = lambda *args, **kwargs: (
            datetime_original_class(*args, **kwargs)
        )
        mock_datetime_class.strptime = datetime_original_class.strptime
        mock_datetime_class.fromisoformat = datetime_original_class.fromisoformat
        mock_datetime_class.combine = datetime_original_class.combine
        mock_datetime_class.timedelta = timedelta
        mock_datetime_class.timezone = timezone
        mock_datetime_class.min = datetime_original_class.min
        mock_datetime_class.max = datetime_original_class.max

        trainer_instance.run_ml_agent_training()

    # Checking that simulation KPIs were calculated for EVERY symbol.
    # The number of calls must be equal to the number of symbols in the config.
    num_symbols = len(getattr(real_config, "TRAINER_TARGET_SYMBOLS", []))
    assert mock_calculate_kpis.call_count == num_symbols

    # Ensure that key mocks were called
    assert MockLoadDataProcess.call_count > 0
    MockBacktester.assert_called()

    # Returning the original defaults
    trainer_instance.strategy_defaults = original_defaults


@patch("bot_module.trainer._load_data_for_process")
@patch("bot_module.trainer.Trainer._get_exchange_info")
@patch("bot_module.trainer.DepthSightBacktester")
@patch("bot_module.trainer.get_strategy_instance")
def test_run_ml_agent_training_disabled(
    mock_get_instance,
    MockBacktester,
    MockGetExchangeInfo,
    MockLoadData,
    trainer_instance,
):
    original_defaults = trainer_instance.strategy_defaults.copy()
    if OnlineAgentStrategy.NAME in trainer_instance.strategy_defaults:
        trainer_instance.strategy_defaults[OnlineAgentStrategy.NAME]["enabled"] = False
    else:
        trainer_instance.strategy_defaults[OnlineAgentStrategy.NAME] = {
            "enabled": False
        }

    trainer_instance.run_ml_agent_training()

    MockGetExchangeInfo.assert_not_called()
    MockLoadData.assert_not_called()
    # get_strategy_instance is called to check required_data_types before early exit,
    # therefore we cannot claim that it will not be called. Instead, let's check that
    # "deeper" functions are not called.
    # mock_get_instance.assert_not_called()
    MockBacktester.assert_not_called()

    trainer_instance.strategy_defaults = original_defaults


@patch("bot_module.trainer.Trainer.run_bayesian_optimization")
def test_run_training_cycle_bayesian(
    mock_run_opt, trainer_instance, create_dummy_log_file
):
    trainer_instance.log_file = Path(create_dummy_log_file)
    trainer_instance.optimization_method = "bayesian"
    best_optuna_params = {
        "TestStrategyA": {
            "stop_loss_atr_multiplier": 1.99,
            "take_profit_atr_multiplier": 3.55,
        }
    }
    mock_run_opt.return_value = best_optuna_params
    if trainer_instance.optimized_params_file.exists():
        trainer_instance.optimized_params_file.unlink()
    trainer_instance.optimized_params = {}
    with patch.object(
        trainer_instance,
        "_save_optimized_params",
        wraps=trainer_instance._save_optimized_params,
    ) as patched_save_method:
        trainer_instance.run_training_cycle()
        mock_run_opt.assert_called_once()
        patched_save_method.assert_called_once()
        assert patched_save_method.call_args[0][0] == best_optuna_params
    reloaded_params = trainer_instance._load_optimized_params()
    assert "TestStrategyA" in reloaded_params
    assert math.isclose(
        reloaded_params["TestStrategyA"]["stop_loss_atr_multiplier"], 1.99
    )

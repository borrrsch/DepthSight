# tests/test_genetic_search_e2e.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from tasks import run_genetic_search_task
from api import models


@pytest.fixture
def mock_run_config():
    """Configuration for the genetic search run."""
    return {
        "name": "E2E Test Run",
        "target_symbols": ["BTCUSDT"],
        "main_timeframe": "1h",
        "data_start_date": "2023-01-01T00:00:00Z",
        "data_end_date": "2023-01-31T23:59:59Z",
        "population_size": 10,
        "generations": 3,
        "hof_size_to_save": 3,
    }


@pytest.fixture
def sample_klines_df():
    """Simple DataFrame to mock data loading."""
    dates = pd.to_datetime(
        pd.date_range(start="2023-01-01", end="2023-02-01", freq="1h")
    )
    data = {
        "open": [100 + i for i in range(len(dates))],
        "high": [102 + i for i in range(len(dates))],
        "low": [98 + i for i in range(len(dates))],
        "close": [101 + i for i in range(len(dates))],
        "volume": [1000 + i * 10 for i in range(len(dates))],
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "open_time"
    return df


@pytest.mark.anyio
async def test_e2e_genetic_search_flow_with_db_mocked(
    mock_run_config, sample_klines_df
):
    """
    End-to-end integration test for the genetic search process,
    with the database layer (crud) fully mocked.
    """
    mock_hof_results = [
        {
            "rank": 1,
            "fitness_score": 2.5,
            "strategy_json": {
                "entryConditions": {
                    "type": "AND",
                    "children": [{"type": "rsi_condition", "params": {"value": 70}}],
                }
            },
            "kpis_json": {
                "total_trades": 50,
                "profit_factor": 2.5,
                "total_pnl_pct": 25.0,
            },
        },
        {
            "rank": 2,
            "fitness_score": 1.8,
            "strategy_json": {
                "entryConditions": {
                    "type": "AND",
                    "children": [{"type": "ma_cross_condition", "params": {}}],
                }
            },
            "kpis_json": {
                "total_trades": 30,
                "profit_factor": 1.8,
                "total_pnl_pct": 15.0,
            },
        },
    ]
    mock_run_backtest_task = MagicMock()

    run_id_to_check = str(uuid4())
    user_id = 1

    mock_db_run_instance = MagicMock(spec=models.GeneticRun)
    mock_db_run_instance.id = run_id_to_check
    mock_db_run_instance.config_json = mock_run_config
    mock_db_run_instance.status = "PENDING"
    mock_db_run_instance.progress = {}

    # Removing autospec=True so that the mock does not check the constructor arguments,
    # as they are not yet updated in the code under test (tasks.py).
    gsf_class_patcher = patch("tasks.GeneticStrategyFinder")
    data_patcher = patch(
        "tasks.download_klines", new_callable=AsyncMock, return_value=sample_klines_df
    )
    backtest_task_patcher = patch("tasks.run_backtest_task", new=mock_run_backtest_task)

    crud_get_patcher = patch(
        "tasks.crud.get_genetic_run",
        new_callable=AsyncMock,
        return_value=mock_db_run_instance,
    )
    crud_create_strategy_patcher = patch(
        "tasks.crud.create_found_strategy", new_callable=AsyncMock
    )

    session_factory_patcher = patch("tasks.get_session_for_worker")

    flag_modified_patcher = patch("tasks.flag_modified")

    with (
        session_factory_patcher as mock_get_session_factory,
        data_patcher,
        gsf_class_patcher as mock_gsf_class,
        backtest_task_patcher,
        crud_get_patcher as mock_get_run,
        crud_create_strategy_patcher as mock_create_strategy,
        flag_modified_patcher,
    ):
        mock_finder_instance = mock_gsf_class.return_value
        mock_finder_instance.run.return_value = mock_hof_results

        mock_async_session = AsyncMock()
        mock_async_session.get = AsyncMock(return_value=mock_db_run_instance)

        mock_session_factory_instance = MagicMock()
        mock_session_factory_instance.return_value.__aenter__.return_value = (
            mock_async_session
        )
        mock_get_session_factory.return_value = mock_session_factory_instance

        result = run_genetic_search_task(run_id=run_id_to_check, user_id=user_id)

        assert result is not None
        assert result["status"] == "COMPLETED"

        mock_get_run.assert_awaited_once()
        assert mock_get_run.await_args.args[0] is mock_async_session

        assert mock_create_strategy.await_count == len(mock_hof_results)

        mock_async_session.commit.assert_awaited()

        assert mock_db_run_instance.status == "COMPLETED"

        assert mock_run_backtest_task.delay.call_count == len(mock_hof_results)

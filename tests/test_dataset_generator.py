from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from bot_module.dataset_generator import DatasetGenerator


pytestmark = pytest.mark.asyncio


def _run_params() -> dict:
    return {
        "symbols": ["BTCUSDT"],
        "start_date": "2024-01-01T00:00:00+00:00",
        "end_date": "2024-01-02T00:00:00+00:00",
    }


async def test_dataset_generator_flattens_raw_features_into_training_frame():
    historical_data = {
        "kline_1m": pd.DataFrame({"close": [100.0, 101.0]}),
    }
    training_data = [
        {
            "timestamp_signal": "2024-01-01T00:00:00Z",
            "strategy": "OnlineAgentStrategy",
            "y_true": 1,
            "raw_features_json": {"rsi": 55.0, "natr": 1.2},
        }
    ]

    with (
        patch("bot_module.dataset_generator.Trainer") as MockTrainer,
        patch("bot_module.dataset_generator.OnlineAgentStrategy") as MockStrategy,
        patch("bot_module.dataset_generator.DepthSightBacktester") as MockBacktester,
    ):
        MockTrainer.return_value._load_historical_data = AsyncMock(
            return_value=historical_data
        )
        strategy = MagicMock()
        strategy.required_data_types = {"kline_1m"}
        MockStrategy.NAME = "OnlineAgentStrategy"
        MockStrategy.return_value = strategy
        MockBacktester.return_value.run_async = AsyncMock(
            return_value={"training_data": training_data}
        )

        df, feature_names = await DatasetGenerator(_run_params(), user_id=1).generate()

    assert list(df["rsi"]) == [55.0]
    assert list(df["natr"]) == [1.2]
    assert "raw_features_json" not in df.columns
    assert set(feature_names) == {"rsi", "natr"}


async def test_dataset_generator_returns_empty_dataset_when_backtester_has_no_examples():
    with (
        patch("bot_module.dataset_generator.Trainer") as MockTrainer,
        patch("bot_module.dataset_generator.OnlineAgentStrategy") as MockStrategy,
        patch("bot_module.dataset_generator.DepthSightBacktester") as MockBacktester,
    ):
        MockTrainer.return_value._load_historical_data = AsyncMock(
            return_value={"kline_1m": pd.DataFrame({"close": [100.0]})}
        )
        strategy = MagicMock()
        strategy.required_data_types = {"kline_1m"}
        MockStrategy.NAME = "OnlineAgentStrategy"
        MockStrategy.return_value = strategy
        MockBacktester.return_value.run_async = AsyncMock(
            return_value={"training_data": []}
        )

        df, feature_names = await DatasetGenerator(_run_params(), user_id=1).generate()

    assert df.empty
    assert feature_names == []


async def test_dataset_generator_returns_none_when_history_is_missing():
    with (
        patch("bot_module.dataset_generator.Trainer") as MockTrainer,
        patch("bot_module.dataset_generator.OnlineAgentStrategy") as MockStrategy,
    ):
        MockTrainer.return_value._load_historical_data = AsyncMock(return_value={})
        strategy = MagicMock()
        strategy.required_data_types = {"kline_1m"}
        MockStrategy.return_value = strategy

        df, feature_names = await DatasetGenerator(_run_params(), user_id=1).generate()

    assert df is None
    assert feature_names is None

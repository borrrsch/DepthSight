import pytest
import time
from bot_module.strategy import VisualBuilderStrategy


@pytest.fixture
def hybrid_config():
    return {
        "entryConditions": {
            "id": "root",
            "type": "AND",
            "children": [
                {
                    "id": "tv_signal_1",
                    "type": "tradingview_signal",
                    "params": {
                        "signal_id": "test_signal",
                        "ttl_seconds": 60,
                        "weight": 60.0,
                    },
                },
                {
                    "id": "rsi_block",
                    "type": "rsi_condition",
                    "params": {"period": 14, "operator": ">", "value": 30},
                },
            ],
        },
        "min_total_foundation_weight_threshold": 50.0,
    }


def test_hybrid_signal_weight_extraction(hybrid_config):
    params = {"config": hybrid_config}
    strategy = VisualBuilderStrategy(params=params)

    # Check if weight was extracted correctly
    assert "test_signal" in strategy.foundation_weights
    assert strategy.foundation_weights["test_signal"] == 60.0


def test_hybrid_signal_evaluation(hybrid_config):
    params = {"config": hybrid_config}
    strategy = VisualBuilderStrategy(params=params)

    pair_info = {"last_price": 100, "is_backtest_mode": False}
    market_data = {
        "kline_1m": None  # Simulating minimal data
    }

    # Mocking RSI checker to return True
    strategy.condition_checkers["rsi_condition"] = lambda **kwargs: (True, {})

    # 1. No signal registered yet
    res, trace = strategy._evaluate_condition_tree(
        hybrid_config["entryConditions"], pair_info, market_data, None
    )
    # The tv_signal_1 node should be False
    tv_node = VisualBuilderStrategy.find_block_in_trace(trace, "tv_signal_1")
    assert tv_node["result"] is False

    # 2. Register signal
    strategy.register_tv_signal("test_signal", 60)
    res, trace = strategy._evaluate_condition_tree(
        hybrid_config["entryConditions"], pair_info, market_data, None
    )
    tv_node = VisualBuilderStrategy.find_block_in_trace(trace, "tv_signal_1")
    assert tv_node["result"] is True

    # 3. Check backtest mode override
    pair_info["is_backtest_mode"] = True
    res, trace = strategy._evaluate_condition_tree(
        hybrid_config["entryConditions"], pair_info, market_data, None
    )
    tv_node = VisualBuilderStrategy.find_block_in_trace(trace, "tv_signal_1")
    assert tv_node["result"] is False


def test_hybrid_signal_expiry(hybrid_config):
    params = {"config": hybrid_config}
    strategy = VisualBuilderStrategy(params=params)
    pair_info = {"last_price": 100, "is_backtest_mode": False}
    market_data = {}

    # Register with very short TTL
    strategy.register_tv_signal("test_signal", 1)

    # Should be active now
    res, trace = strategy._evaluate_condition_tree(
        hybrid_config["entryConditions"], pair_info, market_data, None
    )
    assert (
        VisualBuilderStrategy.find_block_in_trace(trace, "tv_signal_1")["result"]
        is True
    )

    # Wait for expiry
    time.sleep(1.1)

    # Should be inactive now
    res, trace = strategy._evaluate_condition_tree(
        hybrid_config["entryConditions"], pair_info, market_data, None
    )
    assert (
        VisualBuilderStrategy.find_block_in_trace(trace, "tv_signal_1")["result"]
        is False
    )

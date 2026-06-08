from api import live_runtime


def test_get_max_live_strategies_matches_plan_config():
    assert live_runtime.get_max_live_strategies("free") == 0
    assert live_runtime.get_max_live_strategies("standard") == 10
    assert live_runtime.get_max_live_strategies("pro") == 30


def test_count_new_strategy_instances_counts_per_api_key_not_per_symbol():
    running_strategies = [
        {
            "id": "cfg-1",
            "api_key_id": 11,
            "mode": "live",
            "symbol": "BTCUSDT, ETHUSDT",
        }
    ]

    projected = live_runtime.count_new_strategy_instances(
        config_id="cfg-1",
        target_api_key_ids=[11, 12],
        running_strategies=running_strategies,
    )

    assert projected == 1


def test_count_new_strategy_instances_deduplicates_repeated_targets():
    running_strategies = []

    projected = live_runtime.count_new_strategy_instances(
        config_id="cfg-2",
        target_api_key_ids=[21, 21, 22],
        running_strategies=running_strategies,
    )

    assert projected == 2

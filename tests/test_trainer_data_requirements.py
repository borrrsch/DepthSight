from bot_module.trainer import Trainer


def test_data_requirements_collects_mtf_candles_from_wrapped_visual_config():
    strategy_config = {
        "entryTrigger": {"timeframe": "1m"},
        "filters": {
            "type": "AND",
            "children": [
                {"type": "trend_direction", "params": {"timeframe": "15m"}},
                {"type": "senior_tf_confluence", "params": {"timeframe": "30m"}},
                {"type": "significant_level", "params": {"timeframe": "2h"}},
            ],
        },
        "entryConditions": {
            "type": "local_level",
            "params": {"timeframe": "5m"},
        },
    }

    requirements = Trainer().get_data_requirements_for_strategy(
        "VisualBuilderStrategy",
        {"config_data": strategy_config},
        "ETHUSDT",
        "futures_usdtm",
    )

    assert {
        "kline_1m",
        "kline_5m",
        "kline_15m",
        "kline_30m",
        "kline_2h",
        "kline_1h",
        "kline_4h",
        "kline_1d",
    }.issubset(requirements)


def test_data_requirements_collects_mtf_candles_from_strategy_json_wrapper():
    requirements = Trainer().get_data_requirements_for_strategy(
        "GeneticCompatibleStrategy",
        {
            "strategy_json": {
                "entryConditions": {
                    "type": "trend_direction",
                    "params": {"timeframe": "45m"},
                }
            }
        },
        "ETHUSDT",
        "futures_usdtm",
    )

    assert "kline_45m" in requirements

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from api import schemas
from api.dependencies import is_strategy_kline_only, is_strategy_pro_only


def make_backtest_payload(params=None):
    return {
        "strategy_name": "VisualBuilderStrategy",
        "symbol": "BTCUSDT",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-01-02T00:00:00Z",
        "params": params or {},
    }


def make_valid_strategy_config(extra_entry_children=None):
    return {
        "strategy_name": "VisualBuilderStrategy",
        "signal_source": "internal",
        "filters": {"id": "filters_root", "type": "AND", "children": []},
        "entryTrigger": {"type": "on_candle_close", "timeframe": "5m"},
        "entryConditions": {
            "id": "entry_root",
            "type": "AND",
            "children": extra_entry_children or [],
        },
        "initialization": {
            "id": "init_1",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "atr_multiplier",
                "sl_value": 1.5,
                "tp_type": "rr_multiplier",
                "tp_value": 2.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [],
        "enabled": True,
    }


def test_recursive_pro_detection_sees_nested_logic_blocks():
    payload = {
        "config_data": {
            "entryConditions": {
                "type": "AND",
                "children": [
                    {
                        "type": "OR",
                        "children": [
                            {
                                "type": "correlation",
                                "params": {"operator": "lt", "value": 0.5},
                            }
                        ],
                    }
                ],
            },
        }
    }

    assert is_strategy_pro_only(payload) is True


def test_partial_exits_are_no_longer_treated_as_pro_only():
    payload = {
        "config_data": {
            "initialization": {
                "type": "open_position",
                "params": {
                    "partial_exits": [
                        {
                            "id": "pe-1",
                            "size_pct": 50,
                            "tp_type": "percent_from_price",
                            "tp_value": 1.0,
                        }
                    ],
                },
            },
        }
    }

    assert is_strategy_pro_only(payload) is False


def test_recursive_kline_only_detection_sees_dca_custom_condition():
    payload = {
        "config": {
            "positionManagement": [
                {
                    "type": "dca_management",
                    "params": {
                        "step_type": "custom_condition",
                        "step_value": {
                            "type": "AND",
                            "children": [
                                {"type": "order_book_zone_condition", "params": {}}
                            ],
                        },
                    },
                }
            ]
        }
    }

    assert is_strategy_kline_only(payload) is True


def test_recursive_kline_only_detection_sees_senior_tf_confluence():
    payload = {
        "config_data": {
            "entryConditions": {
                "type": "AND",
                "children": [
                    {
                        "type": "senior_tf_confluence",
                        "params": {"timeframe": "1h"},
                        "children": [
                            {
                                "type": "rsi_condition",
                                "params": {"period": 14, "operator": "gt", "value": 50},
                            }
                        ],
                    }
                ],
            }
        }
    }

    assert is_strategy_kline_only(payload) is True


def test_recursive_kline_only_detection_sees_editor_composite_and_provider_blocks():
    payload = {
        "config_data": {
            "entryConditions": {
                "type": "AND",
                "children": [
                    {
                        "type": "AND",
                        "compositeType": "level_proximity_condition",
                        "children": [
                            {
                                "type": "local_level",
                                "params": {
                                    "timeframe": "15m",
                                    "lookback_period": 20,
                                    "proximity_type": "percentage",
                                    "proximity_value": 0.2,
                                },
                            }
                        ],
                    }
                ],
            }
        }
    }

    assert is_strategy_kline_only(payload) is False


@pytest.mark.parametrize(
    "block_type",
    [
        "local_level",
        "significant_level",
        "round_level",
        "classic_pattern",
    ],
)
def test_foundation_blocks_no_longer_mark_strategy_as_kline_only(block_type):
    payload = {
        "config_data": {
            "entryConditions": {
                "type": "AND",
                "children": [
                    {
                        "type": block_type,
                        "params": {},
                    }
                ],
            }
        }
    }

    assert is_strategy_kline_only(payload) is False


def test_move_to_breakeven_no_longer_marks_strategy_as_kline_only():
    payload = {
        "config_data": {
            "positionManagement": [
                {
                    "type": "move_to_breakeven",
                    "params": {
                        "target_type": "rr_multiplier",
                        "target_value": 1.0,
                        "offset_pips": 2,
                    },
                }
            ]
        }
    }

    assert is_strategy_kline_only(payload) is False


def test_backtest_engine_normalization_accepts_aliases_and_rejects_invalid_values():
    assert schemas.normalize_backtest_engine("turbo") == "vector"
    assert schemas.normalize_backtest_engine("precision") == "kline"
    assert schemas.normalize_backtest_engine(None) == "vector"

    with pytest.raises(ValueError):
        schemas.normalize_backtest_engine("foo")


async def test_standard_user_cannot_use_precision_engine_alias(
    standard_user_client, mock_celery_tasks
):
    response = await standard_user_client.post(
        "/api/v1/backtests",
        json=make_backtest_payload({"backtest_engine": "precision"}),
    )

    assert response.status_code == 403, response.text
    assert "Precision Engine" in response.text


async def test_vector_engine_rejects_kline_only_management_blocks(
    standard_user_client, mock_celery_tasks
):
    response = await standard_user_client.post(
        "/api/v1/backtests",
        json=make_backtest_payload(
            {
                "backtest_engine": "vector",
                "config": {
                    "positionManagement": [
                        {
                            "type": "trailing_stop",
                            "params": {"type": "Percentage", "value": 2.0},
                        }
                    ]
                },
            }
        ),
    )

    assert response.status_code == 400
    assert "Precision" in response.text


async def test_standard_user_cannot_save_pro_only_strategy_config(standard_user_client):
    response = await standard_user_client.post(
        "/api/v1/strategies/config",
        json={
            "name": "Blocked Config",
            "description": "",
            "symbol_selection_mode": "STATIC",
            "symbols": ["BTCUSDT"],
            "config_data": make_valid_strategy_config(
                [
                    {
                        "id": "corr_1",
                        "type": "correlation",
                        "params": {"operator": "lt", "value": 0.5},
                    }
                ]
            ),
        },
    )

    assert response.status_code == 403, response.text
    assert "Pro-only blocks" in response.text


async def test_standard_user_cannot_start_saved_pro_only_strategy(
    standard_user_client, mocker, standard_user
):
    mock_config = SimpleNamespace(
        id="cfg-pro-only",
        symbol_selection_mode="STATIC",
        symbols=["BTCUSDT"],
        config_data=make_valid_strategy_config(
            [
                {
                    "id": "corr_1",
                    "type": "correlation",
                    "params": {"operator": "lt", "value": 0.5},
                }
            ]
        ),
        name="Blocked",
        description="",
        use_ml_confirmation=False,
        foundation_weights=None,
        user_id=standard_user.id,
    )
    mocker.patch(
        "api.crud.get_strategy_config", new_callable=AsyncMock, return_value=mock_config
    )

    response = await standard_user_client.post(
        "/api/v1/strategies",
        json={"config_id": "cfg-pro-only", "mode": "paper"},
    )

    assert response.status_code == 403
    assert "Pro-only blocks" in response.text

import pytest
from api import crud, schemas

pytestmark = pytest.mark.asyncio


def _strategy_config(name: str, condition_type: str) -> dict:
    return {
        "strategy_name": "VisualBuilderStrategy",
        "symbol": "BTCUSDT",
        "marketType": "FUTURES",
        "filters": {"type": "AND", "children": []},
        "entryTrigger": {"type": "on_candle_close", "timeframe": "1m", "params": {}},
        "entryConditions": {
            "type": "OR",
            "children": [
                {"type": condition_type, "params": {"operator": "gt", "value": 50}}
            ],
        },
        "initialization": {
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
            },
        },
        "positionManagement": [{"type": "take_profit", "params": {"tp_value": 2.0}}],
        "foundation_weights": {"trend": 1.0},
        "min_foundation_weight_threshold": 0.1,
        "name": name,
    }


async def _create_strategy(db_session, user_id: int, name: str, condition_type: str):
    return await crud.create_strategy_config(
        db_session,
        user_id,
        schemas.StrategyConfigCreate(
            name=name,
            config_data=_strategy_config(name, condition_type),
            symbol_selection_mode="manual",
            symbols=["BTCUSDT"],
        ),
    )


async def test_breed_strategies_requires_owned_parent_configs(
    authenticated_client,
    pro_user,
    free_user,
    db_session,
):
    own = await _create_strategy(db_session, pro_user.id, "Own", "rsi_condition")
    other = await _create_strategy(db_session, free_user.id, "Other", "stoch_condition")
    await db_session.commit()

    response = await authenticated_client.post(
        "/api/v1/strategies/breed",
        json={
            "parent_a_id": own.id,
            "parent_b_id": other.id,
            "mode": "balanced_merge",
            "mutation_rate": 0.0,
        },
    )

    assert response.status_code == 404


async def test_breed_strategies_returns_valid_hybrid_for_balanced_merge(
    authenticated_client,
    pro_user,
    db_session,
):
    parent_a = await _create_strategy(db_session, pro_user.id, "A", "rsi_condition")
    parent_b = await _create_strategy(db_session, pro_user.id, "B", "stoch_condition")
    await db_session.commit()

    response = await authenticated_client.post(
        "/api/v1/strategies/breed",
        json={
            "parent_a_id": parent_a.id,
            "parent_b_id": parent_b.id,
            "mode": "balanced_merge",
            "mutation_rate": 0.0,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "balanced_merge"
    hybrid = data["hybrid_config"]
    condition_types = {child["type"] for child in hybrid["entryConditions"]["children"]}
    assert condition_types == {"rsi_condition", "stoch_condition"}


async def test_breed_strategies_rejects_unknown_mode(
    authenticated_client,
    pro_user,
    db_session,
):
    parent_a = await _create_strategy(db_session, pro_user.id, "A", "rsi_condition")
    parent_b = await _create_strategy(db_session, pro_user.id, "B", "stoch_condition")
    await db_session.commit()

    response = await authenticated_client.post(
        "/api/v1/strategies/breed",
        json={
            "parent_a_id": parent_a.id,
            "parent_b_id": parent_b.id,
            "mode": "does_not_exist",
            "mutation_rate": 0.0,
        },
    )

    assert response.status_code == 500
    assert "Unknown breeding mode" in response.json()["error"]

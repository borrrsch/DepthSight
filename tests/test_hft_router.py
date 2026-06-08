import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api import crud


pytestmark = pytest.mark.asyncio


async def test_hft_start_publishes_user_scoped_start_command(
    authenticated_client,
    pro_user,
    db_session,
    mock_redis_client,
):
    active_keys = await crud.get_active_api_keys_for_user(db_session, pro_user.id)
    api_key = active_keys[0]
    app_config = SimpleNamespace(api_keys=[api_key])

    with patch(
        "api.hft_router.get_user_app_config", new=AsyncMock(return_value=app_config)
    ):
        response = await authenticated_client.post(
            f"/api/v1/hft/start?symbol=ETHUSDT&api_key_id={api_key.id}"
        )

    assert response.status_code == 200
    mock_redis_client.publish.assert_called_once()
    channel, raw_payload = mock_redis_client.publish.call_args.args
    payload = json.loads(raw_payload)
    assert channel == "hft:commands"
    assert payload["action"] == "StartBot"
    assert payload["bot_id"] == f"bot_{pro_user.id}_ETHUSDT"
    assert payload["user_id"] == pro_user.id
    assert payload["api_key"] == api_key.encrypted_api_key
    assert payload["api_secret"] == api_key.encrypted_api_secret


async def test_hft_config_is_persisted_per_user_and_broadcast(
    authenticated_client,
    pro_user,
    mock_redis_client,
):
    payload = {
        "entry_threshold": 0.61,
        "max_position_size_usd": 250.0,
        "risk_per_trade_pct": 0.75,
        "max_concurrent_trades": 2,
    }

    response = await authenticated_client.post("/api/v1/hft/config", json=payload)

    assert response.status_code == 200
    config_key = f"hft:config:{pro_user.id}"
    mock_redis_client.set.assert_called_once()
    assert mock_redis_client.set.call_args.args[0] == config_key
    mock_redis_client.publish.assert_called_once()
    command = json.loads(mock_redis_client.publish.call_args.args[1])
    assert command["action"] == "UpdateScreenerConfig"
    assert command["user_id"] == pro_user.id
    assert command["config"]["entry_threshold"] == pytest.approx(0.61)


async def test_hft_endpoints_require_auth(test_client):
    response = await test_client.post("/api/v1/hft/emergency")

    assert response.status_code == 401

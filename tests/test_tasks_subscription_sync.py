import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import tasks


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


@pytest.mark.asyncio
async def test_publish_live_deactivation_commands_publishes_for_each_active_key(mocker):
    fake_redis = Mock()
    mocker.patch.object(tasks, "redis_client_for_tasks", fake_redis)
    mocker.patch.object(
        tasks.crud,
        "get_active_api_keys_for_user",
        AsyncMock(return_value=[SimpleNamespace(id=101), SimpleNamespace(id=202)]),
    )

    published = await tasks._publish_live_deactivation_commands(object(), [7])

    assert published == 2
    assert fake_redis.publish.call_count == 2

    first_channel, first_payload = fake_redis.publish.call_args_list[0].args
    second_channel, second_payload = fake_redis.publish.call_args_list[1].args

    assert first_channel == tasks.config.REDIS_COMMAND_CHANNEL
    assert second_channel == tasks.config.REDIS_COMMAND_CHANNEL
    assert json.loads(first_payload) == {
        "command": "DEACTIVATE_API_KEY",
        "payload": {"user_id": 7, "api_key_id": 101},
    }
    assert json.loads(second_payload) == {
        "command": "DEACTIVATE_API_KEY",
        "payload": {"user_id": 7, "api_key_id": 202},
    }


@pytest.mark.asyncio
async def test_async_check_expired_subscriptions_downgrades_and_syncs(mocker):
    expired_users = [
        SimpleNamespace(id=3, plan="standard", plan_expires_at=object()),
        SimpleNamespace(id=4, plan="pro", plan_expires_at=object()),
    ]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(expired_users)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    @asynccontextmanager
    async def fake_session_ctx():
        yield session

    publish_sync = mocker.patch.object(
        tasks,
        "_publish_live_deactivation_commands",
        AsyncMock(return_value=3),
    )
    mocker.patch.object(tasks, "get_isolated_worker_session", fake_session_ctx)

    await tasks._async_check_expired_subscriptions()

    assert expired_users[0].plan == "free"
    assert expired_users[1].plan == "free"
    assert expired_users[0].plan_expires_at is None
    assert expired_users[1].plan_expires_at is None
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    publish_sync.assert_awaited_once_with(session, [3, 4])

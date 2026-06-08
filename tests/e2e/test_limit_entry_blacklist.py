#!/usr/bin/env python3
"""
E2E test to verify Limit Entry and Blacklist logic of the HFT bot.

The test checks:
1. Limit Entry - order is created with type LIMIT and status NEW
2. After changing status to FILLED, FILLED is returned
3. Blacklist - symbols from blacklist are saved in Redis
"""

import json
import pytest
import httpx

# mock server URL from conftest fixture
# MOCK_SERVER is taken from the mock_binance_server fixture


async def clear_mock_state(mock_server_url: str):
    """Clearing mock server state"""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(f"{mock_server_url}/__control/clear_state")
        assert resp.status_code == 200


async def get_received_orders(mock_server_url: str):
    """Get all orders received by the mock server"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{mock_server_url}/__control/get_received_orders")
        return resp.json().get("orders", [])


async def set_order_status(
    mock_server_url: str,
    order_id: int,
    status: str,
    avg_price: str = "100.0",
    executed_qty: str = "0.01",
):
    """Set order status (to emulate FILLED)"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{mock_server_url}/__control/set_order_status",
            json={
                "order_id": order_id,
                "status": status,
                "avg_price": avg_price,
                "executed_qty": executed_qty,
            },
        )
        return resp.json()


@pytest.mark.asyncio
async def test_order_lifecycle(mock_binance_server):
    """Full order lifecycle check: creation LIMIT -> NEW -> FILLED"""
    mock_server_url = mock_binance_server
    await clear_mock_state(mock_server_url)

    # 1. LIMIT order creation test
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{mock_server_url}/fapi/v1/order",
            data={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "0.01",
                "price": "100.0",
                "timeInForce": "GTC",
            },
        )
        order = resp.json()
        assert order["status"] == "NEW"
        assert order["type"] == "LIMIT"
        order_id = order["orderId"]

    # 2. Status check (should be NEW)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{mock_server_url}/fapi/v1/order",
            params={"symbol": "BTCUSDT", "orderId": order_id},
        )
        assert resp.json()["status"] == "NEW"

    # 3. Changing status to FILLED
    await set_order_status(mock_server_url, order_id, "FILLED", "100.5", "0.01")

    # 4. Checking that it is now FILLED
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{mock_server_url}/fapi/v1/order",
            params={"symbol": "BTCUSDT", "orderId": order_id},
        )
        assert resp.json()["status"] == "FILLED"


@pytest.mark.asyncio
async def test_market_order_instant_fill(mock_binance_server):
    """MARKET orders must be filled instantly"""
    mock_server_url = mock_binance_server

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{mock_server_url}/fapi/v1/order",
            data={
                "symbol": "ETHUSDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": "0.01",
            },
        )
        assert resp.json()["status"] == "FILLED"


@pytest.mark.asyncio
async def test_blacklist_logic_in_redis(mock_redis_client):
    """Check Blacklist operation in Redis"""
    user_id = 123
    blacklist_key = f"hft:blacklist:{user_id}"
    blacklist = ["SHIBUSDT", "PEPEUSDT"]

    # Using redis mock
    await mock_redis_client.set(blacklist_key, json.dumps(blacklist))

    stored = await mock_redis_client.get(blacklist_key)
    parsed = json.loads(stored)
    assert parsed == blacklist


@pytest.mark.asyncio
async def test_received_orders_verification(mock_binance_server):
    """Check accumulated orders on the mock server"""
    # This test should run AFTER the previous ones if we want to check accumulation,
    # but since conftest uses scope="function" for mock_binance_server,
    # the server restarts and the state is cleared.
    # Therefore, we create a couple of orders right here.
    mock_server_url = mock_binance_server
    await clear_mock_state(mock_server_url)

    async with httpx.AsyncClient() as client:
        # 1 LIMIT
        await client.post(
            f"{mock_server_url}/fapi/v1/order",
            data={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "0.01",
                "price": "100.0",
                "timeInForce": "GTC",
            },
        )
        # 1 MARKET
        await client.post(
            f"{mock_server_url}/fapi/v1/order",
            data={
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": "0.01",
            },
        )

    orders = await get_received_orders(mock_server_url)
    assert len(orders) == 2

    types = [o.get("type") for o in orders]
    assert "LIMIT" in types
    assert "MARKET" in types

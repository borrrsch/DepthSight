import pytest
import json
import time
from unittest.mock import MagicMock, AsyncMock
from bot_module.controller import TradingController, LivePosition, PartialTpOrderInfo
from bot_module.strategy import SignalDirection, PartialTarget


@pytest.mark.asyncio
async def test_serialization_json_format():
    """Verifies that the state is saved in JSON format and can be loaded back."""
    # Setup mocks
    mock_loop = MagicMock()
    mock_consumer = MagicMock()
    mock_executor = AsyncMock()
    mock_rm = MagicMock()
    mock_redis = AsyncMock()

    # Initialize controller
    controller = TradingController(
        loop=mock_loop,
        data_consumer=mock_consumer,
        live_executor=mock_executor,
        paper_executor=mock_executor,
        risk_manager=mock_rm,
        user_id=123,
    )
    controller.redis_client = mock_redis

    # Create a dummy position
    pos = LivePosition(
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        entry_price=50000.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=time.time(),
        strategy="TestStrategy",
        initial_stop_loss=49000.0,
        current_sl_price=49000.0,
        initial_take_profit=55000.0,
        status="OPEN",
        market_type="futures_usdtm",
    )
    pos.partial_tp_orders = [
        PartialTpOrderInfo(
            target_price=52000.0, orig_fraction=0.5, quantity=0.5, status="PENDING"
        )
    ]
    pos.original_partial_targets_plan = [PartialTarget(price=52000.0, fraction=0.5)]

    async with controller._positions_dict_lock:
        controller._active_position_set(pos)

    # 1. Test Saving
    await controller._save_runtime_state()

    # Verify redis_client.set was called with a JSON string
    args, kwargs = mock_redis.set.call_args
    saved_data = args[1]

    # Ensure it's valid JSON and contains our data
    parsed_json = json.loads(saved_data)
    assert parsed_json["serialization_format"] == "json"
    assert "BTCUSDT" in str(parsed_json["active_positions"])
    assert (
        parsed_json["active_positions"]["futures_usdtm:BTCUSDT"]["direction"] == "LONG"
    )

    # 2. Test Loading from JSON
    mock_redis.get.return_value = saved_data
    # Mock exchange to report that BTCUSDT is open
    mock_executor.get_open_positions.return_value = [
        {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "50000.0"}
    ]

    # Clear current state
    async with controller._positions_dict_lock:
        controller._active_positions.clear()

    await controller._load_runtime_state()

    # Verify position is restored correctly
    async with controller._positions_dict_lock:
        restored_pos = controller._active_position_get("BTCUSDT", "futures_usdtm")
        assert restored_pos is not None
        assert restored_pos.symbol == "BTCUSDT"
        assert restored_pos.direction == SignalDirection.LONG
        assert restored_pos.entry_price == 50000.0
        assert len(restored_pos.partial_tp_orders) == 1
        assert restored_pos.partial_tp_orders[0].target_price == 52000.0

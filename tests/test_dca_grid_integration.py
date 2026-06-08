# tests/test_dca_grid_integration.py

import pytest
import asyncio
import time
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

from bot_module.controller import (
    TradingController,
    LivePosition as Position,
    PartialTpOrderInfo,
)
from bot_module.strategy import SignalDirection, StrategySignal, OrderMode
from bot_module.strategy import VisualBuilderStrategy
from bot_module.depthsight_backtester import DepthSightBacktester


@pytest.fixture
def mock_controller_deps(mocker):
    """Mocks for TradingController dependencies."""
    consumer = AsyncMock()
    executor = AsyncMock()
    executor.market_type = "futures_usdtm"
    risk_manager = AsyncMock()
    risk_manager._adjust_and_round_quantity = MagicMock(
        side_effect=lambda q, symbol, price, lot_params, min_notional: q
    )
    trade_logger = MagicMock()

    return {
        "consumer": consumer,
        "executor": executor,
        "risk_manager": risk_manager,
        "trade_logger": trade_logger,
    }


@pytest.fixture
async def fast_controller(mock_controller_deps):
    """A minimal TradingController for testing logic without full startup."""
    with patch("bot_module.controller.get_strategy_instance", return_value=MagicMock()):
        ctrl = TradingController(
            loop=asyncio.get_running_loop(),
            data_consumer=lambda **kwargs: mock_controller_deps["consumer"],
            live_executor=mock_controller_deps["executor"],
            paper_executor=MagicMock(),
            risk_manager=mock_controller_deps["risk_manager"],
            user_id=1,
        )
        ctrl.trade_logger = mock_controller_deps["trade_logger"]

        # Mock _get_market_info to return valid values based on key
        async def mock_gmi(symbol, key, **kwargs):
            if key == "tick_size":
                return 0.01
            if key == "lot_params":
                return {"stepSize": 0.001}
            if key == "min_notional":
                return 5.0
            return None

        ctrl._get_market_info = AsyncMock(side_effect=mock_gmi)

        return ctrl


def _make_dca_position(direction=SignalDirection.LONG):
    position = MagicMock()
    position.direction = direction
    position.entry_price = 100.0
    position.dca_active_sos = 0
    position.symbol = "BTCUSDT"
    position.scale_in_triggered = None
    return position


def _last_price_condition(block_id: str, operator: str, value: float):
    return {
        "id": block_id,
        "type": "price_vs_level",
        "params": {
            "price_source": {"source": "candle", "key": "last_price"},
            "operator": operator,
            "level_source": {"source": "value", "value": value},
        },
    }


# --- 1. STRATEGY COMPONENT TESTS ---


@pytest.mark.asyncio
async def test_dca_percentage_trigger():
    """Test that DCAManagementBlock triggers scale_in on percentage drop."""
    mgmt_config = {
        "positionManagement": [
            {
                "id": "dca1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 3,
                    "volume_multiplier": 2.0,
                    "step_type": "percentage",
                    "step_value": 1.0,  # 1% drop
                },
            }
        ]
    }
    strategy = VisualBuilderStrategy(params={"config": mgmt_config})

    position = MagicMock()
    position.direction = SignalDirection.LONG
    position.entry_price = 100.0
    position.dca_active_sos = 0
    position.symbol = "BTCUSDT"
    position.scale_in_triggered = None

    # CASE 1: Price is 99.5 (0.5% drop) -> No trigger
    pair_info = {"last_price": 99.5, "symbol": "BTCUSDT"}
    # Signature: _handle_dca_management(block, position, pair_info, market_data, prev_pair_info)
    pos = await strategy._handle_dca_management(
        mgmt_config["positionManagement"][0], position, pair_info, {}, {}
    )
    assert pos.scale_in_triggered is None

    # CASE 2: Price is 98.9 (1.1% drop) -> Trigger!
    pair_info["last_price"] = 98.9
    pos = await strategy._handle_dca_management(
        mgmt_config["positionManagement"][0], position, pair_info, {}, {}
    )
    assert pos.scale_in_triggered is not None
    assert pos.scale_in_triggered["add_size_pct"] == 200.0
    assert pos.scale_in_triggered["dca_so_index"] == 1


@pytest.mark.asyncio
async def test_dca_custom_condition_step_value_tree_triggers():
    """DCA custom_condition accepts the frontend shape where step_value is a condition tree."""
    condition_root = {
        "id": "dca_custom_root",
        "type": "AND",
        "children": [
            _last_price_condition("price_below_100", "lt", 100.0),
            _last_price_condition("price_above_90", "gt", 90.0),
        ],
    }
    dca_block = {
        "id": "dca_custom",
        "type": "dca_management",
        "params": {
            "max_safety_orders": 3,
            "volume_multiplier": 1.5,
            "step_type": "custom_condition",
            "step_value": condition_root,
        },
    }
    strategy = VisualBuilderStrategy(
        params={"config": {"positionManagement": [dca_block]}}
    )
    position = _make_dca_position()

    pos = await strategy._handle_dca_management(
        dca_block,
        position,
        {"last_price": 95.0, "symbol": "BTCUSDT"},
        {},
        {},
    )

    assert pos.scale_in_triggered is not None
    assert pos.scale_in_triggered["add_size_pct"] == 150.0
    assert pos.scale_in_triggered["is_dca"] is True
    assert pos.scale_in_triggered["dca_so_index"] == 1


@pytest.mark.asyncio
async def test_dca_custom_condition_children_are_evaluated_as_and_root():
    """Legacy DCA children shape must require all nested conditions, not just the first child."""
    dca_block = {
        "id": "dca_custom_children",
        "type": "dca_management",
        "params": {
            "max_safety_orders": 3,
            "volume_multiplier": 1.0,
            "step_type": "custom_condition",
        },
        "children": [
            _last_price_condition("price_below_100", "lt", 100.0),
            _last_price_condition("price_above_90", "gt", 90.0),
        ],
    }
    strategy = VisualBuilderStrategy(
        params={"config": {"positionManagement": [dca_block]}}
    )
    position = _make_dca_position()

    pos = await strategy._handle_dca_management(
        dca_block,
        position,
        {"last_price": 89.0, "symbol": "BTCUSDT"},
        {},
        {},
    )
    assert pos.scale_in_triggered is None

    pos = await strategy._handle_dca_management(
        dca_block,
        position,
        {"last_price": 95.0, "symbol": "BTCUSDT"},
        {},
        {},
    )
    assert pos.scale_in_triggered is not None
    assert pos.scale_in_triggered["dca_so_index"] == 1


@pytest.mark.asyncio
async def test_grid_initialization_signal():
    """Test that GridManagementBlock triggers grid_init with correct bounds."""
    grid_params = {
        "levels": 5,
        "range_type": "percentage",
        "upper_bound": 105.0,
        "lower_bound": 95.0,
    }
    mgmt_config = {
        "positionManagement": [
            {"id": "grid1", "type": "grid_management", "params": grid_params}
        ]
    }
    strategy = VisualBuilderStrategy(params={"config": mgmt_config})

    position = MagicMock()
    position.grid_init_triggered = None
    position.grid_order_ids = []
    position.symbol = "BTCUSDT"

    pair_info = {"last_price": 100.0, "symbol": "BTCUSDT"}
    # Signature: _handle_grid_management(block, position, pair_info, market_data)
    pos = await strategy._handle_grid_management(
        mgmt_config["positionManagement"][0], position, pair_info, {}
    )

    assert pos.grid_init_triggered is not None
    assert pos.grid_init_triggered == grid_params


# --- 2. CONTROLLER EXECUTION TESTS ---


@pytest.mark.asyncio
async def test_controller_handle_scale_in_fill(fast_controller, mock_controller_deps):
    """Test weighted average entry price calculation after DCA fill."""
    symbol = "BTCUSDT"
    position = Position(
        symbol=symbol,
        direction=SignalDirection.LONG,
        entry_price=100.0,
        initial_quantity=1.0,  # 1 BTC at $100
        remaining_quantity=1.0,
        entry_time=time.time(),
        strategy="Test",
        status="OPEN",
        initial_stop_loss=90.0,
        current_sl_price=90.0,
        initial_take_profit=110.0,
    )
    position.dca_active_sos = 0
    fast_controller._active_positions[symbol] = position

    # More realistic execution report for scale-in fill
    # Buying 1 BTC at $90
    data = {
        "e": "ORDER_TRADE_UPDATE",
        "o": {
            "s": symbol,
            "c": "x-scalein-123",  # Prefix matters!
            "i": 999,
            "X": "FILLED",
            "S": "BUY",
            "q": "1.0",
            "z": "1.0",
            "ap": "90.0",
            "x": "TRADE",  # Execution Type
            "ot": "LIMIT",  # Order Type
        },
    }

    # Mock TP sync to avoid complex order placement in this unit test
    fast_controller._update_tp_after_scale_in = AsyncMock()

    await fast_controller._handle_order_update(data)

    # Wait for the async task created by create_task
    await asyncio.sleep(0.1)

    # Verify math
    # Average = (1*100 + 1*90) / 2 = 95.0
    assert position.entry_price == 95.0
    assert position.initial_quantity == 2.0
    assert position.remaining_quantity == 2.0
    assert position.dca_active_sos == 1
    fast_controller._update_tp_after_scale_in.assert_called_with(
        symbol, market_type="futures_usdtm"
    )


@pytest.mark.asyncio
async def test_controller_execute_grid_ladder(fast_controller, mock_controller_deps):
    """Test that controller places a ladder of limit orders for GRID."""
    symbol = "BTCUSDT"
    position = Position(
        symbol=symbol,
        direction=SignalDirection.LONG,
        entry_price=100.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=time.time(),
        strategy="Test",
        status="OPEN",
        initial_stop_loss=90.0,
        current_sl_price=90.0,
        initial_take_profit=110.0,
    )

    grid_params = {
        "levels": 3,
        "range_type": "percentage",
        "lower_bound": 90.0,
        "upper_bound": 110.0,
    }

    mock_controller_deps["executor"].place_order.return_value = {
        "orderId": 111,
        "status": "NEW",
    }
    fast_controller._active_positions[symbol] = position

    await fast_controller._execute_grid_ladder(position, grid_params)

    # For a 3-level grid between 90 and 110:
    # Levels: 90.0, 100.0, 110.0
    # Long position -> BUY limit orders (according to current _execute_grid_ladder implementation side choice)
    # Wait, in the code: binance_side = "BUY" if LONG else "SELL"
    # So it places BUY limit orders.
    assert mock_controller_deps["executor"].place_order.call_count == 3

    # Check calls
    calls = mock_controller_deps["executor"].place_order.call_args_list
    prices = [float(c.kwargs["price"]) for c in calls]
    assert sorted(prices) == [90.0, 100.0, 110.0]

    assert len(position.grid_order_ids) == 3


@pytest.mark.asyncio
async def test_entry_fill_triggers_immediate_dca_grid_init(fast_controller):
    symbol = "BTCUSDT"
    position = Position(
        symbol=symbol,
        direction=SignalDirection.LONG,
        entry_price=100.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=time.time(),
        strategy="Test",
        status="PENDING_ENTRY",
        initial_stop_loss=None,
        current_sl_price=None,
        initial_take_profit=110.0,
        entry_atr=1.5,
        entry_client_order_id="x-entry-123",
        dca_management_params={
            "max_safety_orders": 2,
            "step_type": "percentage",
            "step_value": 1.0,
            "volume_multiplier": 2.0,
            "step_multiplier": 1.0,
        },
    )
    position.partial_tp_orders = [
        PartialTpOrderInfo(
            target_price=110.0, orig_fraction=1.0, quantity=1.0, status="PENDING"
        )
    ]
    fast_controller._active_positions[symbol] = position

    fast_controller._execute_dca_grid = AsyncMock()
    fast_controller._place_exchange_trailing_stop = AsyncMock()

    await fast_controller._handle_entry_fill(
        symbol=symbol,
        order_id=123,
        client_order_id="x-entry-123",
        avg_fill_price=100.0,
        cumulative_filled_qty=1.0,
        fills=[],
        is_final_fill_status=False,
    )
    await asyncio.sleep(0.05)

    fast_controller._execute_dca_grid.assert_awaited_once()
    args = fast_controller._execute_dca_grid.await_args.args
    assert args[0].symbol == symbol
    assert args[1]["max_safety_orders"] == 2
    assert args[2]["atr"] == 1.5


@pytest.mark.asyncio
async def test_controller_tp_sync_cancels_old_orders(
    fast_controller, mock_controller_deps
):
    """Test that scale-in triggers cancellation of active TP orders."""
    symbol = "BTCUSDT"
    position = Position(
        symbol=symbol,
        direction=SignalDirection.LONG,
        entry_price=100.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=time.time(),
        strategy="Test",
        status="OPEN",
        initial_stop_loss=90.0,
        current_sl_price=90.0,
        initial_take_profit=110.0,
    )
    # Add an active TP order
    position.partial_tp_orders = [
        PartialTpOrderInfo(
            target_price=110.0,
            orig_fraction=1.0,
            quantity=1.0,
            order_id=555,
            client_order_id="x-tp-1",
            status="PENDING",
        )
    ]
    fast_controller._active_positions[symbol] = position

    # Mocking order placement
    mock_controller_deps["executor"].cancel_order = AsyncMock(return_value=True)

    # Mock strategy instance to verify it's called to reset TP
    mock_strat = MagicMock()
    # In controller, it looks for strategy instance via config_id
    position.strategy_config_id = "test-cfg"
    fast_controller.running_strategy_instances["test-cfg"] = (mock_strat, {})

    await fast_controller._update_tp_after_scale_in(symbol)

    # Should cancel order 555
    mock_controller_deps["executor"].cancel_order.assert_called_once_with(
        symbol, orderId=555, origClientOrderId="x-tp-1"
    )

    # Should clear local state
    assert len(position.partial_tp_orders) == 0


@pytest.mark.asyncio
async def test_dca_short_trigger():
    """Test that DCAManagementBlock triggers scale_in on price INCREASE for SHORT."""
    mgmt_config = {
        "positionManagement": [
            {
                "id": "dca1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 3,
                    "step_type": "percentage",
                    "step_value": 1.0,
                },
            }
        ]
    }
    strategy = VisualBuilderStrategy(params={"config": mgmt_config})

    position = MagicMock()
    position.direction = SignalDirection.SHORT
    position.entry_price = 100.0
    position.dca_active_sos = 0
    position.symbol = "BTCUSDT"
    position.scale_in_triggered = None

    # CASE 1: Price is 100.5 (0.5% rise) -> No trigger
    pair_info = {"last_price": 100.5, "symbol": "BTCUSDT"}
    await strategy._handle_dca_management(
        mgmt_config["positionManagement"][0], position, pair_info, {}, {}
    )
    assert position.scale_in_triggered is None

    # CASE 2: Price is 101.5 (1.5% rise) -> Trigger!
    pair_info["last_price"] = 101.5
    await strategy._handle_dca_management(
        mgmt_config["positionManagement"][0], position, pair_info, {}, {}
    )
    assert position.scale_in_triggered is not None
    assert position.scale_in_triggered["dca_so_index"] == 1


@pytest.mark.asyncio
async def test_controller_multiple_dca_steps(fast_controller, mock_controller_deps):
    """Test entry price calculation after two consecutive DCA fills."""
    symbol = "ETHUSDT"
    position = Position(
        symbol=symbol,
        direction=SignalDirection.LONG,
        entry_price=2000.0,
        initial_quantity=1.0,
        remaining_quantity=1.0,
        entry_time=time.time(),
        strategy="Test",
        status="OPEN",
        initial_stop_loss=1800.0,
        current_sl_price=1800.0,
        initial_take_profit=2200.0,
    )
    position.dca_active_sos = 0
    fast_controller._active_positions[symbol] = position
    fast_controller._update_tp_after_scale_in = AsyncMock()

    # SO 1: 1 ETH at 1900
    data1 = {
        "e": "ORDER_TRADE_UPDATE",
        "o": {
            "s": symbol,
            "c": "x-scalein-1",
            "i": 101,
            "X": "FILLED",
            "S": "BUY",
            "q": "1.0",
            "z": "1.0",
            "ap": "1900.0",
            "x": "TRADE",
            "ot": "LIMIT",
        },
    }
    await fast_controller._handle_order_update(data1)
    await asyncio.sleep(0.05)

    # Avg = (1*2000 + 1*1900)/2 = 1950.0. Qty = 2.0
    assert position.entry_price == 1950.0
    assert position.initial_quantity == 2.0
    assert position.dca_active_sos == 1

    # SO 2: 2 ETH at 1800 (volume multiplier usually increases qty, but here we just test arbitrary qty)
    data2 = {
        "e": "ORDER_TRADE_UPDATE",
        "o": {
            "s": symbol,
            "c": "x-scalein-2",
            "i": 102,
            "X": "FILLED",
            "S": "BUY",
            "q": "2.0",
            "z": "2.0",
            "ap": "1800.0",
            "x": "TRADE",
            "ot": "LIMIT",
        },
    }
    await fast_controller._handle_order_update(data2)
    await asyncio.sleep(0.05)

    # Avg = (2*1950 + 2*1800)/4 = 1875.0. Qty = 4.0
    assert position.entry_price == 1875.0
    assert position.initial_quantity == 4.0
    assert position.dca_active_sos == 2


@pytest.mark.asyncio
async def test_grid_short_initialization(fast_controller, mock_controller_deps):
    """Test that Grid initialization for SHORT uses SELL side for the ladder."""
    symbol = "SOLUSDT"
    position = Position(
        symbol=symbol,
        direction=SignalDirection.SHORT,
        entry_price=150.0,
        initial_quantity=10.0,
        remaining_quantity=10.0,
        entry_time=time.time(),
        strategy="Test",
        status="OPEN",
        initial_stop_loss=160.0,
        current_sl_price=160.0,
        initial_take_profit=140.0,
    )
    fast_controller._active_positions[symbol] = position

    grid_params = {"levels": 3, "lower_bound": 140.0, "upper_bound": 160.0}
    mock_controller_deps["executor"].place_order.return_value = {
        "orderId": 777,
        "status": "NEW",
    }

    await fast_controller._execute_grid_ladder(position, grid_params)

    # Short position -> SELL limit orders for the grid
    calls = mock_controller_deps["executor"].place_order.call_args_list
    for call in calls:
        assert call.kwargs["side"] == "SELL"

    assert mock_controller_deps["executor"].place_order.call_count == 3


def _create_flat_klines(num_rows=90, price=100.0):
    index = pd.date_range(
        datetime(2024, 1, 1, tzinfo=timezone.utc), periods=num_rows, freq="1min"
    )
    return pd.DataFrame(
        {
            "open": np.full(num_rows, price, dtype=float),
            "high": np.full(num_rows, price + 0.5, dtype=float),
            "low": np.full(num_rows, price - 0.5, dtype=float),
            "close": np.full(num_rows, price, dtype=float),
            "volume": np.full(num_rows, 100.0, dtype=float),
        },
        index=index,
    )


def _make_local_tmp_dir(prefix: str) -> Path:
    base_dir = Path.cwd() / ".pytest_tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    target_dir = base_dir / f"{prefix}_{uuid.uuid4().hex[:8]}"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def _make_visual_backtester(config_data, klines, artifacts_dir: Path):
    mock_config = MagicMock()
    mock_config.configure_mock(
        STRATEGY_SYMBOL_PERFORMANCE_ADJUSTMENT_ENABLED=False,
        BACKTEST_MIN_STOP_DISTANCE_PCT=0.0005,
        BACKTEST_MAX_POSITION_SIZE_PCT_BALANCE=0.90,
        SYMBOL_COOLDOWN_SECONDS=0.0,
        ML_CONFIRMATION_PROBABILITY_THRESHOLD=0.5,
        ML_CONFIRMATION_REJECT_IF_OPPOSITE_HIGH_PROB=False,
        ML_CONFIRMATION_STRATEGIES=[],
        DEFAULT_TICK_SIZE=0.01,
    )
    mock_config.FOUNDATION_WEIGHTS = {}
    mock_config.MIN_TOTAL_FOUNDATION_WEIGHT_THRESHOLD = 0.0

    bt = DepthSightBacktester(
        strategy_name="VisualBuilderStrategy",
        symbol="TESTUSDT",
        params={"config": config_data},
        historical_data={"kline_1m": klines.copy()},
        initial_balance=10000.0,
        min_trades_required=0,
        risk_params={"riskPerTradePercent": 1.0, "maxStopDistancePct": 5.0},
        backtest_risk_params={"riskPerTradePercent": 1.0, "maxStopDistancePct": 5.0},
        execution_config={"commission_pct": 0.0, "slippage_pct": 0.0},
        strategy_defaults={"VisualBuilderStrategy": {}},
        ml_training_config={},
        ml_sim_log_path=str(artifacts_dir / "sim.csv"),
        exchange_info={
            "tick_size": 0.01,
            "lot_params": {"stepSize": 0.001},
            "min_notional": 10.0,
        },
        min_foundation_weight_threshold=0.0,
        _config_override=mock_config,
        include_eod_in_log=True,
    )

    atr_col_name = f"ATR_{bt.atr_period}"
    bt.klines[atr_col_name] = 1.0
    bt.kline_index_map = {col: idx for idx, col in enumerate(bt.klines.columns)}
    bt.kline_data_array = bt.klines[list(bt.kline_index_map.keys())].to_numpy(
        dtype=np.float64
    )
    return bt


@pytest.mark.asyncio
async def test_backtester_executes_dca_scale_in_on_history():
    signal_fire_idx = 60
    klines = _create_flat_klines()
    klines.loc[klines.index[signal_fire_idx + 1], ["open", "high", "low", "close"]] = [
        100.0,
        100.5,
        97.5,
        98.0,
    ]
    klines.loc[
        klines.index[signal_fire_idx + 2] :, ["open", "high", "low", "close"]
    ] = [99.0, 101.0, 97.0, 100.0]
    artifacts_dir = _make_local_tmp_dir("bt_dca")

    config_data = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init_action",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "fixed_price",
                "sl_value": 95.0,
                "tp_type": "rr_multiplier",
                "tp_value": 1.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "percentage",
                    "step_value": 1.0,
                },
            }
        ],
    }

    backtester = _make_visual_backtester(config_data, klines, artifacts_dir)
    entry_signal = StrategySignal(
        "VisualBuilderStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        stop_loss=95.0,
        take_profit=105.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
        risk_pct=0.01,
    )

    def check_signal_sync(pair_info, *_args, **_kwargs):
        if pair_info["current_candle_index"] == signal_fire_idx:
            return entry_signal, 0.0, {}
        return None, 0.0, {}

    backtester.strategy_instance.check_signal_sync = check_signal_sync
    backtester.kline_data_array = backtester.klines[
        list(backtester.kline_index_map.keys())
    ].to_numpy(dtype=np.float64)

    results = await backtester.run_async()

    assert results is not None
    assert len(backtester.trade_log) == 1
    assert backtester.stats["number_of_entries"] == 2
    assert backtester.trade_log[0]["quantity"] > 20.0
    assert backtester.trade_log[0]["exit_reason"] == "END_OF_DATA"


@pytest.mark.asyncio
async def test_backtester_executes_dca_scale_in_without_stop_loss():
    signal_fire_idx = 60
    klines = _create_flat_klines()
    klines.loc[klines.index[signal_fire_idx + 1], ["open", "high", "low", "close"]] = [
        100.0,
        100.5,
        97.5,
        98.0,
    ]
    klines.loc[
        klines.index[signal_fire_idx + 2] :, ["open", "high", "low", "close"]
    ] = [100.0, 101.0, 99.0, 100.0]
    artifacts_dir = _make_local_tmp_dir("bt_dca_no_sl")

    config_data = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init_action",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "percent_from_price",
                "sl_value": 0.0,
                "tp_type": "percent_from_price",
                "tp_value": 2.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.5,
                    "step_type": "percentage",
                    "step_value": 1.0,
                },
            }
        ],
    }

    backtester = _make_visual_backtester(config_data, klines, artifacts_dir)
    entry_signal = StrategySignal(
        "VisualBuilderStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        stop_loss=None,
        take_profit=102.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
        risk_pct=0.01,
    )

    def check_signal_sync(pair_info, *_args, **_kwargs):
        if pair_info["current_candle_index"] == signal_fire_idx:
            return entry_signal, 0.0, {}
        return None, 0.0, {}

    backtester.strategy_instance.check_signal_sync = check_signal_sync
    backtester.kline_data_array = backtester.klines[
        list(backtester.kline_index_map.keys())
    ].to_numpy(dtype=np.float64)

    results = await backtester.run_async()

    assert results is not None
    assert len(backtester.trade_log) == 1
    assert backtester.stats["number_of_entries"] == 2
    assert backtester.trade_log[0]["exit_reason"] == "TAKE_PROFIT"
    assert backtester.trade_log[0]["quantity"] > 2.5
    assert backtester.trade_log[0]["entry_price"] < 99.0
    assert backtester.trade_log[0]["pnl"] > 4.9


@pytest.mark.asyncio
async def test_backtester_executes_dca_custom_condition_step_value_tree():
    signal_fire_idx = 60
    klines = _create_flat_klines()
    klines.loc[klines.index[signal_fire_idx + 1], ["open", "high", "low", "close"]] = [
        100.0,
        100.5,
        97.5,
        98.0,
    ]
    klines.loc[
        klines.index[signal_fire_idx + 2] :, ["open", "high", "low", "close"]
    ] = [100.0, 101.0, 99.0, 100.0]
    artifacts_dir = _make_local_tmp_dir("bt_dca_custom")

    config_data = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init_action",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "percent_from_price",
                "sl_value": 0.0,
                "tp_type": "percent_from_price",
                "tp_value": 2.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "dca_management",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.5,
                    "step_type": "custom_condition",
                    "step_value": {
                        "id": "dca_custom_root",
                        "type": "AND",
                        "children": [
                            _last_price_condition("price_below_100", "lt", 100.0),
                            _last_price_condition("price_above_90", "gt", 90.0),
                        ],
                    },
                },
            }
        ],
    }

    backtester = _make_visual_backtester(config_data, klines, artifacts_dir)
    entry_signal = StrategySignal(
        "VisualBuilderStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        stop_loss=None,
        take_profit=102.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
        risk_pct=0.01,
    )

    def check_signal_sync(pair_info, *_args, **_kwargs):
        if pair_info["current_candle_index"] == signal_fire_idx:
            return entry_signal, 0.0, {}
        return None, 0.0, {}

    backtester.strategy_instance.check_signal_sync = check_signal_sync
    backtester.kline_data_array = backtester.klines[
        list(backtester.kline_index_map.keys())
    ].to_numpy(dtype=np.float64)

    results = await backtester.run_async()

    assert results is not None
    assert len(backtester.trade_log) == 1
    assert backtester.stats["number_of_entries"] == 2
    assert backtester.trade_log[0]["exit_reason"] == "TAKE_PROFIT"
    assert backtester.trade_log[0]["entry_price"] < 99.0


@pytest.mark.asyncio
async def test_depthsight_marks_dca_grid_signal_to_skip_min_rr_before_risk_manager():
    signal_fire_idx = 60
    klines = _create_flat_klines()
    artifacts_dir = _make_local_tmp_dir("bt_dca_rr_skip")

    config_data = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init_action",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "percent_from_price",
                "sl_value": 1.5,
                "tp_type": "percent_from_price",
                "tp_value": 0.5,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "dca_1",
                "type": "DCA_MANAGEMENT",
                "params": {
                    "max_safety_orders": 1,
                    "volume_multiplier": 1.0,
                    "step_type": "percentage",
                    "step_value": 1.0,
                },
            }
        ],
    }

    backtester = _make_visual_backtester(config_data, klines, artifacts_dir)
    entry_signal = StrategySignal(
        "VisualBuilderStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        stop_loss=98.5,
        take_profit=100.5,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
        risk_pct=0.01,
    )
    captured_details = {}

    def check_signal_sync(pair_info, *_args, **_kwargs):
        if pair_info["current_candle_index"] == signal_fire_idx:
            return entry_signal, 0.0, {}
        return None, 0.0, {}

    async def assess_signal(signal, *_args, **_kwargs):
        captured_details.update(signal.details)
        return True, 1.0, 10.0, None

    backtester.strategy_instance.check_signal_sync = check_signal_sync
    backtester.rm.assess_signal = assess_signal
    backtester.kline_data_array = backtester.klines[
        list(backtester.kline_index_map.keys())
    ].to_numpy(dtype=np.float64)

    await backtester.run_async()

    assert captured_details["uses_dca_or_grid_management"] is True
    assert captured_details["skip_min_rr_for_dca_grid"] is True
    assert (
        DepthSightBacktester._strategy_uses_dca_or_grid_management(
            [{"type": "grid_management"}]
        )
        is True
    )


@pytest.mark.asyncio
async def test_backtester_executes_grid_orders_on_history():
    signal_fire_idx = 60
    klines = _create_flat_klines()
    klines.loc[klines.index[signal_fire_idx + 1], ["open", "high", "low", "close"]] = [
        100.0,
        100.5,
        97.0,
        99.0,
    ]
    klines.loc[klines.index[signal_fire_idx + 2], ["open", "high", "low", "close"]] = [
        99.0,
        100.0,
        96.0,
        98.0,
    ]
    klines.loc[
        klines.index[signal_fire_idx + 3] :, ["open", "high", "low", "close"]
    ] = [99.0, 101.0, 96.5, 99.0]
    artifacts_dir = _make_local_tmp_dir("bt_grid")

    config_data = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init_action",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "fixed_price",
                "sl_value": 95.0,
                "tp_type": "rr_multiplier",
                "tp_value": 1.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "grid_1",
                "type": "grid_management",
                "params": {
                    "range_type": "percentage",
                    "grid_levels": 5,
                    "lower_bound": -4.0,
                    "upper_bound": 0.0,
                },
            }
        ],
    }

    backtester = _make_visual_backtester(config_data, klines, artifacts_dir)
    entry_signal = StrategySignal(
        "VisualBuilderStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        stop_loss=95.0,
        take_profit=105.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
        risk_pct=0.01,
    )

    def check_signal_sync(pair_info, *_args, **_kwargs):
        if pair_info["current_candle_index"] == signal_fire_idx:
            return entry_signal, 0.0, {}
        return None, 0.0, {}

    backtester.strategy_instance.check_signal_sync = check_signal_sync
    backtester.kline_data_array = backtester.klines[
        list(backtester.kline_index_map.keys())
    ].to_numpy(dtype=np.float64)

    results = await backtester.run_async()

    assert results is not None
    assert len(backtester.trade_log) == 1
    assert backtester.stats["number_of_entries"] == 4
    assert backtester.trade_log[0]["quantity"] == pytest.approx(44.0)
    assert backtester.trade_log[0]["exit_reason"] == "END_OF_DATA"


@pytest.mark.asyncio
async def test_backtester_executes_grid_orders_without_stop_loss():
    signal_fire_idx = 60
    klines = _create_flat_klines()
    klines.loc[klines.index[signal_fire_idx + 1], ["open", "high", "low", "close"]] = [
        100.0,
        100.5,
        99.5,
        100.0,
    ]
    klines.loc[klines.index[signal_fire_idx + 2], ["open", "high", "low", "close"]] = [
        100.0,
        100.0,
        97.0,
        98.0,
    ]
    klines.loc[
        klines.index[signal_fire_idx + 3] :, ["open", "high", "low", "close"]
    ] = [100.0, 101.0, 98.5, 100.0]
    artifacts_dir = _make_local_tmp_dir("bt_grid_no_sl")

    config_data = {
        "entryConditions": {"id": "entry_root", "type": "AND", "children": []},
        "initialization": {
            "id": "init_action",
            "type": "open_position",
            "params": {
                "direction": "LONG",
                "risk_type": "percent_balance",
                "risk_value": 1.0,
                "sl_type": "percent_from_price",
                "sl_value": 0.0,
                "tp_type": "percent_from_price",
                "tp_value": 2.0,
                "partial_exits": [],
            },
        },
        "positionManagement": [
            {
                "id": "grid_1",
                "type": "grid_management",
                "params": {
                    "range_type": "percentage",
                    "grid_levels": 5,
                    "lower_bound": -4.0,
                    "upper_bound": 0.0,
                },
            }
        ],
    }

    backtester = _make_visual_backtester(config_data, klines, artifacts_dir)
    entry_signal = StrategySignal(
        "VisualBuilderStrategy",
        "TESTUSDT",
        SignalDirection.LONG,
        stop_loss=None,
        take_profit=102.0,
        trigger_price=100.0,
        mode=OrderMode.MARKET,
        risk_pct=0.01,
    )

    def check_signal_sync(pair_info, *_args, **_kwargs):
        if pair_info["current_candle_index"] == signal_fire_idx:
            return entry_signal, 0.0, {}
        return None, 0.0, {}

    backtester.strategy_instance.check_signal_sync = check_signal_sync
    backtester.kline_data_array = backtester.klines[
        list(backtester.kline_index_map.keys())
    ].to_numpy(dtype=np.float64)

    results = await backtester.run_async()

    assert results is not None
    assert len(backtester.trade_log) == 1
    assert backtester.stats["number_of_entries"] == 4
    assert backtester.trade_log[0]["exit_reason"] == "TAKE_PROFIT"
    assert backtester.trade_log[0]["quantity"] > 2.1
    assert backtester.trade_log[0]["entry_price"] < 99.5
    assert backtester.trade_log[0]["pnl"] > 4.0

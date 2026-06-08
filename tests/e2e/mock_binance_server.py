# tests/e2e/mock_binance_server.py
import asyncio
import logging
import random
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict

import uvicorn
from fastapi import (
    APIRouter,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

# --- Logging configuration for the mock server ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [MockBinance] - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- In-memory server state storage ---
# This is our "database" for the mock server
STATE = {
    # To store active WebSocket connections by stream name
    "active_websockets": defaultdict(list),
    # Data queue for sending to WebSocket
    "ws_data_queue": defaultdict(deque),
    # For storing orders received from the bot
    "received_orders": [],
    # To store listenKey
    "listen_keys": {},
    # To store order statuses (order_id -> {status, avg_price, executed_qty, ...})
    "order_statuses": {},
    # Next order_id for generation
    "next_order_id": 100000,
}

app = FastAPI(title="Mock Binance Server for E2E Tests")

# --- 1. Control endpoints (for management from the test) ---
# These endpoints are not part of the Binance API. They are needed so that our pytest test
# could manage the mock server state.

control_router = APIRouter(prefix="/__control")


@control_router.post("/push_ws_data")
async def push_ws_data(payload: Dict[str, Any]):
    """
    The test uses this endpoint to "feed" market data to the bot.
    Example: {"stream": "btcusdt@kline_1m", "data": {"e": "kline", ...}}
    """
    stream = payload.get("stream")
    data = payload.get("data")
    if not stream or not data:
        raise HTTPException(status_code=400, detail="Stream and data are required")

    logger.info(f"CONTROL: Pushing data to stream '{stream}'")
    STATE["ws_data_queue"][stream].append(data)

    # Immediately send data to all subscribers of this stream
    for ws in STATE["active_websockets"].get(stream, []):
        try:
            await ws.send_json({"stream": stream, "data": data})
        except Exception as e:
            logger.warning(
                f"CONTROL: Failed to send data to a websocket for stream {stream}: {e}"
            )

    return {"status": "ok", "message": f"Data queued for stream {stream}"}


@control_router.get("/get_received_orders")
async def get_received_orders():
    """The test uses this endpoint to check which orders the bot has placed."""
    orders = list(STATE["received_orders"])
    logger.info(f"CONTROL: Test requested {len(orders)} received orders.")
    return {"orders": orders}


@control_router.delete("/clear_state")
async def clear_state():
    """Clears the server state before a new test."""
    logger.info("CONTROL: Clearing server state.")
    STATE["received_orders"].clear()
    STATE["ws_data_queue"].clear()
    STATE["order_statuses"].clear()
    STATE["next_order_id"] = 100000
    # Do not clear active_websockets, as they are managed by connections
    return {"status": "ok"}


@control_router.post("/set_order_status")
async def set_order_status(payload: Dict[str, Any]):
    """
    The test uses this endpoint to set the order status.
    Example: {"order_id": 100001, "status": "FILLED", "avg_price": "100.5", "executed_qty": "0.01"}
    """
    order_id = str(payload.get("order_id"))
    new_status = payload.get("status", "FILLED")
    avg_price = payload.get("avg_price", "100.0")
    executed_qty = payload.get("executed_qty", "0.01")

    if order_id in STATE["order_statuses"]:
        STATE["order_statuses"][order_id]["status"] = new_status
        STATE["order_statuses"][order_id]["avgPrice"] = avg_price
        STATE["order_statuses"][order_id]["executedQty"] = executed_qty
        logger.info(f"CONTROL: Updated order {order_id} status to {new_status}")
    else:
        STATE["order_statuses"][order_id] = {
            "orderId": int(order_id),
            "status": new_status,
            "avgPrice": avg_price,
            "executedQty": executed_qty,
        }
        logger.info(f"CONTROL: Created order {order_id} with status {new_status}")

    return {"status": "ok", "order_id": order_id, "new_status": new_status}


# --- 2. Binance REST API emulation ---
# Here we create the endpoints that our `BinanceExecutor` will call.

binance_fapi_router = APIRouter(prefix="/fapi/v1")


@binance_fapi_router.post("/listenKey")
async def create_listen_key():
    """Emulates ListenKey creation for User Data Stream."""
    listen_key = f"mockListenKey_{uuid.uuid4().hex}"
    STATE["listen_keys"][listen_key] = {"created_at": time.time()}
    logger.info(f"API: Created ListenKey: {listen_key}")
    return {"listenKey": listen_key}


@binance_fapi_router.put("/listenKey")
async def keep_alive_listen_key(request: Request):
    """Emulates ListenKey keep-alive."""
    # In reality, we would check the listenKey from the query parameters
    # For the mock, simply return success.
    logger.info("API: Received Keep-Alive for a listen key.")
    return {}


@binance_fapi_router.post("/order")
async def place_order(request: Request):
    """
    Emulates order placement. For LIMIT orders, returns NEW,
    for MARKET orders, returns FILLED immediately.
    """
    form_data = await request.form()
    order_details = dict(form_data)
    order_details["timestamp_received"] = datetime.now(timezone.utc).isoformat()
    STATE["received_orders"].append(order_details)

    order_id = STATE["next_order_id"]
    STATE["next_order_id"] += 1
    order_type = order_details.get("type", "MARKET")
    quantity = order_details.get("quantity", "0.01")
    price = order_details.get("price", "100.0")

    # For LIMIT orders, return NEW (maker mode emulation)
    # For MARKET orders, return FILLED immediately
    if order_type == "LIMIT":
        status = "NEW"
        avg_price = "0"
        executed_qty = "0"
    else:
        status = "FILLED"
        avg_price = str(random.uniform(99, 101))
        executed_qty = quantity

    # Save the order in STATE for subsequent GET /order requests
    STATE["order_statuses"][str(order_id)] = {
        "orderId": order_id,
        "symbol": order_details.get("symbol"),
        "status": status,
        "clientOrderId": order_details.get("newClientOrderId", ""),
        "price": price,
        "avgPrice": avg_price,
        "origQty": quantity,
        "executedQty": executed_qty,
        "cumQty": executed_qty,
        "type": order_type,
        "side": order_details.get("side"),
        "reduceOnly": order_details.get("reduceOnly", "false"),
        "updateTime": int(time.time() * 1000),
    }

    logger.info(
        f"API: Order {order_id} placed: {order_type} {order_details.get('side')} status={status}"
    )

    return STATE["order_statuses"][str(order_id)]


@binance_fapi_router.get("/order")
async def get_order(request: Request):
    """
    Emulates GET /order to check the order status.
    The bot calls this to check if a LIMIT order has been filled.
    """
    params = dict(request.query_params)
    order_id = params.get("orderId")

    if order_id and str(order_id) in STATE["order_statuses"]:
        order = STATE["order_statuses"][str(order_id)]
        logger.info(f"API: GET order {order_id} -> status={order['status']}")
        return order

    logger.warning(f"API: Order {order_id} not found")
    raise HTTPException(
        status_code=400, detail={"code": -2013, "msg": "Order does not exist."}
    )


@binance_fapi_router.delete("/order")
async def cancel_order(request: Request):
    """Emulates order cancellation."""
    query_params = dict(request.query_params)
    logger.info(f"API: Received order cancellation request: {query_params}")
    # Simply return a successful response
    return {
        "orderId": query_params.get("orderId", random.randint(1000, 2000)),
        "symbol": query_params.get("symbol"),
        "clientOrderId": query_params.get("origClientOrderId"),
        "status": "CANCELED",
    }


# --- 3. Binance WebSocket API emulation ---


@app.websocket("/ws/{stream_path:path}")
async def websocket_endpoint(websocket: WebSocket, stream_path: str):
    """
    Handles incoming WebSocket connections from the bot.
    Stream path can be either `btcusdt@kline_1m` or `mockListenKey_...`.
    """
    await websocket.accept()
    logger.info(f"WS: Client connected to path: /{stream_path}")

    STATE["active_websockets"][stream_path].append(websocket)

    try:
        # Main loop for sending data from the queue
        while True:
            # Send data if it is in the queue for this stream
            if (
                stream_path in STATE["ws_data_queue"]
                and STATE["ws_data_queue"][stream_path]
            ):
                data_to_send = STATE["ws_data_queue"][stream_path].popleft()
                await websocket.send_json({"stream": stream_path, "data": data_to_send})
                logger.info(f"WS: Sent data to stream '{stream_path}'")

            # You can also add logic for listening to messages from the client (e.g., subscribe/unsubscribe)
            try:
                # Waiting for messages from the client in a non-blocking manner
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                logger.info(f"WS: Received message on '{stream_path}': {message}")
            except asyncio.TimeoutError:
                pass  # It is normal if the client sent nothing

            await asyncio.sleep(0.2)  # A small pause to avoid loading the CPU

    except WebSocketDisconnect:
        logger.info(f"WS: Client disconnected from path: /{stream_path}")
    except Exception as e:
        logger.error(f"WS: Error on path /{stream_path}: {e}", exc_info=True)
    finally:
        # Remove the socket from the active list upon disconnection
        if stream_path in STATE["active_websockets"]:
            if websocket in STATE["active_websockets"][stream_path]:
                STATE["active_websockets"][stream_path].remove(websocket)
                if not STATE["active_websockets"][stream_path]:
                    del STATE["active_websockets"][stream_path]
            logger.info(f"WS: Cleaned up connection for path: /{stream_path}")


# --- Application build ---
app.include_router(control_router)
app.include_router(binance_fapi_router)


if __name__ == "__main__":
    # Start the mock server on a port that does not conflict with the main API
    uvicorn.run("mock_binance_server:app", host="127.0.0.1", port=9999, reload=True)

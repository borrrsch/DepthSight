# File: tests/mocks.py
import asyncio
import time
import random
from typing import Dict, Any, Optional, List, Set, Callable, Coroutine
from collections import defaultdict
from types import SimpleNamespace
import pandas as pd
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import logging
from datetime import timezone  # Add timezone import
import json  # Ensure json is imported for MockRedisClient

import redis.asyncio
import redis.exceptions

# Attempt to shim redis.asyncio.exceptions if it's missing
# and redis.asyncio appears to be a full module.
# This is to help fakeredis if it's looking for this specific path.
if hasattr(redis.asyncio, "__path__"):  # Check if redis.asyncio is a package
    if not hasattr(redis.asyncio, "exceptions"):
        print("Attempting to monkeypatch redis.asyncio.exceptions")
        setattr(redis.asyncio, "exceptions", redis.exceptions)

try:
    import fakeredis.aioredis as fakeredis_aioredis

    FakeRedisBase = fakeredis_aioredis.FakeRedis
except ModuleNotFoundError:

    class FakeRedisBase:
        def __init__(self, **kwargs):
            self._data = {}
            self.decode_responses = kwargs.get("decode_responses", False)

        async def publish(self, channel, message):
            return 1

        async def set(self, key, value, **kwargs):
            if kwargs.get("nx") and key in self._data:
                return False
            self._data[key] = value
            return True

        async def get(self, key):
            return self._data.get(key)

        async def delete(self, *keys):
            deleted_count = 0
            for key in keys:
                if key in self._data:
                    del self._data[key]
                    deleted_count += 1
            return deleted_count

        async def flushdb(self):
            self._data.clear()
            return True

    fakeredis_aioredis = SimpleNamespace(FakeRedis=FakeRedisBase)

# --- bot_module imports ---
try:
    from bot_module.strategy import SignalDirection
    from bot_module.config import DEFAULT_TICK_SIZE
    import bot_module.config as bot_config_module  # Import for REDIS_STATE_KEY_STRATEGIES
except ImportError:
    from enum import Enum

    class SignalDirection(Enum):
        LONG = "LONG"
        SHORT = "SHORT"

    DEFAULT_TICK_SIZE = 0.00000001

    # Mock bot_config_module if needed for offline use of mocks
    class MockBotConfig:
        REDIS_STATE_KEY_STRATEGIES = "depthsight:state:strategies"

    bot_config_module = MockBotConfig()


logger = logging.getLogger("mocks")  # Logger for mocks
# Basic logger configuration (if not already configured)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)  # Set DEBUG for mocks


# --- MockRedisClient (using fakeredis) ---
class MockRedisClient(FakeRedisBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.publish_calls = []  # To keep track of publish calls for tests

    async def publish_method(self, channel, message):
        self.publish_calls.append((channel, message))
        # Call the original publish method from FakeRedis
        return await super().publish(channel, message)

    # Override publish to use our tracked method
    @property
    def publish(self):
        return self.publish_method

    async def set_initial_data(self, key, value):
        # For FakeRedis, setting initial data is done via standard commands
        # This method might need to be adapted or used differently with FakeRedis.
        # For now, let's assume direct use of 'set' or 'hmset' etc. in tests.
        # If complex objects need to be stored (like JSON strings), ensure they are serialized.
        if isinstance(value, (dict, list)):
            await self.set(key, json.dumps(value))
        else:
            await self.set(key, value)

    def reset_mock(self):
        self.publish_calls = []
        # For FakeRedis, to reset data, you might want to flush the db
        # This is a more involved operation, consider if needed for each test.
        # For now, just resetting publish_calls.
        # await self.flushdb() # Example if full reset is needed


# Instantiate the FakeRedis client
# We pass decode_responses=True so that get commands return strings, not bytes.
# This is common for Redis interactions where keys/values are text.
mock_redis_client = MockRedisClient(decode_responses=True)


# --- Updated MockDataConsumer ---
class MockDataConsumer:
    """
    Simulates DataConsumer, providing data from historical DataFrames.
    Redesigned for more reliable data delivery in E2E tests.
    """

    def __init__(
        self, historical_data: Dict[str, Optional[pd.DataFrame]], symbols: List[str]
    ):
        self._historical_data: Dict[str, Optional[pd.DataFrame]] = {}
        self._symbols = set(symbols)
        self._active_pairs_info: List[Dict[str, Any]] = []
        self._primary_kline_key: Optional[str] = None

        for key, df in historical_data.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                df_copy = df.copy()
                if not isinstance(df_copy.index, pd.DatetimeIndex):
                    try:
                        df_copy.index = pd.to_datetime(df_copy.index, utc=True)
                    except Exception as e:
                        logger.error(
                            f"[MockConsumer Init] Failed to convert index for '{key}': {e}. Skipping."
                        )
                        self._historical_data[key] = None
                        continue
                if df_copy.index.tz is None:
                    df_copy.index = df_copy.index.tz_localize("UTC")
                elif df_copy.index.tz != timezone.utc:
                    df_copy.index = df_copy.index.tz_convert("UTC")

                if key == "aggTrade":
                    for col in ["price", "quantity"]:
                        if col in df_copy.columns:
                            df_copy[col] = pd.to_numeric(df_copy[col], errors="coerce")
                        else:
                            logger.warning(
                                f"[MockConsumer Init] Missing column '{col}' in aggTrade data."
                            )
                    df_copy.dropna(subset=["price", "quantity"], inplace=True)
                    if not df_copy.index.is_monotonic_increasing:
                        df_copy.sort_index(inplace=True)

                self._historical_data[key] = df_copy
            else:
                self._historical_data[key] = None

        self._current_index = -1
        self._max_index = -1

        tf_priority = ["1m", "3m", "5m", "15m", "30m", "1h"]
        for tf in tf_priority:
            key = f"kline_{tf}"
            df = self._historical_data.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                self._primary_kline_key = key
                self._max_index = len(df) - 1
                break
        if self._primary_kline_key is None:
            for key, df in self._historical_data.items():
                if (
                    key.startswith("kline_")
                    and isinstance(df, pd.DataFrame)
                    and not df.empty
                ):
                    self._primary_kline_key = key
                    self._max_index = len(df) - 1
                    break

        if self._primary_kline_key:
            logger.info(
                f"[MockConsumer Init] Primary kline key: '{self._primary_kline_key}'. Max index: {self._max_index}."
            )
        else:
            logger.error("[MockConsumer Init] No valid kline data found!")
            self._active_pairs_info = [
                {"symbol": s, "natr": 1.0, "atr": 0.001, "last_price": 100.0}
                for s in self._symbols
            ]

        self._running = False
        self.pair_update_queue: asyncio.Queue[bool] = asyncio.Queue(maxsize=1)
        self._required_streams: Set[str] = set()

        if self._max_index >= 0:
            self._update_pairs_info_from_kline(0)
        logger.info(
            f"[MockConsumer] Initialized for symbols: {self._symbols}. Max index: {self._max_index}"
        )

    def _update_pairs_info_from_kline(self, index: int):
        """Updates _active_pairs_info with data from kline at the specified index."""
        kline_key_to_use = self._primary_kline_key
        if not kline_key_to_use:
            if not self._active_pairs_info:
                self._active_pairs_info = [
                    {"symbol": s, "natr": 1.0, "atr": 0.001, "last_price": 100.0}
                    for s in self._symbols
                ]
            return

        df_kline = self._historical_data.get(kline_key_to_use)
        if not isinstance(df_kline, pd.DataFrame) or df_kline.empty:
            return

        if 0 <= index < len(df_kline):
            try:
                current_kline = df_kline.iloc[index]
                current_close = float(current_kline.get("close", 0.0))
                current_atr = float(current_kline.get("atr", 0.0))

                if pd.isna(current_close) or pd.isna(current_atr) or current_close <= 0:
                    if self._active_pairs_info:
                        prev_info = next(iter(self._active_pairs_info), None)
                        if prev_info:
                            if pd.isna(current_close) or current_close <= 0:
                                current_close = prev_info.get("last_price", 100.0)
                            if pd.isna(current_atr):
                                current_atr = prev_info.get("atr", 0.001)
                        else:
                            if pd.isna(current_close) or current_close <= 0:
                                current_close = 100.0
                            if pd.isna(current_atr):
                                current_atr = 0.001
                    else:
                        if pd.isna(current_close) or current_close <= 0:
                            current_close = 100.0
                        if pd.isna(current_atr):
                            current_atr = 0.001

                current_natr = (
                    (current_atr / current_close * 100)
                    if current_close > 0 and current_atr > 0
                    else 0.0
                )
                self._active_pairs_info = [
                    {
                        "symbol": s,
                        "natr": current_natr,
                        "atr": current_atr,
                        "last_price": current_close,
                    }
                    for s in self._symbols
                ]
            except (IndexError, KeyError, ValueError, TypeError) as e:
                logger.error(
                    f"[MockConsumer] Error updating pair info at index {index}: {e}",
                    exc_info=True,
                )
                if not self._active_pairs_info:
                    self._active_pairs_info = [
                        {"symbol": s, "natr": 1.0, "atr": 0.001, "last_price": 100.0}
                        for s in self._symbols
                    ]
        else:
            pass  # Keep old values

    async def start(self):
        self._running = True
        logger.info("[MockConsumer] Started.")

    async def stop(self):
        self._running = False
        logger.info("[MockConsumer] Stopped.")

    def advance_time(self) -> bool:
        """Shifts the internal time pointer by one step and updates pair_info."""
        if self._current_index < self._max_index:
            self._current_index += 1
            self._update_pairs_info_from_kline(self._current_index)
            # logger.debug(f"[MockConsumer] Advanced to index: {self._current_index}")
            return True
        else:
            return False

    def get_current_timestamp(self) -> Optional[pd.Timestamp]:
        """Returns the timestamp of the current index from the main kline DataFrame."""
        if not self._primary_kline_key:
            return None
        df_primary = self._historical_data.get(self._primary_kline_key)
        if not isinstance(df_primary, pd.DataFrame) or df_primary.empty:
            return None
        if 0 <= self._current_index < len(df_primary):
            try:
                ts = df_primary.index[self._current_index]
                return ts if isinstance(ts, pd.Timestamp) else None
            except IndexError:
                return None
        else:
            return None

    def _get_current_kline_data(self, timeframe: str) -> Optional[pd.Series]:
        """Helper method to get current candle data for the specified timeframe."""
        key = f"kline_{timeframe}"
        df = self._historical_data.get(key)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return None
        if 0 <= self._current_index < len(df):
            try:
                return df.iloc[self._current_index].copy()
            except IndexError:
                return None
        else:
            return None

    async def get_active_pairs(self) -> List[Dict[str, Any]]:
        return [p.copy() for p in self._active_pairs_info]

    async def get_active_symbols(self) -> Set[str]:
        return self._symbols.copy()

    async def get_kline_history(
        self, symbol: str, timeframe: str, limit: int = 250, **kwargs
    ) -> Optional[pd.DataFrame]:
        """Returns a DataFrame with Klines history UP TO the current index (inclusive)."""
        key = f"kline_{timeframe}"
        df = self._historical_data.get(key)
        log_prefix = (
            f"[MockConsumer:get_kline_history:{key}:{symbol}]"  # Added symbol to log
        )

        if symbol not in self._symbols:
            logger.warning(f"{log_prefix} Symbol not managed.")
            return pd.DataFrame()
        if not isinstance(df, pd.DataFrame) or df.empty:
            logger.debug(f"{log_prefix} Kline data not found or empty.")
            return pd.DataFrame()
        if self._current_index < 0:
            logger.debug(f"{log_prefix} Current index {self._current_index} < 0.")
            return pd.DataFrame()

        end_idx = self._current_index + 1
        start_idx = max(0, end_idx - limit)

        # --- Added logging before the slice ---
        df_len = len(df)
        logger.debug(
            f"{log_prefix} Request: limit={limit}. State: current_idx={self._current_index}, df_len={df_len}. Calculated slice: [{start_idx}:{end_idx}]"
        )

        if start_idx >= df_len or start_idx >= end_idx:
            logger.debug(
                f"{log_prefix} Invalid slice indices. Returning EMPTY DataFrame."
            )
            return pd.DataFrame()

        try:
            slice_df = df.iloc[start_idx:end_idx]
            # --- Added logging of the result ---
            if slice_df.empty:
                logger.debug(f"{log_prefix} Slice resulted in EMPTY DataFrame.")
            else:
                logger.debug(
                    f"{log_prefix} Returning slice with {len(slice_df)} rows. Index range: {slice_df.index.min()} to {slice_df.index.max()}"
                )
            return slice_df.copy()
        except Exception as e:
            logger.error(
                f"{log_prefix} Error slicing DataFrame [{start_idx}:{end_idx}] (Len: {df_len}): {e}",
                exc_info=True,
            )
            logger.debug(f"{log_prefix} Returning EMPTY DataFrame due to error.")
            return pd.DataFrame()

    async def get_recent_trades(
        self, symbol: str, limit: int = 100
    ) -> Optional[pd.DataFrame]:
        """Returns a DataFrame with the latest trades BEFORE the current time."""
        key = "aggTrade"
        df_trades = self._historical_data.get(key)
        log_prefix = f"[MockConsumer:get_recent_trades:{symbol}]"

        if symbol not in self._symbols:
            logger.warning(f"{log_prefix} Symbol not managed.")
            return pd.DataFrame()
        if not isinstance(df_trades, pd.DataFrame) or df_trades.empty:
            logger.debug(f"{log_prefix} aggTrade data not found or empty.")
            return pd.DataFrame()
        if not isinstance(df_trades.index, pd.DatetimeIndex):
            logger.error(f"{log_prefix} aggTrade data no DatetimeIndex!")
            return pd.DataFrame()
        if self._current_index < 0:
            logger.debug(f"{log_prefix} Current index {self._current_index} < 0.")
            return pd.DataFrame()

        current_time = self.get_current_timestamp()
        if current_time is None:
            logger.warning(f"{log_prefix} Cannot get current timestamp.")
            return pd.DataFrame()

        # --- Added logging before filtering ---
        df_len = len(df_trades)
        logger.debug(
            f"{log_prefix} Request: limit={limit}. State: current_idx={self._current_index}, current_time={current_time}, df_len={df_len}"
        )

        try:
            # Use .loc for DatetimeIndex
            slice_df = df_trades.loc[df_trades.index <= current_time].tail(limit)
            # --- Added logging of the result ---
            if slice_df.empty:
                logger.debug(
                    f"{log_prefix} Filtering by time <= {current_time} resulted in EMPTY DataFrame."
                )
            else:
                logger.debug(
                    f"{log_prefix} Returning slice with {len(slice_df)} rows. Index range: {slice_df.index.min()} to {slice_df.index.max()}"
                )
            return slice_df.copy()
        except Exception as e:
            logger.error(
                f"{log_prefix} Error filtering/slicing aggTrades (Time <= {current_time}): {e}",
                exc_info=True,
            )
            logger.debug(f"{log_prefix} Returning EMPTY DataFrame due to error.")
            return pd.DataFrame()

    async def get_latest_depth(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Generates a pseudo-orderbook based on the current price."""
        # (Logic unchanged, but add a log on error)
        if symbol not in self._symbols:
            return None
        current_pair_info = next(
            (p for p in self._active_pairs_info if p.get("symbol") == symbol), None
        )
        if not current_pair_info or "last_price" not in current_pair_info:
            return None
        price = current_pair_info["last_price"]
        if price <= 0:
            logger.warning(
                f"[MockConsumer] get_latest_depth: Invalid price {price} for {symbol}."
            )
            return None
        tick_size = current_pair_info.get("tick_size", DEFAULT_TICK_SIZE)
        if tick_size <= 0:
            tick_size = DEFAULT_TICK_SIZE
        try:
            num_levels = 20
            bids = [
                [f"{price - (i + 1) * tick_size:.8f}", f"{random.uniform(5, 50):.4f}"]
                for i in range(num_levels)
            ]
            asks = [
                [f"{price + (i + 1) * tick_size:.8f}", f"{random.uniform(5, 50):.4f}"]
                for i in range(num_levels)
            ]
            return {"bids": bids, "asks": asks, "lastUpdateId": int(time.time() * 1000)}
        except Exception as e:
            logger.error(f"[MockConsumer] Error generating depth for {symbol}: {e}")
            return None

    # --- Subscription methods (stubs, unchanged) ---
    async def ensure_subscription(self, data_type_key: str, symbol: str, **kwargs):
        self._required_streams.add(f"{data_type_key}:{symbol}")

    async def remove_subscription(self, data_type_key: str, symbol: str):
        self._required_streams.discard(f"{data_type_key}:{symbol}")

    async def clear_all_subscriptions(self):
        self._required_streams.clear()


# --- MockBinanceExecutor (no changes, assuming it works correctly) ---
class MockBinanceExecutor:
    """Simulates BinanceExecutor for E2E tests with more detailed simulation."""

    def __init__(
        self,
        initial_balance: Dict[str, float],
        commission_pct: float,
        slippage_pct: float,
        exchange_info: Dict,
    ):
        self.balances = defaultdict(lambda: {"free": 0.0, "locked": 0.0})
        for asset, amount in initial_balance.items():
            self.balances[asset]["free"] = float(amount)  # Save as float
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.exchange_info = exchange_info  # Dictionary symbol -> info

        self.open_orders: Dict[int, Dict[str, Any]] = {}
        self.order_history: List[Dict[str, Any]] = []
        self._next_order_id = int(time.time() * 10)
        self._user_data_callback: Optional[Callable[[Dict[str, Any]], Coroutine]] = None
        self._current_kline: Optional[pd.Series] = None
        logger.info(f"[MockExecutor] Initialized. Balance: {dict(self.balances)}")

    async def close(self):
        logger.info("[MockExecutor] Closed.")
        pass

    def set_current_kline(self, kline: pd.Series):
        """Sets the current candle for execution simulation."""
        self._current_kline = kline
        # logger.debug(f"[MockExecutor] Current kline set: {kline.name} O={kline['open']} H={kline['high']} L={kline['low']} C={kline['close']}")

    async def get_account_balance(self) -> Dict[str, Dict[str, str]]:
        """Returns balances in string format."""
        # logger.debug(f"[MockExecutor] get_account_balance called.")
        return {
            asset: {"free": f"{data['free']:.8f}", "locked": f"{data['locked']:.8f}"}
            for asset, data in self.balances.items()
        }

    async def fetch_exchange_info(
        self, force_update: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Returns mock exchange information."""
        # logger.debug(f"[MockExecutor] fetch_exchange_info called.")
        # In mock, simply return the saved data
        return {
            "symbols": list(self.exchange_info.values())
        }  # Format like the real API

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        # logger.debug(f"[MockExecutor] get_symbol_info called for {symbol}.")
        return self.exchange_info.get(symbol.upper())

    async def get_filter(
        self, symbol: str, filter_type: str
    ) -> Optional[Dict[str, Any]]:
        sym_info = self.exchange_info.get(symbol.upper(), {})
        filters = sym_info.get("filters", [])
        return next((f for f in filters if f.get("filterType") == filter_type), None)

    async def get_tick_size(self, symbol: str) -> Optional[float]:
        return self.exchange_info.get(symbol.upper(), {}).get("tick_size")

    async def get_lot_size_params(self, symbol: str) -> Optional[Dict[str, float]]:
        return self.exchange_info.get(symbol.upper(), {}).get("lot_params")

    async def get_min_notional(self, symbol: str) -> Optional[float]:
        return self.exchange_info.get(symbol.upper(), {}).get("min_notional")

    def _generate_order_id(self) -> int:
        self._next_order_id += 1
        return self._next_order_id

    def _apply_slippage(self, price: float, side: str, order_type: str) -> float:
        """Applies slippage (simplified)."""
        # Slippage only for MARKET orders
        if self.slippage_pct == 0 or order_type != "MARKET":
            return price
        multiplier = (
            (1 + self.slippage_pct) if side == "BUY" else (1 - self.slippage_pct)
        )
        slippaged_price = price * multiplier
        # logger.debug(f"[MockExecutor] Slippage: Price {price:.8f} -> {slippaged_price:.8f} (Side: {side})")
        return slippaged_price

    def _adjust_quantity(self, quantity: float, symbol: str) -> float:
        """Adjusts quantity according to LOT_SIZE filters."""
        lot_params = self.exchange_info.get(symbol.upper(), {}).get("lot_params")
        if not lot_params:
            return quantity  # No filters - no adjustment
        step_size = lot_params.get("stepSize", 0)
        min_qty = lot_params.get("minQty", 0)

        # Check quantity type
        try:
            qty_dec = Decimal(str(quantity))
        except (ValueError, TypeError, InvalidOperation):
            logger.error(
                f"[MockExecutor] Invalid quantity type for adjustment: {quantity} ({type(quantity)})"
            )
            return 0.0  # Cannot process - return 0

        adj_qty = quantity  # Start with the original
        if step_size > 0:
            step_dec = Decimal(str(step_size))
            # Round DOWN to step
            adj_qty = float(
                (qty_dec / step_dec).quantize(Decimal("0"), rounding=ROUND_DOWN)
                * step_dec
            )
            # logger.debug(f"[MockExecutor] Qty {quantity:.8f} adjusted by stepSize {step_size:.8f} -> {adj_qty:.8f}")

        if adj_qty < min_qty:
            # logger.debug(f"[MockExecutor] Adjusted qty {adj_qty:.8f} < minQty {min_qty:.8f}. Returning 0.")
            return 0.0
        return adj_qty

    def _check_min_notional(self, quantity: float, price: float, symbol: str) -> bool:
        """Checks the minimum nominal value."""
        min_notional = self.exchange_info.get(symbol.upper(), {}).get("min_notional")
        if min_notional is None:
            return True  # No filter - check passed
        notional_value = quantity * price
        # logger.debug(f"[MockExecutor] Checking minNotional for {symbol}: Value={notional_value:.4f}, Min={min_notional:.4f}")
        return notional_value >= min_notional

    def _round_price(
        self, price: float, symbol: str, rounding_mode=ROUND_DOWN
    ) -> float:
        """Rounds price by tick_size."""
        tick_size = self.exchange_info.get(symbol.upper(), {}).get("tick_size")
        if tick_size is None or tick_size <= 0:
            return price
        try:
            price_dec = Decimal(str(price))
            tick_dec = Decimal(str(tick_size))
            rounded_dec = (price_dec / tick_dec).quantize(
                Decimal("0"), rounding=rounding_mode
            ) * tick_dec
            return float(rounded_dec)
        except Exception as e:
            logger.error(
                f"[MockExecutor] Error rounding price {price} for {symbol}: {e}"
            )
            return price

    async def place_order(
        self, symbol: str, side: str, order_type: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Simulates order placement with improved validation, MARKET processing
        and added debugging for SL/TP orders.
        """
        order_id = self._generate_order_id()
        client_order_id = kwargs.get("newClientOrderId", f"mock-{order_id}")
        symbol_upper = symbol.upper()
        side_upper = side.upper()
        order_type_upper = order_type.upper()
        log_prefix = f"[MockExecutor Place:{order_id}:{symbol_upper}:{side_upper}:{order_type_upper}]"
        # --- LOG 1: Input data ---
        logger.debug(f"{log_prefix} Received order placement request. Kwargs: {kwargs}")

        # Extract parameters
        quantity_str = kwargs.get("quantity")
        quote_qty_str = kwargs.get("quoteOrderQty")
        price_str = kwargs.get("price")
        stop_price_str = kwargs.get("stopPrice")
        time_in_force = kwargs.get("timeInForce")

        quantity = 0.0
        quote_qty = 0.0
        price = 0.0
        stop_price = 0.0
        try:
            if quantity_str is not None:
                quantity = float(quantity_str)
            if quote_qty_str is not None:
                quote_qty = float(quote_qty_str)
            if price_str is not None:
                price = float(price_str)
            if stop_price_str is not None:
                stop_price = float(stop_price_str)
        except (ValueError, TypeError) as e:
            msg = f"Invalid numeric parameter value: {e}"
            logger.error(f"{log_prefix} {msg}")
            return {"error": True, "code": -1104, "msg": msg}  # Use real Binance code

        # Basic parameter validation (tightened)
        if order_type_upper == "LIMIT":
            if quantity <= 0 or price <= 0 or not time_in_force:
                msg = f"LIMIT requires positive quantity({quantity}), price({price}) and timeInForce({time_in_force})"
                logger.error(f"{log_prefix} {msg}")
                return {"error": True, "code": -1104, "msg": msg}
        elif order_type_upper == "MARKET":
            if not (quantity > 0 or quote_qty > 0):
                msg = f"MARKET requires positive quantity({quantity}) or quoteOrderQty({quote_qty})"
                logger.error(f"{log_prefix} {msg}")
                return {"error": True, "code": -1104, "msg": msg}
            if quantity > 0 and quote_qty > 0:  # Cannot specify both
                msg = "MARKET order cannot have both quantity and quoteOrderQty"
                logger.error(f"{log_prefix} {msg}")
                return {"error": True, "code": -1104, "msg": msg}
        # Refined validation for STOP/TAKE_PROFIT orders
        elif order_type_upper in [
            "STOP_MARKET",
            "TAKE_PROFIT_MARKET",
            "STOP",
            "STOP_LOSS_LIMIT",
            "TAKE_PROFIT_LIMIT",
        ]:
            if quantity <= 0:
                msg = f"{order_type_upper} requires positive quantity({quantity})"
                logger.error(f"{log_prefix} {msg}")
                return {"error": True, "code": -1104, "msg": msg}
            if stop_price <= 0:
                # Trailing delta may not require stopPrice, but requires trailingDelta
                if (
                    "trailingDelta" not in kwargs
                    or float(kwargs.get("trailingDelta", 0)) <= 0
                ):
                    msg = f"{order_type_upper} requires positive stopPrice({stop_price}) (or 'trailingDelta')."
                    logger.error(f"{log_prefix} {msg}")
                    return {"error": True, "code": -1104, "msg": msg}
            # For LIMIT versions, price is also needed
            if order_type_upper.endswith("LIMIT") and price <= 0:
                msg = f"{order_type_upper} requires positive price({price})"
                logger.error(f"{log_prefix} {msg}")
                return {"error": True, "code": -1104, "msg": msg}
        # Add validation for other types if needed

        # Processing MARKET order and calculating quantity
        orig_qty_for_record = quantity  # Saving the original quantity for the record
        if order_type_upper == "MARKET":
            if quote_qty > 0:  # Calculating quantity from quoteOrderQty
                if self._current_kline is None:
                    msg = "Cannot calculate quantity for MARKET quoteOrderQty: current price unknown"
                    logger.error(f"{log_prefix} {msg}")
                    return {"error": True, "code": -1104, "msg": msg}
                market_price = float(self._current_kline["close"])  # Simplified
                if market_price <= 0:
                    msg = f"Cannot calculate quantity for MARKET quoteOrderQty: invalid market price ({market_price})"
                    logger.error(f"{log_prefix} {msg}")
                    return {"error": True, "code": -1104, "msg": msg}
                quantity = quote_qty / market_price  # Calculate base quantity
                logger.debug(
                    f"{log_prefix} Calculated base quantity {quantity:.8f} from quoteOrderQty {quote_qty:.2f} at price {market_price:.8f}"
                )
                # Leave orig_qty_for_record = 0 because it was not set
            elif quantity > 0:
                # If quantity is set, quote_qty must be 0 (already checked)
                quote_qty = 0.0
                orig_qty_for_record = quantity  # Use the specified quantity
            else:  # This branch should not be reached due to validation above
                msg = "Internal error: MARKET order has neither quantity nor quoteOrderQty"
                logger.error(f"{log_prefix} {msg}")
                return {"error": True, "code": -999, "msg": msg}

        # Adjusting quantity by LOT_SIZE (if quantity > 0)
        adj_quantity = quantity
        if quantity > 0:
            adj_quantity = self._adjust_quantity(quantity, symbol_upper)
            # LOG 2: After LOT_SIZE
            logger.debug(
                f"{log_prefix} Quantity after LOT_SIZE adjustment: {adj_quantity:.8f} (Original: {quantity:.8f})"
            )
            if adj_quantity <= 0:
                msg = (
                    f"Quantity ({quantity:.8f}) became zero after LOT_SIZE adjustment."
                )
                logger.error(f"{log_prefix} {msg}")
                return {
                    "error": True,
                    "code": -1013,
                    "msg": msg,
                }  # FILTER_FAILURE.LOT_SIZE

        # Check minNotional
        # Using order price (LIMIT), current price (MARKET) or stopPrice (STOP/TAKE_PROFIT)
        price_for_notional_check = 0
        if order_type_upper == "LIMIT":
            price_for_notional_check = price
        elif order_type_upper == "MARKET":
            price_for_notional_check = (
                float(self._current_kline["close"])
                if self._current_kline is not None
                else 0
            )
        # Using stopPrice for stop orders
        elif order_type_upper in [
            "STOP_MARKET",
            "TAKE_PROFIT_MARKET",
            "STOP",
            "STOP_LOSS_LIMIT",
            "TAKE_PROFIT_LIMIT",
        ]:
            price_for_notional_check = stop_price  # Use stopPrice for these types
            logger.debug(
                f"{log_prefix} Using stopPrice {stop_price:.8f} for minNotional check."
            )
        else:  # For other types (if they appear)
            price_for_notional_check = (
                float(self._current_kline["close"])
                if self._current_kline is not None
                else 0
            )

        if price_for_notional_check <= 0:
            msg = f"Cannot estimate price ({price_for_notional_check}) for minNotional check (Order Type: {order_type_upper})."
            logger.error(f"{log_prefix} {msg}")
            return {"error": True, "code": -1104, "msg": msg}

        min_notional_passes = self._check_min_notional(
            adj_quantity, price_for_notional_check, symbol_upper
        )  # Corrected to use adj_quantity

        if order_type_upper in ["STOP_MARKET", "TAKE_PROFIT_MARKET"]:
            logger.debug(
                f"{log_prefix} MinNotional Check (using stopPrice {price_for_notional_check:.8f}): Qty={adj_quantity:.8f}, Value={adj_quantity * price_for_notional_check:.4f}, Result={min_notional_passes}"
            )
        else:
            logger.debug(
                f"{log_prefix} MinNotional Check (using price {price_for_notional_check:.8f}): Qty={adj_quantity:.8f}, Value={adj_quantity * price_for_notional_check:.4f}, Result={min_notional_passes}"
            )

        if not min_notional_passes:
            msg = f"Order value ({adj_quantity * price_for_notional_check:.4f}) below minNotional."
            logger.error(f"{log_prefix} {msg}")
            return {
                "error": True,
                "code": -1013,
                "msg": msg,
            }  # FILTER_FAILURE.MIN_NOTIONAL

        # Final quantity for execution
        final_quantity = adj_quantity
        logger.debug(
            f"{log_prefix} Final quantity for order record and potential execution: {final_quantity:.8f}"
        )

        # Creating an order record with NEW status
        order_data = {
            "symbol": symbol_upper,
            "orderId": order_id,
            "orderListId": -1,
            "clientOrderId": client_order_id,
            "transactTime": int(time.time() * 1000),
            "price": f"{price:.8f}",
            "origQty": f"{orig_qty_for_record:.8f}",  # Original quantity
            "executedQty": "0.00000000",
            "cummulativeQuoteQty": "0.00000000",
            "status": "NEW",
            "timeInForce": time_in_force or "GTC",
            "type": order_type_upper,
            "side": side_upper,
            "stopPrice": f"{stop_price:.8f}" if stop_price > 0 else "0.00000000",
            "icebergQty": "0.0",
            "time": int(time.time() * 1000),
            "updateTime": int(time.time() * 1000),
            "isWorking": True,  # NEW orders are considered active
            "workingTime": int(time.time() * 1000),
            "origQuoteOrderQty": f"{quote_qty:.8f}"
            if quote_qty > 0
            else "0.00000000",  # Record quote_qty
            "selfTradePreventionMode": "NONE",
            "fills": [],  # List of trades will be here
            "quantity_to_execute": final_quantity,
        }
        # --- LOG 4: Prepared data ---
        logger.debug(f"{log_prefix} Prepared order_data (status NEW): {order_data}")

        # --- ERROR SIMULATION (For Controller debugging, if needed) ---
        # if order_type_upper == "STOP_MARKET":
        #      logger.warning(f"{log_prefix} --- SIMULATING IMMEDIATE REJECTION FOR STOP_MARKET ---")
        #      order_data["status"] = "REJECTED"
        #      order_data["isWorking"] = False
        #      self.order_history.append(order_data.copy()) # Adding to history
        #      await self._send_execution_report(order_data, "REJECTED")
        #      # Return error response
        #      return {
        #          "error": True, "code": -2010, "msg": "Simulated rejection",
        #          "symbol": symbol_upper, "orderId": order_id, "clientOrderId": client_order_id,
        #          "status": "REJECTED" # Return REJECTED status
        #      }
        # --- END OF MOCK ---

        # Adding to open orders and history
        self.open_orders[order_id] = order_data
        self.order_history.append(order_data.copy())
        logger.info(
            f"{log_prefix} Order created (status NEW). Final Qty for Execution: {final_quantity:.8f}"
        )

        # Sending an order creation report (NEW)
        await self._send_execution_report(order_data, "NEW")

        # --- Immediate execution ONLY for MARKET ---
        if order_type_upper == "MARKET":
            logger.debug(f"{log_prefix} Attempting immediate fill for MARKET order.")
            if self._current_kline is not None:
                market_fill_price = float(self._current_kline["close"])
                fill_result = await self._fill_order(
                    order_id, market_fill_price, final_quantity
                )
                if not fill_result:
                    logger.error(
                        f"{log_prefix} Failed to fill MARKET order immediately (check balance/logic). Order remains NEW/REJECTED."
                    )
                    # Status could have changed to REJECTED inside _fill_order
                # else: logger.info(f"{log_prefix} MARKET order filled immediately.")
            else:
                logger.error(
                    f"{log_prefix} Cannot fill MARKET order: current kline unknown."
                )
                # Canceling the order because it cannot be executed
                order_data["status"] = "EXPIRED"  # Or REJECTED?
                order_data["isWorking"] = False
                if order_id in self.open_orders:
                    del self.open_orders[order_id]
                self.order_history.append(order_data.copy())
                await self._send_execution_report(order_data, "EXPIRED")
                return {
                    "error": True,
                    "code": -2011,
                    "msg": "Market order expired due to no price",
                }  # Use real code

        # Returning a response similar to the real API
        # Take the last entry from history to return the current status
        last_hist_entry = next(
            (o for o in reversed(self.order_history) if o["orderId"] == order_id),
            order_data,
        )
        response_payload = {
            "symbol": symbol_upper,
            "orderId": order_id,
            "clientOrderId": client_order_id,
            "transactTime": last_hist_entry["transactTime"],
            "price": last_hist_entry["price"],
            "origQty": last_hist_entry["origQty"],
            "executedQty": last_hist_entry["executedQty"],
            "cummulativeQuoteQty": last_hist_entry["cummulativeQuoteQty"],
            "status": last_hist_entry["status"],
            "timeInForce": last_hist_entry["timeInForce"],
            "type": last_hist_entry["type"],
            "side": last_hist_entry["side"],
            "stopPrice": last_hist_entry["stopPrice"],  # Added
            "origQuoteOrderQty": last_hist_entry["origQuoteOrderQty"],
        }
        # --- LOG 5: Method response ---
        logger.debug(f"{log_prefix} Returning REST response: {response_payload}")
        return response_payload

    async def cancel_order(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        origClientOrderId: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simulates order cancellation."""
        symbol_upper = symbol.upper()
        o_id_to_cancel = None
        id_str = ""

        if orderId is not None:
            o_id_to_cancel = orderId
            id_str = f"ID {orderId}"
        elif origClientOrderId is not None:
            id_str = f"ClientID {origClientOrderId}"
            # Search for order by client ID
            for oid, odata in self.open_orders.items():
                if (
                    odata["clientOrderId"] == origClientOrderId
                    and odata["symbol"] == symbol_upper
                ):
                    o_id_to_cancel = oid
                    break
        else:  # Neither ID nor ClientID is specified
            return {
                "error": True,
                "code": -1104,
                "msg": "Missing order identifier (orderId or origClientOrderId required).",
            }

        log_prefix = f"[MockExecutor Cancel:{symbol_upper}:{id_str}]"

        if o_id_to_cancel in self.open_orders:
            order_data = self.open_orders.pop(o_id_to_cancel)  # Remove from open
            order_data["status"] = "CANCELED"
            order_data["isWorking"] = False
            order_data["updateTime"] = int(time.time() * 1000)
            self.order_history.append(order_data.copy())  # Add canceled to history
            logger.info(f"{log_prefix} Order CANCELED.")
            await self._send_execution_report(order_data, "CANCELED")
            # Return API response
            return {
                "symbol": order_data["symbol"],
                "orderId": order_data["orderId"],
                "origClientOrderId": order_data["clientOrderId"],  # Original ClientID
                "clientOrderId": order_data[
                    "clientOrderId"
                ],  # The response usually contains our ClientID
                "status": order_data["status"],
                "executedQty": order_data["executedQty"],
                "cummulativeQuoteQty": order_data["cummulativeQuoteQty"],
                "type": order_data["type"],
                "side": order_data["side"],
                "price": order_data["price"],
                "origQty": order_data["origQty"],
            }
        else:
            # --- Simulation of Binance response when trying to cancel a non-existent order ---
            # Check if it has already been executed or canceled
            history_entry = next(
                (
                    o
                    for o in reversed(self.order_history)
                    if (
                        o["orderId"] == orderId
                        or o["clientOrderId"] == origClientOrderId
                    )
                    and o["symbol"] == symbol_upper
                ),
                None,
            )
            if history_entry:
                msg = f"Order status is {history_entry['status']}, can not be canceled."
                logger.warning(f"{log_prefix} {msg}")
                # Return an error similar to Binance (-2011: Unknown order sent.)
                # Or just {"error": True, "msg": msg}? Return -2011.
                return {"error": True, "code": -2011, "msg": "Unknown order sent."}
            else:
                msg = "Order does not exist."
                logger.warning(f"{log_prefix} {msg}")
                return {"error": True, "code": -2011, "msg": "Unknown order sent."}

    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Returns simulated open orders."""
        # logger.debug(f"[MockExecutor] get_open_orders called for {symbol or 'ALL'}.")
        symbol_upper = symbol.upper() if symbol else None
        orders = []
        for order_data in list(self.open_orders.values()):  # Copy for safety
            if symbol_upper is None or order_data["symbol"] == symbol_upper:
                orders.append(
                    {
                        "symbol": order_data["symbol"],
                        "orderId": order_data["orderId"],
                        "orderListId": order_data["orderListId"],
                        "clientOrderId": order_data["clientOrderId"],
                        "price": order_data["price"],
                        "origQty": order_data["origQty"],
                        "executedQty": order_data["executedQty"],
                        "cummulativeQuoteQty": order_data["cummulativeQuoteQty"],
                        "status": order_data["status"],
                        "timeInForce": order_data["timeInForce"],
                        "type": order_data["type"],
                        "side": order_data["side"],
                        "stopPrice": order_data["stopPrice"],
                        "icebergQty": order_data["icebergQty"],
                        "time": order_data["time"],
                        "updateTime": order_data["updateTime"],
                        "isWorking": order_data["isWorking"],
                        "workingTime": order_data["workingTime"],
                        "origQuoteOrderQty": order_data["origQuoteOrderQty"],
                        "selfTradePreventionMode": order_data[
                            "selfTradePreventionMode"
                        ],
                    }
                )
        # logger.debug(f"[MockExecutor] Returning {len(orders)} open orders.")
        return orders

    async def _fill_order(
        self, order_id: int, price: float, quantity: Optional[float] = None
    ) -> bool:  # Added Optional for quantity
        """Internal method for simulating execution and updating the balance."""
        log_prefix = f"[MockExecutor Fill:{order_id}]"
        # logger.debug(f"{log_prefix} Attempting fill: Price={price:.8f}, Qty={quantity:.8f}")

        if order_id not in self.open_orders:
            history_entry = next(
                (o for o in reversed(self.order_history) if o["orderId"] == order_id),
                None,
            )
            status = history_entry["status"] if history_entry else "UNKNOWN"
            logger.warning(
                f"{log_prefix} Order not found in open_orders (Status: {status}). Cannot fill."
            )
            return False

        order_data = self.open_orders[order_id]
        # --- Take quantity from order_data if not passed ---
        if quantity is None:
            quantity_to_fill = order_data.get(
                "quantity_to_execute", float(order_data.get("origQty", 0))
            )
            logger.debug(
                f"{log_prefix} Quantity not provided, using quantity_to_execute/origQty: {quantity_to_fill:.8f}"
            )
        else:
            quantity_to_fill = quantity
        if quantity_to_fill <= 1e-9:
            logger.warning(
                f"{log_prefix} Fill quantity is zero or negative. Cannot fill."
            )
            # Maybe the order needs to be canceled?
            return False

        symbol = order_data["symbol"]
        side = order_data["side"]
        base_asset = self.exchange_info.get(symbol, {}).get(
            "baseAsset", symbol[:-4]
        )  # Approximate extraction
        quote_asset = self.exchange_info.get(symbol, {}).get(
            "quoteAsset", "USDT"
        )  # Approximate extraction

        # Applying slippage (for info only, does not affect balance calculation yet)
        fill_price = self._apply_slippage(price, side, order_data["type"])
        cost = fill_price * quantity_to_fill
        commission_amount = abs(cost * self.commission_pct)
        commission_asset = quote_asset  # Assume commission in USDT

        required_quote = 0.0
        required_base = 0.0
        if side == "BUY":
            required_quote = cost + commission_amount
        else:
            required_base = quantity_to_fill
            required_quote = commission_amount  # Corrected: use quantity_to_fill

        # logger.debug(f"{log_prefix} Fill Calc: Side={side}, FillPrice={fill_price:.8f}, Cost={cost:.4f}, Comm={commission_amount:.4f}")
        # logger.debug(f"{log_prefix} Required: Base={required_base:.8f} {base_asset}, Quote={required_quote:.4f} {quote_asset}")
        # logger.debug(f"{log_prefix} Available: Base={self.balances[base_asset]['free']:.8f}, Quote={self.balances[quote_asset]['free']:.4f}")

        # Balance check
        reject_reason = None
        if self.balances[quote_asset]["free"] < required_quote:
            reject_reason = f"Insufficient {quote_asset} balance"
        elif side == "SELL" and self.balances[base_asset]["free"] < required_base:
            reject_reason = f"Insufficient {base_asset} balance"

        if reject_reason:
            logger.warning(f"{log_prefix} {reject_reason}. Rejecting fill.")
            order_data["status"] = "REJECTED"  # Change status
            order_data["isWorking"] = False
            order_data["updateTime"] = int(time.time() * 1000)
            self.order_history.append(order_data.copy())  # Add to history
            await self._send_execution_report(order_data, "REJECTED")
            if order_id in self.open_orders:
                del self.open_orders[order_id]  # Remove from open
            return False

        # Update balances
        # logger.debug(f"{log_prefix} Updating balances...")
        if side == "BUY":
            self.balances[base_asset]["free"] += quantity_to_fill
            self.balances[quote_asset]["free"] -= cost
        else:  # SELL
            self.balances[base_asset]["free"] -= quantity_to_fill
            self.balances[quote_asset]["free"] += cost
        self.balances[commission_asset]["free"] -= commission_amount
        # logger.debug(f"{log_prefix} Balances updated: {base_asset}={self.balances[base_asset]['free']:.8f}, {quote_asset}={self.balances[quote_asset]['free']:.8f}")

        # Update order data
        current_filled_qty = float(order_data["executedQty"])
        new_filled_qty = current_filled_qty + quantity_to_fill  # Use quantity_to_fill
        order_data["executedQty"] = f"{new_filled_qty:.8f}"
        order_data["cummulativeQuoteQty"] = (
            f"{float(order_data['cummulativeQuoteQty']) + cost:.8f}"
        )
        order_data["status"] = "FILLED"  # Consider it fully executed
        order_data["isWorking"] = False  # Remove from book
        order_data["updateTime"] = int(time.time() * 1000)

        # Create trade record (fill)
        fill_info = {
            "price": f"{fill_price:.8f}",
            "qty": f"{quantity_to_fill:.8f}",  # Use quantity_to_fill
            "commission": f"{commission_amount:.8f}",
            "commissionAsset": commission_asset,
            "tradeId": self._generate_order_id(),  # Simulate trade ID
        }
        order_data.setdefault("fills", []).append(fill_info)  # Add to fills list

        # Remove from open orders
        if order_id in self.open_orders:
            del self.open_orders[order_id]

        # Update the history record (the last record for this ID)
        last_index = next(
            (
                i
                for i, o in reversed(list(enumerate(self.order_history)))
                if o["orderId"] == order_id
            ),
            -1,
        )
        if last_index != -1:
            self.order_history[last_index] = order_data.copy()
        else:
            self.order_history.append(order_data.copy())  # Add if not found

        # Send TRADE and FILLED report
        await self._send_execution_report(order_data, "TRADE", fill_info)
        await self._send_execution_report(order_data, "FILLED")
        logger.info(
            f"{log_prefix} Order FILLED. Price: {fill_price:.4f}, Qty: {quantity_to_fill:.4f}."
        )  # Use quantity_to_fill
        return True

    async def check_pending_orders(self):
        """Checks limit and stop orders for execution against the current candle."""
        if self._current_kline is None:
            return

        try:
            # Convert OHLC to float
            k_open = float(self._current_kline["open"])
            k_high = float(self._current_kline["high"])
            k_low = float(self._current_kline["low"])
            k_close = float(
                self._current_kline["close"]
            )  # Not used for the trigger, but for the log
            # logger.debug(f"[MockExecutor CheckOrders] Kline O={k_open:.8f} H={k_high:.8f} L={k_low:.8f} C={k_close:.8f}")
        except (TypeError, ValueError, KeyError) as e:
            logger.error(
                f"[MockExecutor CheckOrders] Invalid kline data: {self._current_kline}. Error: {e}"
            )
            return

        # Copy keys because the dictionary may change during iteration
        order_ids_to_check = list(self.open_orders.keys())
        # logger.debug(f"[MockExecutor CheckOrders] Checking {len(order_ids_to_check)} open orders: {order_ids_to_check}")

        for order_id in order_ids_to_check:
            if order_id not in self.open_orders:
                # logger.debug(f"[MockExecutor CheckOrders] Order {order_id} vanished during check. Skipping.")
                continue

            order_data = self.open_orders[order_id]
            log_prefix = f"[MockExecutor CheckOrders:{order_id}]"
            try:
                order_type = order_data["type"]
                side = order_data["side"]
                # Use final_quantity if it was calculated, otherwise origQty
                # quantity = float(order_data.get("final_quantity", order_data["origQty"])) # Assuming that final_quantity is added in place_order
                # Clarification: final_quantity is not saved in order_data. Using origQty, as it reflects what was ORDERED.
                # If there was quoteOrderQty, origQty might be 0, and quantity should be taken from fills (which is difficult here).
                # We will assume that origQty is always specified for LIMIT/STOP orders.
                quantity_to_check = order_data.get(
                    "quantity_to_execute", float(order_data.get("origQty", 0))
                )  # Corrected variable name
                if quantity_to_check <= 0:  # Skip orders with zero quantity
                    logger.warning(
                        f"{log_prefix} Skipping check for order with zero quantity."
                    )
                    continue

                if order_type == "LIMIT":
                    limit_price = float(order_data["price"])
                    fill_price = None
                    # logger.debug(f"{log_prefix} Checking LIMIT {side} @{limit_price:.8f}")
                    if side == "BUY" and k_low <= limit_price:
                        fill_price = min(
                            k_open, limit_price
                        )  # Execution at the best price
                        # logger.debug(f"{log_prefix} LIMIT BUY Triggered (Low <= Limit). Fill Price: {fill_price:.8f}")
                    elif side == "SELL" and k_high >= limit_price:
                        fill_price = max(
                            k_open, limit_price
                        )  # Execution at the best price
                        # logger.debug(f"{log_prefix} LIMIT SELL Triggered (High >= Limit). Fill Price: {fill_price:.8f}")

                    if fill_price:
                        await self._fill_order(
                            order_id, fill_price, quantity_to_check
                        )  # Corrected variable name

                elif order_type in [
                    "STOP_MARKET",
                    "TAKE_PROFIT_MARKET",
                    "STOP",
                ]:  # Added "STOP" for completeness
                    stop_price = float(order_data["stopPrice"])
                    triggered = False
                    # logger.debug(f"{log_prefix} Checking {order_type} {side} Stop@{stop_price:.8f}")
                    # BUY order (short closing): triggers if High >= StopPrice
                    if side == "BUY" and k_high >= stop_price:
                        triggered = True
                    # SELL order (long closing): triggers if Low <= StopPrice
                    elif side == "SELL" and k_low <= stop_price:
                        triggered = True

                    if triggered:
                        # logger.debug(f"{log_prefix} {order_type} {side} TRIGGERED!")
                        # For STOP_MARKET / TAKE_PROFIT_MARKET we execute at market (using k_close as simulation)
                        # Ideally, we should look at the next candle or use the stop price, but k_close is simpler
                        fill_price = k_close
                        # logger.debug(f"{log_prefix} Filling {order_type} at market price approximation: {fill_price:.8f}")
                        await self._fill_order(
                            order_id, fill_price, quantity_to_check
                        )  # Corrected variable name
                    # else: logger.debug(f"{log_prefix} {order_type} {side} NOT triggered.")

            except (KeyError, ValueError, TypeError) as e:
                logger.error(
                    f"{log_prefix} Error processing order check: {e}. Order data: {order_data}"
                )
                continue  # Move to the next order

    async def start_user_data_stream(
        self, callback: Callable[[Dict[str, Any]], Coroutine]
    ):
        """Saves the callback for sending executionReport."""
        logger.info("[MockExecutor] User data stream started (callback registered).")
        self._user_data_callback = callback

    async def stop_user_data_stream(self):
        logger.info("[MockExecutor] User data stream stopped.")
        self._user_data_callback = None

    async def _send_execution_report(
        self, order_data: Dict, execution_type: str, fill_info: Optional[Dict] = None
    ):
        """Sends a simulated executionReport message via callback."""
        if not self._user_data_callback:
            return

        # Creating a copy to avoid modifying the original
        report_data = order_data.copy()
        now_ts = int(time.time() * 1000)

        # Ensure all keys exist in report_data, otherwise use defaults
        def get_safe(key, default):
            return report_data.get(key, default)

        report = {
            "e": "executionReport",  # Event type
            "E": now_ts,  # Event time
            "s": get_safe("symbol", "UNKNOWN"),  # Symbol
            "c": get_safe("clientOrderId", ""),  # Client order ID
            "S": get_safe("side", ""),  # Side
            "o": get_safe("type", ""),  # Order type
            "f": get_safe("timeInForce", ""),  # Time in force
            "q": get_safe("origQty", "0.0"),  # Order quantity
            "p": get_safe("price", "0.0"),  # Order price
            "P": get_safe("stopPrice", "0.0"),  # Stop price
            "F": get_safe("icebergQty", "0.0"),  # Iceberg quantity
            "g": get_safe("orderListId", -1),  # OrderListId
            "C": get_safe(
                "origClientOrderId", None
            ),  # Original client order ID (for cancels) - can be None
            "x": execution_type,  # Execution type
            "X": get_safe("status", ""),  # Order status
            "r": "NONE",  # Order reject reason (TODO: Add actual reasons)
            "i": get_safe("orderId", -1),  # Order ID
            "l": "0.0",  # Last executed quantity
            "z": get_safe("executedQty", "0.0"),  # Cumulative filled quantity
            "L": "0.0",  # Last executed price
            "n": "0",  # Commission amount for last trade
            "N": None,  # Commission asset
            "T": now_ts,  # Transaction time
            "t": -1,  # Trade ID
            "I": get_safe("orderId", -1) * 10,  # ignore
            "w": get_safe("isWorking", False),  # Is the order on the book?
            "m": False,  # Is this trade the maker side? (False in mock)
            "M": False,  # ignore
            "O": get_safe("time", now_ts),  # Order creation time
            "Z": get_safe(
                "cummulativeQuoteQty", "0.0"
            ),  # Cumulative quote asset transacted amount
            "Y": "0.0",  # Last quote asset transacted amount (calculate below)
            "Q": get_safe("origQuoteOrderQty", "0.0"),  # Quote Order Qty
        }
        # Removing None from C if it ended up there
        if report["C"] is None:
            report["C"] = ""

        # Fill in details for TRADE
        if execution_type == "TRADE" and fill_info:
            report["l"] = fill_info.get("qty", "0.0")
            report["L"] = fill_info.get("price", "0.0")
            report["n"] = fill_info.get("commission", "0")
            report["N"] = fill_info.get("commissionAsset")
            report["t"] = fill_info.get("tradeId", -1)
            report["m"] = False  # In the mock, all trades are takers
            # Calculate lastQuoteTransacted (Y)
            try:
                report["Y"] = f"{float(report['l']) * float(report['L']):.8f}"
            except (ValueError, TypeError):
                report["Y"] = "0.0"

        # logger.debug(f"[MockExecutor] Sending execution report: {report['X']} for order {report['i']}")
        try:
            # Run the callback in the background to avoid blocking the current operation
            asyncio.create_task(self._user_data_callback(report))
        except Exception as e:
            logger.error(
                f"[MockExecutor] Error calling user data callback: {e}", exc_info=True
            )

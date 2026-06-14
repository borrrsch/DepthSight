# Platform Engine

The DepthSight Engine is the core of the system, responsible for executing trading operations in real-time. It coordinates all components from data ingestion to order execution.

## Key Functions
* **Real-time Trading**: Processes market data in real-time and reacts instantly to strategy signals.
* **Multi-Exchange Support**: Supports popular exchanges such as Binance, Bybit, OKX, and others.
* **Position Management**: Automatically tracks open positions, managing Stop Loss and Take Profit orders.
* **Execution Logic**: Smart order execution algorithms to minimize slippage.

## How It Works
1. **Data Ingestion**: The system receives price quotes and order book data via WebSocket.
2. **Feature Extraction**: Technical indicators and ML features are calculated from raw data.
3. **Signal Generation**: The strategy analyzes data and generates a signal (Buy/Sell/Wait).
4. **Risk Check**: The Risk Manager validates the signal against set limits.
5. **Execution**: If the check passes, the order is sent to the exchange.

## Monitoring
You can monitor the engine's performance in the "Live Trading" section or through system logs. The engine automatically reconnects on failures and synchronizes position states with the exchange.

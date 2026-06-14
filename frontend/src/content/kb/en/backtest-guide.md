# DepthSight Backtesting System

Backtests allow you to verify your trading strategy on historical data with high precision. DepthSight implements two fundamentally different testing engines, each designed for specific tasks.

## Backtester Types

### 1. Fast Vector Backtester
Uses high-performance vectorized calculations to instantly process large datasets.
* **Purpose**: Rapid discovery of profitable setups, initial hypothesis testing, and large-scale parameter optimization (Genetic Algorithm).
* **Features**: Operates on closed candles (OHLC), does not account for micro-movements within the candle.
* **Speed**: Processes years of history in seconds.

### 2. DepthSight Backtester (Event-driven)
Maximum precision simulation of real trading based on tick data and order book history (L2).
* **Purpose**: Final validation of a strategy before launching on a live account.
* **Features**: Accounts for real order book liquidity, slippage, execution latency, and commissions.
* **Precision**: Emulates market and limit order behavior exactly as it happens on the exchange.

## Launch Parameters
When running any backtest, you can configure:
* **Initial Deposit**: Amount in USDT for simulation.
* **Leverage**: Affects buying power and liquidation risk.
* **Commission**: Choose account type (VIP level) for accurate net profit calculation.
* **Execution Mode**: Market orders or Limit orders (Limit/Retest/Break).

## Analyzing Reports
DepthSight provides exhaustive analytics after the test:
* **Equity & Drawdown**: Charts for capital growth and drawdowns.
* **Trade Statistics**: Win Rate, Profit Factor, average profit/loss per trade.
* **Risk Ratios**: Sharpe, Sortino, Calmar — to assess strategy quality.
* **Chart Visualization**: All entries and exits are displayed on an interactive chart with labels for closing reasons (SL, TP, Management).

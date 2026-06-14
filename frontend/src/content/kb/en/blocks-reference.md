# DepthSight Blocks Reference

The DepthSight platform provides over 40 specialized blocks for building trading strategies. Below is a full description of all available components, divided by category.

---

## 1. Base Filters
Used to restrict strategy operations. If a filter condition is not met, the strategy will not search for an entry point.

*   **Time Filter**: Restrict trading by time (hours, minutes) and days of the week. Supports session-based trading.
*   **ADX Filter**: Trend strength check. Helps avoid entering during "choppy" markets.
*   **NATR Filter**: Filter based on Normalized Volatility (NATR). Cuts out periods of low market activity.
*   **Volatility Filter**: Assessment of current volatility relative to its moving average.
*   **Trend Filter**: Basic trend direction filter (Long/Short/Flat).
*   **BTC State Filter**: A unique filter that blocks trades if Bitcoin market conditions (dominance, volatility) contradict your strategy.

---

## 2. Foundations
Unique DepthSight deep analytics blocks working with L2 order book data and trade streams.

*   **Orderbook Density**: Searches for large limit orders (walls) in the book. Parameters allow you to set a minimum volume in USD.
*   **Tape Acceleration**: Monitors the acceleration of the trade stream. Captures moments of aggressive buying or selling.
*   **Round Number Level**: Works with psychological price levels (e.g., 50000, 60000).
*   **Price Consolidation**: Detects "shelves" — periods where the price is trapped in a narrow range.
*   **Market Activity**: Assesses overall trading activity and participant interest in the instrument.
*   **Return to Level**: Tracks the price returning to a previously broken level (retest).
*   **Level Proximity**: Checks the closeness of the price to significant support or resistance levels.

---

## 3. Technical Indicators
Classic analysis tools with deep configuration options.

*   **RSI Condition**: Overbought/oversold levels, level crossovers, and divergences.
*   **MACD Cross**: Crossover of the MACD and signal lines or histogram zero-line breach.
*   **Bollinger Bands**: Trading on bounces from channel boundaries or breakouts.
*   **Stochastic**: Identifying reversal zones with filtering by %K and %D lines.
*   **MA Cross**: Crossover of two moving averages (SMA, EMA, WMA).
*   **ATR Condition**: Using Average True Range to assess current price dynamics.
*   **Candlestick Patterns**: Detection of classic patterns (Pin Bar, Engulfing, Doji, Inside Bar).

---

## 4. Advanced Logic
Container blocks for creating complex hierarchical conditions.

*   **AND Block**: Logical "AND". The signal passes only if ALL nested conditions are true.
*   **OR Block**: Logical "OR". The signal passes if AT LEAST ONE nested condition is true.
*   **Senior TF Confluence**: Check nested conditions on a higher timeframe (e.g., enter on 1m when the 1h trend is confirmed).
*   **Value Comparison**: A universal block for comparing two values (price, indicators, block results).
*   **Price vs Level**: Comparison of the current price with a dynamic or static level.

---

## 5. Position Management
Defines system behavior after a trade is opened.

*   **Take Profit**: Fixing profit by fixed price, percentage, or ATR.
*   **Stop Loss**: Risk limitation. Supports adaptive placement behind densities or price extremes.
*   **Trailing Stop**: Dynamically moving the stop-order behind the profit.
*   **Partial TP**: Closing part of the position (e.g., 50%) when the first target is reached.
*   **Break-Even**: Moving the stop-loss to the entry point when a specified profit is reached.
*   **Grid/DCA**: Building an order grid for position averaging when the price moves against the entry.
*   **Time Exit**: Automatic trade closure after a specified duration.
*   **Regime Change Exit**: Closing the position when the market phase changes.

---

## 6. Artificial Intelligence (AI & ML)
*   **ML Confirmation**: Signal confirmation from DepthSight's neural network (Confidence Score).
*   **Oracle Regime**: Following the global market regime as determined by AI.
*   **AI Online Agent**: Connecting a dynamic agent for adaptive trade management.

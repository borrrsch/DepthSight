# Dynamic Links: How Blocks "Talk" to Each Other

In DepthSight, strategy blocks are not just independent conditions; they are a team of experts that can pass data to one another. The **Dynamic Links** feature allows one block to use the output of another.

This transforms your strategy from a "rigid" algorithm into a flexible system that adapts to the market.

## Practical Examples for Traders

### 1. Stop Loss Behind an Orderbook "Wall"
Instead of setting a fixed 0.5% stop loss, you can link it to real money in the order book.
*   **Block A (Orderbook Density)**: Searches for a large buy density (e.g., $500,000).
*   **Block B (Stop Loss)**: In the "Price" parameter, you select **Source: Block Result** and specify the ID of Block A.
*   **Result**: Your stop loss will automatically be placed just below the found density. If the density moves higher, the stop loss for new trades will adapt accordingly.

### 2. Stop Loss Behind the Breakout Candle Low
A popular technique: when a level is broken, place the stop behind the "signal" candle.
*   **Block (Stop Loss)**: Select **Source: Candle**, key `low`, offset `shift: 0`.
*   **Result**: The robot will take the exact low price of the current (signal) candle and set the stop loss right there. You don't need to guess the volatility of the breakout.

### 3. Take Profit at a Level from Another Block
Imagine one block finds a strong historical level (Significant Level), and you want to close your position at that level.
*   **Block A (Significant Level)**: Finds yesterday's high.
*   **Block B (Take Profit)**: References the result of Block A.
*   **Result**: The take profit will always be exactly at yesterday's high, no matter how high or low it is.

## What Data Can Be Passed?
Through dynamic links, blocks can exchange any information:
*   **Prices**: The price of a found level, density, fractal, or extreme.
*   **Indicator Values**: RSI, ATR, or moving averages from any timeframe.
*   **Trade State**: Current profit in risk units (R/R), number of averages (DCA), or time in position.

## How to Configure in the Editor?
In the configuration panel of any block, next to numerical parameters, there is a "link" icon. Clicking it opens a source selection (**Source**):
1.  **Constant**: A fixed number (as usual).
2.  **Block Result**: Choose the ID of another block from your strategy.
3.  **Candle**: OHLC data (Open, High, Low, Close, Volume).
4.  **Indicator**: The value of any technical indicator.
5.  **Position State**: Data about your currently open position.

Using dynamic links is the transition from simple bots to professional trading systems that "understand" the market structure.

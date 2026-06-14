# Logic Guide: The "Brains" of Your Strategy

Logic blocks in DepthSight do not analyze the market themselves. They control how other conditions are combined. Below is a breakdown of all 5 blocks in the "What-Why-Example" format.

---

## 1. AND Block
*   **What it is**: A container block that requires **all** nested conditions to be met simultaneously.
*   **Why**: To filter out random signals and enter only when there are multiple confirmations.
*   **Example**: Place `RSI < 30` and `Orderbook Density` inside. The bot will only buy when the price is both cheap and protected by a large order.

## 2. OR Block
*   **What it is**: A container block that triggers if **at least one** of the nested conditions is met.
*   **Why**: For creating flexible strategies that can enter based on different scenarios.
*   **Example**: Place `Breakout Yesterday High` and `TradingView Signal` inside. The bot will enter if either one or the other occurs.

## 3. Senior TF Confluence (Multi-Timeframe)
*   **What it is**: A special container that checks conditions on a timeframe higher than your working one (e.g., on 1h instead of 1m).
*   **Why**: To never trade against the "Big" trend. If everything is falling on the 1h, buying on the 1m is a bad idea.
*   **Example**: Nest a trend indicator inside this block and select "1 Hour." Now, on the 1m, the bot will only buy if the trend is also UP on the 1h.

## 4. Value Comparison
*   **What it is**: A universal tool for comparing any two numbers in the system (prices, indicators, block results).
*   **Why**: Allows creating your own unique rules that are not available in standard blocks.
*   **Example**: "If current price is higher than the closing price 5 candles ago."

## 5. Price vs Level
*   **What it is**: A specific block for comparing the current price with a specific level found by another block.
*   **Why**: Allows building logic for "breakouts" or "bounces" from dynamic levels.
*   **Example**: "If price is higher than the level from the Significant Level block by more than 0.2%."

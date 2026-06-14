# Filters Guide: How to Protect Your Deposit

Filters are the "smart kill-switch" of your strategy. They don't tell the bot when to buy; they tell it when **not** to trade. Below is a complete breakdown of all 10 filters, strictly following the 3-point structure.

---

## 1. Time Filter (Manual Hours)
*   **What it is**: Restricting the bot's operation to specific hours and minutes throughout the day.
*   **Why**: To eliminate trading during periods of low liquidity or during technical breaks on the exchange.
*   **Example**: "Trade only from 10:00 to 20:00" so the bot only works when you are at your computer and can monitor it.

## 2. Trading Session (Preset Sessions)
*   **What it is**: Quick time settings tied to the opening of major world exchanges (London, New York, Tokyo).
*   **Why**: Each session has its own character. Breakout strategies work better in London, while scalping is often suited for Asia.
*   **Example**: "Enable only the New York session." The bot will be active during the most volatile time when the largest trades are made.

## 3. BTC State Filter (Market Mood)
*   **What it is**: A global "mood" sensor for Bitcoin that broadcasts its state to all altcoins.
*   **Why**: During panic sell-offs of Bitcoin (Dump), technical analysis on other coins stops working.
*   **Example**: Set a block on entries during a "Panic Dump." The bot will not buy ETH if BTC is currently plummeting.

## 4. ADX Filter (Trend Strength)
*   **What it is**: An indicator that determines whether there is a directed movement in the market or if the price is ranging.
*   **Why**: To prevent the bot from trading based on trend indicators when there is actually no trend present.
*   **Example**: Set ADX > 25. The bot will ignore any signals until the market starts to "accelerate."

## 5. NATR Filter (Volatility in %)
*   **What it is**: A measure of the average price range in percentages relative to its cost.
*   **Why**: Trading coins with very low movement potential is unprofitable due to commissions.
*   **Example**: NATR > 0.5. The bot will only select "live" assets that are capable of moving enough distance to hit a take-profit.

## 6. Volatility Squeeze (Coiled Spring)
*   **What it is**: A detector for abnormal quietness when price stays in a very narrow range for a long time.
*   **Why**: After every strong squeeze, a powerful explosive impulse occurs in the market.
*   **Example**: The bot finds a "squeeze" and waits for a breakout. This allows entering a trade at the very beginning of a massive move.

## 7. Rel Vol Filter (Relative Volume)
*   **What it is**: A block comparing the current trading volume with its average value over the last 24 hours.
*   **Why**: Increased volume confirms that real money has entered the coin and the movement is not accidental.
*   **Example**: Rel Vol > 2.0. The bot will only pay attention to a coin if there is significantly increased interest in it today.

## 8. Volatility Filter (Range Filter)
*   **What it is**: A check of the ratio between the maximum and minimum price within a candle.
*   **Why**: Helps cut out excessively "noisy" or manipulative coins with huge spikes.
*   **Example**: The bot will prohibit an entry if the current candle has an abnormally long wick (shadow), which often happens before a reversal.

## 9. Correlation
*   **What it is**: A mathematical check of how synchronously a coin moves behind Bitcoin.
*   **Why**: To find assets that are "stronger than the market" (rising faster than BTC) or "weaker" (falling faster).
*   **Example**: Set correlation < 0.7 to find market-independent movements and unique situations.

## 10. Trend Filter (Directional Filter)
*   **What it is**: A basic check of price position relative to a moving average (SMA/EMA).
*   **Why**: Following the main rule of trading: "Trend is your friend" (only trade in the direction of the trend).
*   **Example**: "Price above EMA 200." The bot will only look for buy trades (LONG), ignoring sell signals.

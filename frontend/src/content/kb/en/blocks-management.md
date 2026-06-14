# Management Guide: Takes, Stops, and Grids

Management blocks are responsible for how the bot behaves after entering a trade. This is the foundation of your risk management. Below is a breakdown of all 9 blocks in the "What-Why-Example" format.

---

## 1. Take Profit
*   **What it is**: Setting a profit target. Can be in percentages, USDT, or based on ATR.
*   **Why**: To lock in profits on time and not wait for the market to reverse.
*   **Example**: "Take Profit 1% from entry." As soon as the price rises by 1%, the bot will automatically close the trade.

## 2. Stop Loss
*   **What it is**: Limiting the maximum allowable loss in a single trade.
*   **Why**: Protecting your deposit from total loss during sharp market movements.
*   **Example**: "Adaptive stop behind the nearest order book density." The bot will hide your risk behind real whale money.

## 3. Trailing Stop
*   **What it is**: A sliding stop-loss that "follows" the price as long as it moves into profit.
*   **Why**: To squeeze the maximum out of a strong trend and not close too early.
*   **Example**: "Trailing 0.3%." If price has risen by 2% and starts to fall, the bot will close the trade with a 1.7% profit, protecting most of the gain.

## 4. Move to Break-Even
*   **What it is**: Automatically moving the stop-loss to the entry point once the price has covered part of the path to the profit target.
*   **Why**: To turn the trade into a "free" one. After this, you can no longer lose money.
*   **Example**: "Upon reaching +0.5% profit, move the stop to break-even."

## 5. DCA / Scale In (Averaging)
*   **What it is**: An algorithm for buying more of an asset if the price goes against your entry.
*   **Why**: Improves the average entry price, allowing you to exit the trade with profit on a small pullback.
*   **Example**: "Buy an equal amount for every 1.5% drop."

## 6. Grid Management
*   **What it is**: Building an entire network of limit orders within a specified price range.
*   **Why**: Allows earning on price fluctuations within a corridor (flat/range).
*   **Example**: The bot places 10 buy orders below the current price, collecting all "dips."

## 7. Conditional Exit
*   **What it is**: Closing a trade based on an event rather than a price level.
*   **Why**: To exit the market if the entry signal is no longer relevant.
*   **Example**: "Close position if RSI crosses 70 from top to bottom" (signaling the impulse is over).

## 8. Time Exit
*   **What it is**: Forcibly closing a trade after a specified duration.
*   **Why**: To avoid "hanging" in positions over the weekend or overnight when you are not trading.
*   **Example**: "Close trade after 4 hours if it is still open."

## 9. Regime Change Exit
*   **What it is**: Emergency closure of all positions based on a signal from the DepthSight AI Oracle.
*   **Why**: If the AI sees that the market phase has changed from "Growth" to "Crash," the bot will exit trades in advance.
*   **Example**: The bot closes a LONG as soon as the Oracle issues a "Bearish Trend" status for the entire market.

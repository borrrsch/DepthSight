# Risk Management Guide

The Risk Management module in DepthSight is your primary defender. It operates at the core Engine level and has the highest priority. Even if a strategy or the AI Oracle gives a buy signal, the Risk Manager will block it if safety rules are violated.

In this article, we will detail all available settings, including dynamic risk scaling.

---

## 1. Global Limits

These settings apply to your entire account or portfolio. If one of these limits is reached, the bot completely halts trading.

### Daily Max Loss
*   **How it works**: Sets the maximum percentage loss allowed based on the starting balance of the current day.
*   **Example**: You set a limit of 2%. If your starting balance was $10,000 and you lose $200, the bot blocks all new entries ("Daily Loss Reached"). Exactly at 00:00 UTC, the counter resets, and trading resumes.

### Max Drawdown
*   **How it works**: Tracks the balance drop from its absolute historical peak.
*   **Why use it**: If your deposit grew from $10,000 to $15,000, the drawdown is calculated from $15,000. If the limit is set at 10%, the bot stops working if the balance drops to $13,500, protecting your earned profits.

### Max Consecutive Losses
*   **How it works**: Stops trading after a series of losing trades (e.g., 5 stop-losses in a row).
*   **Why use it**: Protects against fatal algorithm errors or a broken market structure. Gives you time to review the strategy.

### Max Concurrent Trades
*   **How it works**: Limits the number of simultaneously open positions.
*   **Why use it**: Prevents rapid account liquidation due to insufficient free margin if several strategies generate signals at once.

---

## 2. Position Management (Per-Trade Risk)

### Risk Per Trade
*   **How it works**: The main money management setting. Determines what percentage of the total deposit you are willing to lose in a single trade.
*   **Mechanics**: If the risk is 1% and the deposit is $10,000, the bot will calculate the position size so that if the stop-loss is hit, you lose exactly $100. The position size is calculated dynamically depending on the distance to the stop loss.

### Max Stop Distance
*   **How it works**: Prohibits the bot from entering a trade if the stop-loss is too far away.
*   **Why use it**: If the market is highly volatile, a stop-loss behind an order book density might be 10% away from the entry point. This is dangerous. By setting a limit (e.g., 5%), you filter out such high-risk trades.

---

## 3. Dynamic Risk Management (Dynamic RM)

This is an advanced feature (Strategy-Symbol Adjustment) that allows the bot to automatically scale the risk size for specific "Strategy + Coin" pairs based on their recent performance.

### How does it work?
The system analyzes the last N trades (Window Size).
*   **Risk Reduction**: If a strategy trading ETH consistently incurs losses (Win Rate falls below a threshold, or a series of stops occurs), the Risk Manager **reduces the Risk Multiplier** from 1.0 to 0.75, then to 0.5. You start losing less money during a bad phase.
*   **Cooldown**: In the event of severe losses, the strategy for this coin can receive a "time penalty" (e.g., a trading ban for 1 hour).
*   **Recovery**: If the strategy starts earning again with the reduced volume (e.g., 3 profits in a row), the risk multiplier gradually returns to normal (1.0).

---

## 4. Auto-Blacklist

The system allows you to set up automatic exclusion of coins from trading.
*   **Logic**: You can create a rule: "If 3 stop-losses are hit on a coin within 2 hours, add it to the blacklist for 24 hours."
*   **Why use it**: If a coin (like DOGE) becomes completely unpredictable or heavily manipulated, the bot will stop trying to trade it and switch to other assets in the list.

### Summary
Risk Management in DepthSight is fully automated. Configure these rules once, and you'll never have to worry about emotional decisions or losing control of your bots.

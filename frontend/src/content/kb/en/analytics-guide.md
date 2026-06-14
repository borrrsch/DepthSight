# Analytics and Statistics: Finding Weaknesses

Even the best strategy has its vulnerabilities. The **Analytics** tab in DepthSight is designed not just to show a pretty equity curve, but to help you find patterns in your losses. 

By learning to read these charts, you can multiply your strategy's performance simply by adding a couple of the right filters.

---

## 1. PnL by Symbol
If you are running a strategy or portfolio on multiple coins (or using Dynamic Selection), this chart is your best friend.
*   **What it shows**: A bar chart where each coin displays its PnL (net profit).
*   **How to use it**: It often happens that a strategy works perfectly on BTC and ETH, but "bleeds" all its profit on DOGE or SOL due to their specific volatility.
*   **Action**: See a coin with a massive red bar? Exclude it from trading for this strategy via the symbol settings.

## 2. Hourly PnL
An interactive bar chart showing the strategy's results broken down by 24 hours.
*   **What it shows**: During which hours of the day the bot earns the most, and when it loses (green and red bars).
*   **How to use it**: The crypto market is 24/7, but volumes change. You might see that the strategy consistently hits stop-losses from 02:00 to 06:00, for example.
*   **Action**: You can simply **click on a losing bar** right on the chart! That hour will be disabled (the bar turns gray), and the platform will automatically recalculate all backtest statistics excluding that hour. If the result improves, add this rule to your Time Filter block.

## 3. Day of Week PnL
*   **What it shows**: A bar chart of the strategy's profitability depending on the day of the week (Monday - Sunday).
*   **How to use it**: Trend-following strategies often produce false signals on weekends due to volume drops.
*   **Action**: Just like with hours, simply **click on a losing day** (e.g., Saturday) to exclude it from the analytics. If you like the newly recalculated result, apply these settings to your strategy.

## 4. Phantom Analysis (Break-Even Analysis)
A unique DepthSight tool for evaluating the effectiveness of your stop-losses.
*   **What it shows**: What would have happened to the trades if the bot had NOT moved them to Break-Even or closed them via Trailing Stop.
*   **How to use it**: If the tab shows a high "Stolen Profit" metric, it means your Break-Even is triggering too early. The price clips your stop and then goes to the Take-Profit.
*   **Action**: Increase the activation distance in the settings of the `Move to Break-Even` block.

---

## 5. Key Metrics: Win Rate vs Profit Factor

Many beginners only look at the **Win Rate** (percentage of profitable trades), but this is a mistake. A strategy with a 30% Win Rate can be highly profitable if its average win is huge, while a strategy with a 90% Win Rate can wipe out a deposit with a single giant loss.

Look at the **Profit Factor**:
*   *Profit Factor < 1*: The strategy is losing money.
*   *Profit Factor = 1.1 - 1.4*: A decent strategy.
*   *Profit Factor > 1.5*: An excellent strategy.
*   *Profit Factor > 3.0*: Caution, over-optimization (curve fitting) might have occurred during the backtest. Run it in Paper Trading mode before using real money.

### AI Assistant Tip
If you don't know how to interpret the charts, simply click the **Ask AI Copilot** button. It will study the heatmaps itself and tell you: *"I noticed that the strategy loses 30% of its profit on Fridays and is consistently unprofitable on the SOL coin. I recommend excluding them."*

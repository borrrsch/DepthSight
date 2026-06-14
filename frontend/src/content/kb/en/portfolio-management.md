# Portfolio Management: Running Multiple Strategies

Trading a single coin or strategy always carries risk. DepthSight allows you to combine different strategies into portfolios to diversify and smooth out your equity curve.

## 1. Why Do You Need a Portfolio?
*   **Diversification**: If a trend-following strategy incurs losses in a flat market, a mean-reversion strategy can compensate.
*   **Lower Drawdown**: The aggregate drawdown of a portfolio of non-correlated strategies is always less than that of individual strategies.
*   **Scaling**: Allows you to efficiently manage larger capital by distributing it across different assets (e.g., BTC, ETH, SOL).

## 2. How to Run a Portfolio Test
1.  Navigate to the **Laboratory** section.
2.  Switch the mode at the top of the page from **Single Strategy** to **Portfolio Mode**.
3.  Click **Add Strategy** to select algorithms from your library.
4.  For each strategy, configure:
    *   The coins to trade.
    *   Risk per trade (as a % of the total portfolio deposit).
5.  Run the **Portfolio Backtest**.

## 3. Portfolio Analytics
Once the test is complete, you will receive consolidated statistics:
*   **Total Portfolio PnL**: Overall net profit.
*   **Portfolio Max Drawdown**: The maximum drawdown of the entire portfolio.
*   **PnL by Strategy / Symbol**: A detailed breakdown showing exactly which strategy or coin generates the most profit and which is dragging the portfolio down.

### Tip:
Always conduct a portfolio backtest before launching multiple bots on a live account. This ensures they won't consume all your available margin simultaneously.

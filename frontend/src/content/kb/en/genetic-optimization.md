# Genetic Optimization: Finding Ideal Parameters

Manually finding parameters (which RSI period to use, where to place the stop loss) can take days. The **Genetic Command Center** in DepthSight does this automatically using machine learning algorithms inspired by evolution.

## 1. How It Works?
The algorithm creates a "population" (hundreds of variants of your strategy with random settings). It then tests them, selects the most profitable ones, crossbreeds them, and adds "mutations." This process repeats over many generations until the ideal parameters are found.

## 2. Running the Optimization
1.  Go to the **Genetics Lab** tab in the Laboratory section.
2.  Select the base strategy (Seed Strategy) you want to improve.
3.  Configure the **Fitness Function** — this is your main goal:
    *   *Maximize Net Profit*: Search for maximum profit.
    *   *Maximize Sharpe Ratio*: Best balance between risk and reward.
    *   *Minimize Drawdown*: Safest trading with minimal drawdowns.
4.  Set the boundaries for the "genes" (e.g., allow the RSI period to change between 10 and 30).
5.  Click **Start Evolution**.

## 3. Hall of Fame
During evolution, the best strategies found will be placed in the **Hall of Fame**. You can view the equity curve of any of them and save it to your library with one click for Live trading.

### Warning: The Danger of Overfitting
The genetic algorithm might find settings that worked perfectly in the past but will break tomorrow. Always test the found strategy on a new time period (Out-of-sample) before risking real money.

# AI Oracle: Recognizing Market Regimes

Unlike classic indicators that try to guess where the price will go (up or down), the DepthSight AI Oracle solves a much more complex problem—it determines the **market regime**.

## How Does the Oracle Work?

The Oracle is a machine learning model (Gaussian Mixture Model) that analyzes the market through three unique "sensors." It doesn't look at the chart the way a human does.

### 1. Sensor "Memory" (Market Forgetting Speed)
Compares short-term volatility with long-term volatility.
*   **Logic**: If short-term volatility sharply exceeds the long-term, it means the market has "forgotten" its past calm phase and transitioned into a state of panic or euphoria.

### 2. Sensor "News Background" (Sentiment)
Analyzes external data on positive, negative, and important news.
*   **Logic**: Evaluates the "asymmetry" of the news background. A strong bias to one side foreshadows a strong trend.

### 3. Sensor "Complexity" (Complexity Drift)
Uses the ratio of ATR (Average True Range) to the current closing price.
*   **Logic**: Helps the Oracle understand how "noisy" or "clean" the current price movement is.

---

## What Does the Oracle Output?

Every candle, the Oracle outputs two values:
1.  **Regime**: The identifier of the current market phase (e.g., "Low Volatility/Flat," "High Volatility/Trend," or "Extreme Shock").
2.  **Confidence**: A value from 0 to 100%, indicating how confident the model is in its prediction.

## How to Use This in Strategies?

You can use the Oracle in the Strategy Editor to adapt your bot's behavior to the current market phase:

1.  **Regime Change Exit (Emergency Exit)**
    *   You can add this block to the Management section. If the Oracle detects a sharp regime change (e.g., moving from a calm market to an extreme shock), the bot will immediately close all positions without waiting for the stop-loss to trigger.
2.  **Oracle Confidence Filter**
    *   In the strategy settings (Config Panel), you can set a minimum Oracle Confidence threshold.
    *   *Example*: If you set it to 70%, the bot will only trade when the AI is absolutely certain about the current market state. If confidence is 40% (the market is "confusing")—trading will be paused.

### Pro Tip
The Oracle does not say "Buy" or "Sell." It says "There is a storm right now, better use breakout strategies" or "It's calm right now, turn on channel scalping." Use it as a global filter to activate or deactivate your bots.

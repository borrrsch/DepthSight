# AI Copilot: Your Trading Assistant

AI Copilot is an intelligent assistant based on large language models, deeply integrated into the DepthSight platform. It helps turn trading ideas into working algorithms, analyzes the market, and improves your results.

## Copilot Features

### 1. Creating Strategies by Description (Text-to-Strategy)
You can describe your strategy logic in natural language.
* *Example request*: "Create a counter-trend strategy for ETH that enters when RSI is oversold on 5 minutes, if there is a large buy density in the order book."
* *Result*: AI will automatically add RSI and Orderbook Density blocks and combine them in an AND group with optimal settings.

### 2. Generating Strategies from Screenshots (Image-to-Strategy)
You no longer need to spend time explaining logic with words. If you spot a great setup on a chart, just upload a screenshot!
* *How it works*: Take a screenshot of a chart (e.g., from TradingView) showing levels, indicators, or patterns, and send it to Copilot.
* *Result*: The AI recognizes visual elements (e.g., "I see a consolidation breakout and a Pin Bar pattern") and automatically assembles the corresponding block structure in the editor.

### 3. Analyzing Backtests and Live Trading
Copilot is not just a builder; it's your personal risk manager.
* *How it works*: After running a backtest or a series of live trades, ask the AI to analyze the results.
* *Result*: Copilot will examine your equity curve, drawdown, and profit factor, and point out weaknesses. It might say: *"Your strategy loses money during the Asian session. I recommend adding a Time Filter to exclude trading from 00:00 to 08:00."*

### 4. Parameter Optimization and Logic Explanation
* **Fine-tuning**: If you already have a strategy, Copilot can suggest optimal indicator periods based on current market volatility or recommend ATR-based stop losses.
* **Explanation**: Click on the assistant icon in any block to get a detailed explanation of how specific parameters affect the signal and in which market phases the block works best.

## Compatibility Warnings
Sometimes Copilot may suggest features that are under development or not supported by the current engine version. In this case, an **"Unsupported Features"** warning will appear on the canvas. The platform will automatically highlight such blocks so you can adjust them before launching.

## How to Use Effectively
1. Be specific when describing entry and exit conditions.
2. When uploading screenshots, try to make the logic clearly visible (e.g., circle the consolidation zone with a marker).
3. Use Copilot as a partner: let it generate the "skeleton" of the strategy and analyze errors, but always make the final decision yourself.

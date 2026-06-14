# Dynamic Coin Selection

The Dynamic Coin Selection system allows DepthSight to automatically find the most promising assets for trading in real-time. Instead of being limited to a static list of pairs, the bot scans the entire market and selects coins with maximum activity.

## How Dynamic Selection Works
The system analyzes all available trading pairs on the exchange and filters them based on two key metrics:

### 1. Relative Volume (RelVol)
The bot compares current trading volume with its average value over the last 24 hours.
*   **Why it matters**: A volume spike often precedes a strong directional move.
*   **RelVol Threshold**: Default is 5.0. This means a coin comes into focus if its volume is 5 times higher than average.

### 2. Volatility (NATR)
Uses the Normalized Average True Range (NATR).
*   **Why it matters**: Strategies need volatility to reach profit targets. If a coin is "standing still," trading it is inefficient.
*   **NATR Threshold**: Default is 1.0. Filters out instruments with low movement amplitude.

## Editor Configuration
When creating a strategy, you can choose:
*   **Static Mode**: Trade only one selected coin (e.g., BTC/USDT).
*   **Dynamic Mode**: Allow the system to select "hot" assets based on set filters.

## Benefits
*   **Time Saving**: You don't need to manually search for what's "pumping" or actively trading today.
*   **Focus on Liquidity**: The bot always trades where the money and movement are.
*   **Adaptability**: The coin list updates automatically as the market phase changes.

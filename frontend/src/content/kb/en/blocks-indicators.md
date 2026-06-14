# Indicators Guide: The Mathematics of Success

Technical indicators are classic tools that translate the chaos of price action into clear numbers and charts. In DepthSight, they are packaged into convenient blocks that you can customize and combine.

Below is a breakdown of all blocks in this section using the "What-Why-Example" format.

---

## 1. RSI Condition (Relative Strength Index)
*   **What it is**: An indicator that shows market "overheating." It measures the speed and change of price movements.
*   **Why**: Helps understand when the price has flown too far up (overbought) or fallen too far down (oversold).
*   **Example**: Set the condition "RSI < 25." The bot will only signal when the price drops to extreme values, from which a quick bounce usually occurs.

## 2. MACD Condition (Moving Average Convergence Divergence)
*   **What it is**: A trend and momentum indicator consisting of two lines and a histogram.
*   **Why**: To catch the moment when a trend begins to "run out of steam" or, conversely, gains strength.
*   **Example**: Set the condition "MACD lines crossover upwards." This is a classic buy signal at the start of a new uptrend.

## 3. Bollinger Bands
*   **What it is**: A dynamic channel around the price. Its boundaries expand during high volatility and contract during calm periods.
*   **Why**: Price stays inside the channel 90% of the time. Touching the boundaries often means the price has gone too far and will soon return to the middle.
*   **Example**: "Price below the lower band." The bot will look for buys when the price is abnormally cheap relative to recent fluctuations.

## 4. Stochastic Condition
*   **What it is**: An oscillator that compares the current price to the price range over a specific period.
*   **Why**: Very accurate for finding reversals in sideways (flat) movements.
*   **Example**: Condition "%K line crosses %D above level 80." This signals that growth has slowed and the price is ready to start falling.

## 5. MA Cross (Moving Average Crossover)
*   **What it is**: A comparison of two average prices over different periods (e.g., 10 and 50 candles).
*   **Why**: Determines the direction of the "global" trend.
*   **Example**: "SMA 10 is above SMA 50." The bot will only open LONG trades because the overall market direction is up.

## 6. ATR Condition (Average True Range)
*   **What it is**: A volatility indicator that shows how much the price moves on average per candle.
*   **Why**: To adapt the strategy to current market "noise." If ATR is high, targets and stops should be wider.
*   **Example**: Don't enter a trade if the current candle is larger than 3 average ATRs (protection against entering at the very peak of an impulse).

## 7. Candlestick Patterns
*   **What it is**: A block for automatically searching for formations: Pin Bar, Engulfing, Doji, etc.
*   **Why**: Patterns show the psychological reaction of market participants in a single candle.
*   **Example**: "BULLISH Pin Bar." The bot will find a candle with a long lower tail—a signal that sellers tried to push the price down, but buyers defeated them.

---

### Pro Tip:
Don't use indicators alone. The best strategy is an **Indicator** (to define the zone) + a **Foundation** (for confirmation with real money in the order book).

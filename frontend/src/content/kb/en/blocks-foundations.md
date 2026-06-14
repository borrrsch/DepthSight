# Foundations Guide: Market Mechanics and Real Money

"Foundations" are what separate a pro from a novice. They look at the reasons behind price movements: real money and psychology. Below is a breakdown of all 16 blocks in the strict "What-Why-Example" format.

---

## 1. Orderbook Zone (Densities)
*   **What it is**: Searching for large limit orders ("walls") from market makers and whales.
*   **Why**: Price often bounces off large sums of money. These are your "concrete" support levels.
*   **Example**: "Find density over $1,000,000." The bot will see this barrier and use it as an entry anchor.

## 2. L2 Microstructure
*   **What it is**: Deep analysis of the balance between limit buys and sells in the order book.
*   **Why**: Allows you to see "hidden pressure." If there are 3 times more buyers, the price is highly likely to rise.
*   **Example**: Don't buy if the order book is "empty" or skewed towards sellers, even if the chart looks good.

## 3. Level Proximity
*   **What it is**: A sensor indicating that price has come very close to an important level (e.g., within 0.1%).
*   **Why**: Allows activating trading logic specifically in the "zone of interest" rather than in the middle of a blank chart.
*   **Example**: "When approaching the Daily High, activate trade stream monitoring."

## 4. Tape Condition (Tape Analysis)
*   **What it is**: Real-time monitoring of all executed trades.
*   **Why**: To catch the moment when an aggressive buyer ("vacuum") enters the market.
*   **Example**: "Tape acceleration > 2.5." The entry will only occur during a real explosive market impulse.

## 5. Volume Confirmation
*   **What it is**: Verifying the trading volume on the current signal candle.
*   **Why**: Filters out "fake" movements on low volume that quickly fizzle out.
*   **Example**: "Candle volume 1.8x higher than average." This ensures the movement is backed by crowd money.

## 6. Significant Level
*   **What it is**: Automatic search for daily/weekly/monthly highs and lows.
*   **Why**: Saves you from manual level drawing. The bot sees the market's primary targets itself.
*   **Example**: Set an entry on "Breakout Daily High."

## 7. Return to Level (Retest)
*   **What it is**: Detecting a level breakout followed by a return to that level for confirmation.
*   **Why**: Allows entering a trade with confirmation and very low risk.
*   **Example**: Price breaks 100, returns to 100, and the bot buys. This is a classic profitable entry point.

## 8. Price Consolidation ("Shelves")
*   **What it is**: Searching for areas where price stays in a very narrow corridor for a long time ("accumulating").
*   **Why**: A long consolidation is always followed by a powerful breakout. This is an opportunity to enter at the very beginning of a trend.
*   **Example**: The bot finds a 30-minute "shelf" and prepares for a breakout of its boundaries.

## 9. Price Action Analyzer
*   **What it is**: Recognizing market structure: Higher Highs (HH) or Lower Lows (LL).
*   **Why**: To trade strictly according to the current trend structure, identifying moments of its reversal.
*   **Example**: "Enter only if a Higher Lows structure is present."

## 10. Round Level
*   **What it is**: Tracking psychological prices like 50,000, 1.0, or 100.
*   **Why**: Humans most often place their stop-losses and limit orders near these round numbers.
*   **Example**: Use a round number as a take-profit filter, as price often reverses just before hitting it.

## 11. Market Activity (Market Heat)
*   **What it is**: Evaluating the frequency of trades (not just volume, but their count).
*   **Why**: To avoid trading in a "dead" market where movements are chaotic and random.
*   **Example**: "Activity > High." The bot only works during moments of maximum trader interest in the coin.

## 12. Open Interest (OI)
*   **What it is**: The number of active (unclosed) positions in the futures market.
*   **Why**: Rising OI along with price confirms "fresh blood" entering the trend.
*   **Example**: "OI rising for 5 minutes." This signals that the current rally is real buying, not just short covering.

## 13. Correlation (BTC Sync)
*   **What it is**: Checking how exactly a coin follows Bitcoin's movements.
*   **Why**: To find leader coins that move on their own, independent of the overall market.
*   **Example**: "Correlation < 0.5." The bot will select a coin with a unique situation that "doesn't care" about a BTC drop.

## 14. Classic Pattern
*   **What it is**: Automatic recognition of formations: Pin Bar, Engulfing, Doji.
*   **Why**: Patterns show the crowd's instantaneous reaction to price.
*   **Example**: "Buy when Bullish Engulfing appears."

## 15. Level Touch Analyzer
*   **What it is**: A counter for how many times a specific price level has been touched.
*   **Why**: The more times a support level is touched from above, the higher the chance it will be broken downward next time.
*   **Example**: "Sell on the 4th touch of a support level" (trading on level weakening).

## 16. TradingView Signal
*   **What it is**: A block for receiving external signals via Webhooks (from your TradingView indicators).
*   **Why**: Allows using any unique TradingView developments inside DepthSight.
*   **Example**: "BUY signal received from TradingView" -> Bot checks order book density and opens a trade.

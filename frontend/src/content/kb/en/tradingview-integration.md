# TradingView Integration: A Symbiosis of Two Platforms

Do you have a favorite private indicator on TradingView (Pine Script) that you want to automate? In DepthSight, the **TradingView Signal** block allows you to receive external signals via Webhook and use them as part of your trading logic.

But the main advantage of DepthSight is that you can freely combine these external signals with the platform's internal filters and L2 data.

---

## 1. How it works in DepthSight
In regular bots, a signal from TradingView immediately results in a buy or sell. This is dangerous because chart indicators are "blind"—they cannot see the real liquidity in the order book.

In DepthSight, an external signal is just another building block in your constructor.

### Example of "Symbiosis":
You nest two conditions inside an **AND** block:
1.  **TradingView Signal** (a "BUY" alert arrived from your Pine Script).
2.  **Orderbook Density** (a density > $500,000 found in the order book).

**Result**: The bot will receive the signal from TradingView but will **NOT open a trade** until it verifies that right now, there is real money in the order book ready to protect your position. This reduces false entries tenfold.

---

## 2. Webhook Setup (Step-by-Step)

### Step 1: Getting the URL in DepthSight
1.  Add the `TradingView Signal` block to the **Entry Conditions** section of your strategy.
2.  Upon saving the strategy, the system will generate a unique **Webhook URL** for you. Copy it.

### Step 2: Setting up the Alert in TradingView
1.  Open the chart of the desired coin on TradingView.
2.  Create an Alert on your indicator.
3.  In the **Notifications** tab, check the "Webhook URL" box and paste the address copied from DepthSight.

### Step 3: Writing the Message (JSON)
In the "Message" field in TradingView, you need to paste a specific JSON code. DepthSight expects to receive the signal direction (`LONG` or `SHORT`) and, optionally, the entry price.

*Example message for a LONG entry:*
```json
{
  "action": "LONG",
  "symbol": "{{ticker}}",
  "price": "{{close}}"
}
```

*   `action`: Must match what you configured in the `TradingView Signal` block (e.g., you want the block to react only to the word "LONG").
*   `{{ticker}}` and `{{close}}`: These are built-in TradingView variables that will automatically insert the correct coin and current price.

---

## 3. Advanced Combination Scenarios

*   **TradingView + Bitcoin State**: Nest the TV Signal in an AND block alongside the `BTC State Filter`. Now, your buy signals for altcoins will be ignored if Bitcoin is in a dump phase.
*   **TradingView + AI Oracle (Market Regime)**: Configure the `Oracle Confidence` in the strategy configuration panel. The bot will execute external signals only when the AI Oracle confirms that the market is currently in a predictable phase, rather than a chaotic flat.
*   **TradingView + Volatility**: Use the `NATR Filter`. The bot will accept the signal from TV only if there is currently enough market volatility for a good move.
*   **Dynamic Stops**: Even if the signal came from the outside, you can use DepthSight's `Stop Loss` block to link your risk to a local order book density rather than a fixed percentage.

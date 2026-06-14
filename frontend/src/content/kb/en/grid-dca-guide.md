# Grid & DCA Strategies: Smart Averaging

Grid trading and DCA (Dollar Cost Averaging) are popular but risky position management methods. The concept is simple: if the price moves against you, the bot buys more of the asset, thereby improving (bringing closer) the average entry price. This allows you to close in profit even with a small price pullback.

In DepthSight, this mechanism is taken to a completely new level thanks to its integration with the visual editor.

---

## 1. Built-in DCA Calculator
Creating a grid "blindly" is a direct path to account liquidation. To avoid this, the platform features a powerful visual **DCA Calculator**.

*   **Where to find it**: Available directly in the strategy editor when adding a DCA/Grid management block.
*   **What it does**: You input the initial order size, grid step, volume multiplier (Martingale), and the number of steps. The calculator instantly plots a chart showing:
    *   How much total margin (money) this grid will consume.
    *   Where your average entry price will be at each step.
    *   What the maximum drawdown will be if all orders are filled.
*   **Why**: This allows you to know exactly before launching the bot whether your deposit can survive a 20-30% market drop.

---

## 2. Smart Grids: Symbiosis with the Visual Editor
The main problem with ordinary bots is "dumb" grids. They buy strictly every 1% or 2% drop, even if the price is free-falling on massive volume.

In DepthSight, you can combine a grid block with **ANY** other blocks in the visual editor. The logic is divided into two parts:
1.  **Initial Entry Conditions**: You can use global filters, the AI Oracle, and complex patterns to open the very first trade in the grid.
2.  **Conditions for Averaging Steps**: You can place ANY block directly *inside* the DCA block. The bot will execute the next grid step only if both the percentage drop and the nested condition are met.

### Practical Examples

**Example A: Averaging by Tape and Orderbook Activity**
Instead of a banal purchase on a dip, you can nest an **AND** logic block containing `L2 Microstructure` and `Tape Condition` inside the DCA block.
*   *Logic*: If the price drops by the set percentage, the bot **will not** immediately buy more. It will wait until there is an imbalance of limit buyers in the order book AND a spike in market buys in the tape (Tape Acceleration).
*   *Result*: The bot won't waste margin trying to catch a "falling knife," but will average the position exactly at the moment a bounce originates.

**Example B: Grid by Orderbook Densities (Dynamic Links)**
Use `Dynamic Links` to tie your grid steps to real money instead of percentages.
*   *Logic*: Link to the `Orderbook Density` block.
*   *Result*: The bot will not place limit orders every 1%, but will hide them exactly behind large clusters of market maker limit orders in the order book.

**Example C: Protecting the Initial Entry with AI Oracle**
You can use the `Oracle Regime` in the filters section to control when the grid is allowed to start.
*   *Logic*: Allow the first purchase only if the Oracle assesses the market as "Flat" (Ranging). If the Oracle detects an "Extreme Trend," the bot will not start building the grid at all, as grids against strong trends almost always lead to liquidation.

---

## 3. Risk Management
Always use the global **Risk Manager** (Max Drawdown settings) when working with grids. If the market moves relentlessly against you, the Risk Manager will forcibly close positions and save your account from a Margin Call, even if the grid algorithm tries to keep buying.

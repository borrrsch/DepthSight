# DepthSight Strategy Editor

The Strategy Editor is a visual constructor using a hierarchical block system to create trading algorithms of any complexity without writing code.

## How the Editor Works
Unlike classic node-based systems with "spaghetti connections," DepthSight uses a **Structural Approach (Hierarchical Drag-and-Drop)**. You build your strategy as a logic tree, making it easy to read and protecting it from logical errors.

### Main Workspaces
1. **Component Palette**: Located on the left. Contains all available blocks divided into categories.
2. **Strategy Canvas**: Central area where you assemble blocks into logic chains.
3. **Config Panel**: Located on the right. Here you configure specific block parameters and general strategy settings (symbol, timeframe, risk).

## Strategy Structure
Any algorithm consists of three main sections:

### 1. Filters
Global conditions that must be met for the strategy to start looking for an entry point. For example:
* "Trade only during the US Session."
* "Trend filter ADX > 25."
* "Volatility NATR above average."

### 2. Entry Conditions
Specific triggers for opening a position. Blocks here are combined using logical operators:
* **AND**: A signal is generated only if ALL nested conditions are true.
* **OR**: A signal is triggered if at least one condition is met.
* **Senior TF Confluence**: Allows checking conditions on a higher timeframe.

### 3. Position Management
Defines the system's behavior after entering a trade:
* Setting **Take Profit** and **Stop Loss**.
* Using **Trailing Stop** to protect profits.
* **Grid/DCA**: Automatic position averaging when price moves against you.
* **Break-Even**: Moving the stop loss to the entry price.

## AI Copilot
An intelligent assistant is integrated into the editor. You can click the **AI Copilot** button and describe your desired strategy in words (e.g., "Create a scalping strategy based on RSI and order book densities"). The AI will automatically assemble the block structure and suggest optimal parameters.

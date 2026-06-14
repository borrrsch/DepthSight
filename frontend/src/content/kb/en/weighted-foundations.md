# Weighted Foundations System

Weighted Foundations is an advanced signal quality assessment system that allows DepthSight to make trading decisions based on a combination of factors rather than a single condition.

## The Core Concept
Each "foundation" block (Orderbook, Tape, Round Numbers, etc.) is assigned a specific "weight" (points) as a percentage. An entry signal is considered valid only when the sum of the weights of all confirmed blocks reaches a specified threshold.

### Example Weight Distribution:
*   **Orderbook Density**: 40%
*   **Tape Acceleration**: 30%
*   **Price Consolidation**: 20%
*   **Round Number**: 10%

**Total: 100%**

## How It Works
1.  The strategy generates a base signal (e.g., based on the RSI indicator).
2.  The system checks all active Foundations.
3.  If only "Density" and "Round Number" are confirmed, the score will be **40 + 10 = 50%**.
4.  If your **Foundation Threshold** is set to **70%**, this entry will be rejected as not reliable enough.

## Why You Need It
*   **Noise Filtering**: A single spike in the tape might be random, but a spike in the tape *together* with order book density is a strong signal.
*   **Flexible Configuration**: You can make a strategy very conservative (90-100% threshold) or more aggressive (40-50% threshold).
*   **Optimization**: The system allows you to accurately determine which factors in your strategy carry the most weight in making profitable decisions.

## Configuration
Weights and the overall threshold are configured in the **Config Panel** of the Strategy Editor under "Foundation Settings." You can use the platform's default weights or define your own for each block.

# Cross-Exchange Funding Rate Carry Trade: BitMEX/Drift SOL

## Summary

We investigated cross-exchange perpetual futures funding rate arbitrage across 5 exchanges (BitMEX, OKX, dYdX, Drift, Hyperliquid) and 5 assets (BTC, ETH, SOL, XRP, BNB) using 12 months of data. The most promising pair identified was **BitMEX vs Drift on SOL**, which we then analysed over ~3 years of historical data (Jan 2023 - Mar 2026).

## Key Finding: Arbitrage Is Not Viable, But Carry Is

The funding rate spread between BitMEX and Drift for SOL is persistent and one-directional. However, the per-period spread (~2 bps per 8h) is far smaller than round-trip transaction costs (~25 bps), meaning classical arbitrage (enter and exit within one funding period) is not profitable.

The grid search backtest across 4 entry thresholds x 4 leverage levels produced **zero trades** because the entry condition (spread > total round-trip cost) was never satisfied.

Instead, the strategy is viable as a **funding rate carry trade**: hold the position (short BitMEX, long Drift) and collect the spread over multiple periods, amortising entry/exit costs over the holding duration.

## Data: BitMEX/Drift SOL Spread (~3 Years)

| Year | Mean Spread (bps/8h) | % Positive | Gross Annual Return (1x) |
|------|---------------------|------------|--------------------------|
| 2023 | 1.1                 | 71%        | 12%                      |
| 2024 | 2.4                 | 79%        | 26%                      |
| 2025 | 2.0                 | 93%        | 21%                      |
| 2026 | 2.5                 | 97%        | 28%                      |

- **Overall**: 81.6% positive, mean 1.82 bps/period
- **Worst single period**: -70.3 bps (Jan 4, 2023)
- **Longest negative streak**: 16 periods (5 days)
- **Max cumulative drawdown**: 364 bps

## Why the Spread Exists

### It's BitMEX, Not Just SOL

Analysis of all exchange-asset pairs revealed that BitMEX has the **highest funding rate for every single asset**: ETH (1.95 bps), XRP (1.98 bps), SOL (1.61 bps), BNB (0.60 bps), BTC (0.44 bps). Every pair with BitMEX on the long-funding side is persistently positive. This is not a SOL-specific or Drift-specific phenomenon — it's a BitMEX-wide structural feature.

### Hypothesis: Inverse Contract Convexity + Ecosystem Hedging

We believe the spread is driven by two mechanical forces, not trader demographics:

1. **Inverse contract convexity (BitMEX side)**: BitMEX's SOL perpetual is BTC-margined (SOL/USD:BTC). When collateral (BTC) and position (SOL) are different assets, the payoff is nonlinear. If SOL rallies but BTC doesn't, the position grows but margin doesn't keep up proportionally. This convexity means longs are structurally more likely to face liquidation pressure, creating a persistent premium for being long — which pushes funding higher. This is mathematical, not behavioural.

2. **Native ecosystem hedging (Drift side)**: SOL is the native gas token of Solana. Validators, stakers, and DeFi farmers have natural long SOL exposure. Drift is where they hedge — shorting SOL perps to reduce exposure. This creates persistent short pressure on Drift, pushing its funding lower or negative (-0.49 bps for SOL). This is tied to SOL's role in the Solana ecosystem, not to any particular group of traders.

The combination — inflated funding on BitMEX from inverse contract mechanics, deflated funding on Drift from ecosystem hedging — creates the widest structural gap specifically on SOL (2.1 bps).

### Why the Spread Persists

Cross-chain capital friction prevents arbitrageurs from closing the gap. Bridging capital between Bitcoin/Ethereum (BitMEX) and Solana (Drift) requires multiple steps, time, and cost. If this were on the same chain or the same exchange, the spread would be arbitraged away quickly.

### How to Validate This Hypothesis

The inverse contract thesis can be tested with a clean comparison:

- **Binance linear SOL vs Binance inverse SOL**: Same exchange, same users, different contract type. If inverse shows higher funding, it confirms the mechanics matter.
- **Binance inverse SOL vs BitMEX inverse SOL**: Same contract type, different exchange. If funding is similar, it confirms structure over venue.

This requires Binance API keys (coin-margined futures endpoint). Bybit offers the same test. Both exchanges offer linear and inverse SOL contracts.

## Why Q1 2023 Was Bad

Two identifiable black swan events caused the only extended negative period:

1. **January 2023 - FTX Aftermath**: SOL was at ~$8, recovering from the FTX/Alameda collapse. BitMEX traders aggressively shorted SOL, flipping the usual long bias. BitMEX funding went to -75 bps on Jan 4.

2. **March 2023 - SVB/USDC Depeg**: Silicon Valley Bank collapsed, USDC depegged to $0.87, and trust in DeFi/stablecoins broke down. Drift (USDC-settled, Solana-based) was hit on both fronts.

Both were structural shocks to the crypto ecosystem, not failures of the spread thesis. Since Q2 2023, the spread has been 77-100% positive every quarter.

## Transaction Costs

Round-trip costs for BitMEX/Drift (taker-taker, $10K notional):
- **Trading fees**: 25 bps (4 trades: open + close on each exchange)
- **Slippage**: ~0 bps at $10K
- **Gas**: ~0 bps (Solana tx negligible)

At maker-maker rates, costs drop to ~2 bps round-trip, which would make single-period arbitrage viable if fills are reliable.

## Expected Returns (Hold Strategy)

| Leverage | Annual Return (net of 1 RT cost) |
|----------|----------------------------------|
| 1x       | ~23%                             |
| 3x       | ~68%                             |
| 5x       | ~114%                            |

These are theoretical ceilings based on historical data. Actual returns depend on holding period, rebalancing frequency, and whether the structural spread persists.

## Risks

1. **Limited data** - The entire thesis rests on ~3 years. The trend is improving, but 2023 shows it can go wrong.

2. **Exchange/counterparty risk** - Capital locked on two exchanges simultaneously. Either could be hacked or freeze withdrawals.

3. **Solana downtime** - If the network goes down, the Drift leg is frozen while BitMEX keeps trading. A large SOL price move during an outage could liquidate one leg.

4. **Liquidation asymmetry** - Each exchange only sees one leg. A sharp SOL move can liquidate the losing side before the winning side can offset it. Manageable at low leverage with adequate margin buffers.

5. **Spread closing permanently** - If cross-chain bridges improve or Drift's user base shifts, the structural edge could disappear.

## Next Steps

### Priority 1: Validate the Inverse Contract Hypothesis
1. Get Binance/Bybit API keys and pull funding rates for both linear and inverse SOL contracts
2. Compare linear vs inverse funding on the same exchange — this is the critical test
3. Compare inverse funding across exchanges (Binance, Bybit, BitMEX) to isolate venue effects

### Priority 2: Quantify the Mechanics
4. Formalise the convexity effect from the inverse contract payoff structure
5. Pull Drift on-chain open interest data to verify the short-bias / hedging thesis
6. Check if the spread correlates with BTC/SOL correlation (inverse contract convexity should matter more when BTC and SOL decorrelate)

### Priority 3: Strategy Viability
7. Stress test against specific SOL events (network outages, token unlocks, liquidation cascades)
8. Paper trade to test execution feasibility (latency, Solana congestion)
9. Test whether maker orders are reliably fillable (would reduce costs from 25 bps to ~2 bps)
10. Check if the same structural spread exists for ETH, BTC on inverse vs linear pairs

## Strategy Classification

This is a **cross-exchange funding rate carry trade** (or relative value carry strategy). It is market neutral (long + short the same asset on different venues), but the return comes from carrying the position over time and collecting the persistent funding rate differential - not from directional price movement or single-period arbitrage.

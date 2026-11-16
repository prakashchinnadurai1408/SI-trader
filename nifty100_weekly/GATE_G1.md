# Gate G1 — Monthly Nifty 100 strategy

Recorded on 16 November 2026 before testing the monthly strategy. Applies to the Section 29 long-only quality, momentum and low-volatility strategy. These are research pass criteria.

## Pass criteria

All three criteria must pass on the same out-of-sample run.

1. **Net return.** Strategy net CAGR must exceed the Nifty 100 Total Return Index CAGR by at least **1.0 percentage point** over identical dates.
2. **Rolling win rate.** The strategy must beat the index in at least **60% of rolling 36-month windows**, sampled monthly. A tie counts as a non-win. Report the number of windows and disclose that adjacent windows overlap.
3. **Maximum drawdown.** Peak-to-trough decline in the strategy's daily marked-to-market portfolio value must be **30% or less**, including position and cash balances.

## Measurement

- Require at least **60 complete out-of-sample months**. A shorter or materially incomplete run is inconclusive. Declare the test dates and data coverage before calculating performance.
- Use a walk-forward process with chronological training and validation. Freeze the strategy rules, calibration process and gate thresholds before the held-out test. Any later changes require a new untouched test period.
- Use the Nifty 100 membership, financial statements, and veto flags available at each historical decision date. Adjust for corporate actions and include dividends. Simulate fills after signals become available and include brokerage, statutory charges, slippage, and applicable modeled taxes. Record cost and tax assumptions before running.
- Benchmark against the [Nifty 100 Total Return Index methodology](https://www.niftyindices.com/resources/index-concepts/total-return-index). The benchmark is an index series. Publish the strategy cost and tax assumptions separately.
- A pass makes the strategy eligible for the six-rebalance paper pilot in the BRD. Live-order approval is a separate gate.

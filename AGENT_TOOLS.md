# Agent tools

## Arena strategy review

The Arena review is the quality gate every new or materially changed
strategy passes before it can be promoted. It is defined in code by
`nifty100_weekly/nifty100_adapter/research/arena.py`; this section is the
specification that module implements.

### What it must do

1. Produce **Weekly** and **Monthly** research rankings and **strategy
   experiments** over the submitted strategies.
2. Give every solver the **same fixed dates**, and the same decision-time
   evidence, costs, capital and risk constraints. Nothing may be tuned per
   solver, and nothing may be chosen after looking at the results.
3. Keep the **final holdout out of strategy selection**. The evaluation
   window decides the ranking; the holdout only measures what the chosen
   strategies did on data that was not used to pick them.
4. Compare **measured holdout performance and risks**, not just returns.
5. **Label unverified data and unmeasured results explicitly.** A strategy
   with no price history, or a parameter with no configured feed, is
   reported as unmeasured/unavailable - never silently scored as zero or
   neutral.

### How to run it

```bash
cd nifty100_weekly
python -B -m unittest discover -s tests -p 'test_strategy_integrations.py' -v
```

A full review report, including the holdout comparison and the labelling of
anything unmeasured, is produced by `ArenaReview.report()` and exported with
`ArenaReview.export_report(path, eval_data, holdout_data)`.

### Authority

The Arena review is **read-only**. Promotion and execution follow the
existing SI-Trader gates: the execution bridge, paper trading and the five
compliance gates. Ranking a strategy first does not place a trade.

### Constraints used

| Constraint | Value |
|---|---|
| Evaluation capital | Rs 25,000 |
| Round-trip cost + tax | 0.38% (STT 0.1% per side, brokerage 0.05%, STCG 20%) |
| Max loss per trade | Rs 500 |
| Max positions | 10 |
| Parameter catalogue | 48 parameters, weights total 100 |
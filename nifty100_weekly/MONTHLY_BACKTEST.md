# Phase 1 monthly backtest

Run from the SI-Trader checkout root in PowerShell.

```powershell
python -m nifty100_weekly.nifty100_adapter.backtest.monthly_backtester --data 'C:\path\to\point-in-time-data' --start 2019-02 --end 2024-01 --out 'C:\path\to\new-report'
```

The dates above illustrate a 60-month range. Declare your actual untouched holdout dates before running. The report directory must be new. It receives `daily_equity.csv` and `report.json`. The JSON contains Gate G1 metrics, monthly data coverage, trade and risk-alert logs, cost assumptions, and the data manifest. See [Gate G1](GATE_G1.md) for the frozen research thresholds.

## Input files

| File | Required columns or keys |
| --- | --- |
| prices.csv | date, isin, open, high, low, close, signal_close, split_ratio, dividend |
| snapshots.csv | date, known_on, isin, symbol, sector, turnover_crore, quality, value, ownership, earnings_revisions, news_sentiment, asm_gsm, pledging_veto, legal_veto, regulatory_veto, auditor_veto |
| tri.csv | date, tri |
| manifest.json | mode, rules_frozen_before_test, sources, short_term_tax, long_term_tax, dividend_tax |

Use YYYY-MM-DD dates. Prices and dividends are INR per share. Provide raw OHLC for valuation and execution, a corporate-action-adjusted total-return close for signals, split ratio 1 on ordinary dates, and dividend 0 on non-dividend dates. On a combined split and distribution date, the dividend input is measured per post-split share. The simulator applies cash dividends on the supplied entitlement date and rejects fractional share actions that need cash-in-lieu data.

Each decision date is the last benchmark trading session of the month before rebalance. Provide exactly 100 eligible-for-membership index records before strategy screens for that date. The date in known_on must be no later than the decision date. Use point-in-time factor scores with higher values representing stronger signals. Veto flags must explicitly be true or false. Include sufficient price warm-up for 252 consecutive prior benchmark sessions, and a TRI calendar that includes the month before and the month after the holdout. A declared research source must document timing, historical index membership, corporate actions, and feed coverage. The program validates the supplied fields and dates; it cannot verify source lineage independently.

Example manifest structure with illustrative tax inputs:

```json
{
  "mode": "research",
  "rules_frozen_before_test": true,
  "sources": {
    "prices": "Provider, dataset version and corporate-action method",
    "snapshots": "Historical membership and as-published factors and vetoes",
    "tri": "Nifty 100 TRI data provider and extract date"
  },
  "short_term_tax": 0.20,
  "long_term_tax": 0.125,
  "dividend_tax": 0.0
}
```

Mode synthetic can verify the runner and always makes Gate G1 inconclusive. Fill in the rates and source records used for the actual run.

## Strategy assumptions

- The portfolio uses the fixed Section 29 scorecard and chronological monthly decisions, with no factor fitting or LLM stock selection. It ranks 6- and 12-month momentum excluding the latest month, 63-session volatility, and the supplied factors. Lookbacks use 21, 126, and 252 trading sessions.
- It targets 12 positions, limits initial allocations to 10% per stock and 30% per sector, and reserves at least 5% cash for new purchases. Gains and market moves can move an existing holding above its cap. The 30% monthly turnover budget counts buys plus sells. Mandatory exits may exceed it and are reported.
- Existing holdings through rank 25 take priority over new additions. The tax-aware hold band protects qualifying winners within 30 days before their first anniversary, subject to the stop, vetoes, and exposure constraints. The simulator uses whole shares and models sales using FIFO. Sale proceeds are made available to simulated buys at the same opening session. The model omits investor-specific exemptions, loss offsets, and settlement delays.
- Weekly checks raise alerts for a 15% trailing stop and a 10% portfolio drawdown. A stopped holding exits on the next monthly rebalance. The exposure overlay targets 18% volatility using the TRI and limits target exposure to 50% after a 10% trailing 21-session TRI drop. This is a market drawdown proxy for the momentum-crash guard.
- Mandatory vetoes use month-end snapshots. There is no intraweek corporate veto feed yet. Calendar scheduling, paper pilot execution, and broker orders are outside this backtester.

## Historical data intake

Download a **Nifty 100 Total Returns Index Values** CSV from the [NSE Indices historical reports](https://www.niftyindices.com/reports/historical-data). Use the total-return series. Include the full warm-up calendar, the declared holdout, and sessions in the following month.

From the checkout root, run:

```powershell
$intake = 'nifty100_weekly.nifty100_adapter.backtest.historical_intake'
python -m $intake fetch --tri 'C:\data\nifty100-tri-export.csv' --start 2018-01-01 --end 2024-02-29 --out 'C:\data\nse-archives'
python -m $intake prepare --archives 'C:\data\nse-archives' --tri 'C:\data\nifty100-tri-export.csv' --adjustments 'C:\data\adjustments.csv' --snapshots 'C:\data\snapshots.csv' --manifest 'C:\data\manifest.json' --out 'C:\data\g1-bundle'
python -m $intake check --data 'C:\data\g1-bundle' --start 2019-02 --end 2024-01
```

The download dates are examples. Allow at least 252 trading sessions before the first month-end decision. Fetch downloads only observed benchmark sessions and reuses valid files on retry. Preparation supports both formats from the [NSE capital-market archives](https://www.nseindia.com/all-reports/). It normalizes OHLC, filters on the historical snapshot ISINs, and combines verified adjustment inputs. It records SHA-256 checksums on the prepared bundle. The backtester also checks those checksums when present.

Supply adjustments.csv with columns date, isin, signal_close, split_ratio, dividend. Include a row for every archived price used, with explicit 1 and 0 values for no split and no dividend. Supply the point-in-time monthly snapshots described above. The public bhavcopy contains raw prices. It does not establish historical membership, factor scores, veto states, or verified corporate-action adjustments. Do not substitute a current constituent list or fill unverified veto fields with false.

The check command returns its diagnostics as JSON. It exits 0 for a ready research bundle and 2 when an input or coverage requirement is unmet. It checks for 60 months, benchmark calendar coverage, 100 dated members per decision, and sufficient consecutive price history without calculating returns. It checks the supplied data contract and declared provenance. It cannot certify the vendor's lineage. Run the backtester only after the check passes.

After a qualifying Gate G1 pass, follow the [six-rebalance paper pilot guide](PAPER_PILOT.md).

## AI strategy challenger

Open **AI strategy builder** in the local dashboard. Configure an Ollama model once in Strategy settings, enter a research objective, generate a proposal, and export monthly-challenger.json. The proposer and reviewer run in separate model calls. This workflow changes factor weights for the challenger only. The baseline and Gate G1 pilot criteria stay frozen.

Declare the holdout dates and strategy comparison before viewing results. Use the exact same verified data bundle, dates, starting capital, and cost assumptions in both runs. The dates below are examples.

```powershell
$runner = 'nifty100_weekly.nifty100_adapter.backtest.monthly_backtester'
python -m $runner --data 'C:\data\g1-bundle' --start 2019-02 --end 2024-01 --out 'C:\data\baseline'
python -m $runner --data 'C:\data\g1-bundle' --start 2019-02 --end 2024-01 --out 'C:\data\challenger' --challenger 'C:\data\monthly-challenger.json'
python -m nifty100_weekly.nifty100_adapter.backtest.compare_strategies --baseline 'C:\data\baseline' --challenger 'C:\data\challenger'
```

The comparison rejects mismatched input fingerprints, equity dates, benchmarks, capital, and costs. It reports total ROI, annualized net return, drawdown, and 36-month head-to-head wins. A 100% relative ROI improvement means the challenger doubled a positive baseline ROI over the same period. With a zero or negative baseline, use the percentage-point difference instead. Synthetic or short datasets are inconclusive. No comparison promotes a challenger into the paper pilot or live execution.

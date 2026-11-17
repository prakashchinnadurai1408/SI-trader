# Connecting the parameter catalogue

Open **Data feeds** and choose **Refresh data feeds** to inspect all 48 parameters, their sources, coverage, refresh cadences, and dated samples.

- P/E compares each positive company P/E to its Nifty 100 industry median when at least three peer observations exist.
- Promoter ownership uses dated, ISIN-matched shareholding filings. It does not provide promoter pledging or a detailed ownership breakdown.
- Corporate actions and dividends show observations by ex-date. They are not a corporate-action adjustment history.
- Company news currently covers recent NSE corporate disclosures only.
- Bulk/block deals are included only when the report date matches the observed NSE close. An empty or undated statement does not prove the absence of trades.

## Add provider data

Set SI_TRADER_CATALOGUE_FEED to the absolute path of a local JSON file in the PowerShell environment that starts SI-Trader. Restart the app and reopen Data feeds. The file is a JSON array up to 2 MB. Use one object per parameter and symbol.

```json
[
  {
    "parameter": "debt_equity_ratio",
    "symbol": "RELIANCE",
    "asOf": "2026-11-16T12:00:00+05:30",
    "source": "https://example.com/replace-with-the-published-filing",
    "value": 0.0
  }
]
```

This example uses placeholder data. Supply an ISO timestamp with an offset, an HTTPS source link, and a scalar value. Use the literal asterisk only for eligible market-wide advisory, dial, or flag observations. Fresh local observations are counted separately from NSE data. The app validates structure and freshness, but a declared URL does not certify the data.

The connected observations are research evidence. They do not change watchlist weights or clear risk vetoes. Prioritize ASM/GSM, promoter pledging, legal cases, and regulatory actions. Then add point-in-time financials, detailed ownership, and adjusted history. Use the [matched backtest workflow](MONTHLY_BACKTEST.md) to measure whether a new input improves returns, drawdown, or consistency.

## Full 48 research

The **Full 48 research** tab checks the data contract before running a separate research screen. It requires all 100 current constituents for each stock-level parameter and a single asterisk record for each market-level input. The check lists coverage, rejected types, and stale records. It calls no model while the bundle is incomplete.

The full screen fills daily momentum, five-session momentum and turnover from NSE. It also uses available verified-format NSE promoter holding values and positive P/E ratios divided by the Nifty 100 industry peer median. Provider observations may fill remaining gaps under the same definitions. Set SI_TRADER_FULL_CATALOGUE_FEED to a local JSON file in the same array format shown above, then restart the server. Refresh rules are per catalogue row. Use the coverage screen to see the value type and scope for each parameter.

- Stock Score factors use comparable values from 0 to 100, higher is stronger. P/E uses a raw positive peer ratio, where lower is stronger. Automatic daily and five-session momentum are ranked using observed returns. Provider values for those momentum inputs should not be mixed with raw returns.
- Explicit booleans are required for status gates. For an ordinary Filter, true passes. For a Veto, true excludes. For a Flag, true marks an observed event. Absence of news or a missing record does not imply false.
- Debt/equity, interest coverage, promoter holding, promoter pledging, and turnover apply their catalogue thresholds. Cost versus edge requires an independently supported net edge after costs in percent. Market-level STT, STCG, and brokerage are declared percentages, including an explicit zero if applicable. The app never derives expected returns from past momentum to fill the net edge field.
- Market dials are scores from 0 to 100, higher means lower market risk. Market inputs are international conditions, government news, political incidents, regulator announcements, historical events, and the three rates. Other rows are stock-specific.

The AI receives a summary of all 48 inputs and chooses positive weights for every Score factor. Fixed code applies filters and vetoes, ranks the surviving names, and displays company flags and market dials. Advisory inputs and flags provide review context. Provider-declared source links and dates are validated for structure and freshness, but their accuracy needs independent verification. This is a research ranking without any order path. Use historical ablation tests on the same declared holdout before claiming any accuracy or ROI improvement.

## Three-agent review

Open **Three-agent review**, choose an Ollama model and research objective in Strategy settings, and optionally enter NSE symbols you already hold. This workflow can run when the strict Full 48 research screen is blocked.

- Maker receives coverage and observed signals across the catalogue and nominates up to six candidates from a short list. Complete scoring data determines the short list. Partial observations remain context.
- Checker considers downside scenarios including drawdown, reversal, liquidity, correlation, costs, valuation, and events. It can exclude a name, reject the shortlist, or flag a holding for exit review.
- Umpire can weight only surviving research ideas and can recommend an exit review only for supplied holdings. Known failed checks cannot be overridden. Missing data alone does not generate an exit signal.

The three stages use separate calls to the configured model. Shared model errors are still possible. Unknown or stale inputs remain visible. Weights are research priorities and have no broker order path. Exit review is a prompt to examine the evidence, not an instruction to sell. Accuracy remains subject to an out-of-sample comparison and Gate G1.

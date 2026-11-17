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

Open **Research & execution → Three-agent review**, choose an Ollama model and research objective in **Settings**, and optionally enter NSE symbols you already hold. This workflow can run when the strict Full 48 research screen is blocked.

- Maker receives coverage and observed signals across the catalogue and nominates up to six candidates from a short list. Complete scoring data determines the short list. Partial observations remain context.
- Checker considers downside scenarios including drawdown, reversal, liquidity, correlation, costs, valuation, and events. It can exclude a name, reject the shortlist, or flag a holding for exit review.
- Umpire can weight only surviving research ideas and can recommend an exit review only for supplied holdings. Known failed checks cannot be overridden. Missing data alone does not generate an exit signal.

The three stages use separate calls to the configured model. Shared model errors are still possible. Unknown or stale inputs remain visible. Weights are research priorities and have no broker order path. Exit review is a prompt to examine the evidence, not an instruction to sell. Accuracy remains subject to an out-of-sample comparison and Gate G1.


## Pull multiple provider feeds

Set `SI_TRADER_SOURCE_MANIFEST` to a JSON file accessible to the dashboard server and restart the app. Configure up to eight named HTTPS endpoints that you control or have permission to access. Each must return the normalized observation array described above. Stock rows must include the current constituent ISIN in an `isin` field. For authenticated endpoints, provide a bearer token via the named environment variable used to start the server.

```json
{
  "Financial statements": {"url": "https://data.example.com/normalized/financials"},
  "Ownership data": {"url": "https://data.example.com/normalized/ownership", "bearerEnv": "SI_OWNERSHIP_TOKEN"}
}
```

These example endpoints are placeholders. Feed adapters or a provider-side export must normalize raw filings, APIs and vendor files into this schema. A public website URL is not a normalized endpoint.

**Full 48 research → Check full catalogue** retrieves configured sources and displays each provider's status, counts, and source links. Existing NSE observations and the legacy full-catalogue file still work. When a parameter needs fallback data, the newest valid observation is used. Equally recent values that disagree, or conflicting fresh risk observations, remain unknown. Stale or future-dated inputs cannot fill required coverage. The model receives the validated evidence in the Full 48 screen and Three-agent review. The monthly builder receives observed coverage and numeric summaries as hypothesis context. Monthly backtests still use their own point-in-time historical bundle.

## 48-Parameter Run Report

On **Weekly** or **Monthly**, open **48-Parameter Run Report** and select **Refresh evidence preview**. The preview works without Ollama. Each parameter shows its role, strategy use, coverage, missing or conflicting observations, latest date, and source links. The provider section includes fetch failures and empty responses.

A weekly paper run evaluates all 48 parameters by their catalogue roles. Score factors with complete coverage get comparable percentile ranks and positive weights, normalized to 100. P/E is ranked lower-is-stronger. Partial score coverage stays out of the rank. Dated filter and veto failures exclude stocks before ranking. The lowest observed market dial can only lower the paper exposure cap; missing dials do not alter the user-set cap. Flags and advisory summaries give the planner context. Observed provider rates are visible alongside the app's separate simulated cost model. The planner receives the coverage of all 48 parameters and a ranked shortlist. The report records the ranking weights and the number of stocks each known filter or veto excluded. Select a stock in the simulated basket to see its linked observations. A missing check stays unknown. The weekly cost/edge control requires an independent net-edge observation. Historical momentum is a ranking input and does not supply an expected return. The monthly factor proposal records all 48 coverage counts. A historical backtest uses its separate dated input bundle.

The report pulls NSE corporate disclosures and actions alongside the existing price, valuation, and ownership inputs. It also checks the [SEBI RSS feed](https://www.sebi.gov.in/rss.html) for dated market-wide announcements. Those headlines can flag an announcement and do not establish stock-level enforcement status. An empty RSS response or unsuccessful fetch leaves the field unobserved. The report records known risk exclusions separately from the completeness of the feed.

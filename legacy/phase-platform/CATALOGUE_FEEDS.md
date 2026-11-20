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

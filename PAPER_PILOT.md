# Six-rebalance paper pilot

The monthly pilot runs separately from the weekly dashboard. It requires the report.json and daily_equity.csv files from a qualifying research-mode Gate G1 run. It recalculates the gate metrics and records both file hashes. The checks validate the supplied reports for consistency and cannot independently certify the source history.

Run from PowerShell in the project parent. Replace the sample file paths, paper capital, dates and reviewer name before running.

```powershell
Set-Location 'C:\Users\Prakash\OneDrive\Documents\Default Project'
$pilot = 'nifty100_weekly.nifty100_adapter.backtest.paper_pilot'
$ledger = 'C:\data\monthly-paper-pilot.sqlite'
python -m $pilot --ledger $ledger init --g1-report 'C:\data\g1-report\report.json' --capital 100000
python -m $pilot --ledger $ledger status
```

## Each rebalance

1. Refresh the research input bundle with current corporate-action-aware prices, TRI and a point-in-time snapshot for the month-end decision. Retain the session history needed for momentum and daily paper marks.
2. After the decision close and before the next session date, create a plan. Inspect its Keep, Add and Remove actions, held quantities, target weights and risk-exit reasons.
3. Use approve before the execution date or skip the rebalance. An approved proposal may also be skipped if the intended execution becomes invalid. Skips are logged and do not count toward the six completed rebalances.
4. Once the execution session has closed and the bundle includes that session, record paper fills using its published open, modeled costs and available paper cash. Only the first session after the approved decision is accepted. Filled quantities can differ from targets because of cash, the opening price, and the turnover cap.
5. Update the bundle and record marks through the latest published close. Weekly price-stop and drawdown alerts are recorded as part of marking. There is no automatic scheduler or intraday veto monitor.

```powershell
python -m $pilot --ledger $ledger plan --data 'C:\data\pilot-bundle' --decision 2026-11-30 --execution 2026-12-01
python -m $pilot --ledger $ledger approve --reviewer 'Trader'
python -m $pilot --ledger $ledger fill --data 'C:\data\pilot-bundle'
python -m $pilot --ledger $ledger mark --data 'C:\data\pilot-bundle' --through 2026-12-04
python -m $pilot --ledger $ledger status
python -m $pilot --ledger $ledger audit
```

Each command commits its state update and audit event together. Status shows progress, the last mark, cash, holdings, and paper and benchmark returns. Once six rebalances are recorded, status flags the pilot for review and blocks further proposals. The pilot never sends broker orders.

## Broker order-ticket review

To review a ticket opened by the trader, crop the screenshot to the order fields and exclude account details, credentials and OTPs. Prepare expected.json independently from the trade plan and the broker's instrument mapping. Enter the intended symbol, exchange, side, product, order_type, quantity and limit_price. Use null for limit_price on a market ticket.

```powershell
python -m nifty100_weekly.nifty100_adapter.order_ticket_review --expected 'C:\data\expected.json' --screenshot 'C:\data\ticket.png' --model 'gemma4:latest'
```

The checker runs locally using Windows OCR, with optional Ollama vision for missing labels. It compares visible fields to the expected order and returns manual_review or blocked. A matching transcription still requires the trader to verify the account and original ticket. The checker does not fill forms, submit or cancel orders, verify an execution, or replace the Gate G1 and paper-pilot requirements. Any broker-enabled execution must have its own supported adapter and order/fill reconciliation.

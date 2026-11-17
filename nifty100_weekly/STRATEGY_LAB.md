# Strategy Lab

Open **Research & execution → Strategy Lab** from the paper dashboard, then select **Refresh NSE snapshot**. The snapshot shows the exchange's source date, market breadth, and industry-group median five-session returns. The Lab links to the Monthly workspace, three-agent review, and the 48-parameter evidence screen.

## Stock diagnostics

In PowerShell, set `$env:SI_TRADER_STRATEGY_BUNDLE` to a prepared [monthly research bundle](MONTHLY_BACKTEST.md), then launch the app in that session. The Lab requires continuous stock and Nifty 100 TRI history and uses the bundle's latest covered session. It reports the observation date beside the NSE snapshot date. A stock diagnostic covers volatility, momentum, RSI, ATR, market beta, and simulated downside and upside percentiles over 5 to 30 sessions. The simulation uses historical volatility with zero log drift. It represents a stress scenario, with no target-return forecast.

## Test the defensive monthly strategy

In **Monthly → Historical backtest**, enter the first and last holdout months and starting capital. **Check data readiness** lists missing files, calendar gaps, and membership coverage issues without calculating returns. **Run monthly comparison** checks readiness before comparing the baseline and defensive variant. Select **Generate monthly proposal** on the same page and select **Include the current AI factor challenger** to assess it on the same holdout. The comparison stays in the browser session. Use the CLI below for saved reports and the baseline evidence files used by the paper pilot.

Run the fixed monthly baseline and the defensive overlay on identical point-in-time data, dates, capital, and costs. See [monthly backtest setup](MONTHLY_BACKTEST.md) for the baseline command. Repeat that command with `--defensive` and a new report directory. Pass that directory as `--challenger` to the existing comparison command. The defensive rule targets 25% equity below the 10-month average of completed Nifty 100 TRI month-end values and 95% otherwise. Order constraints govern how quickly it can reach the target. The comparison adds downside capture in negative benchmark months and time to recover from the worst drawdown. The baseline remains the eligibility path for the paper pilot.

## Product priorities

1. Acquire and validate historical membership, adjusted prices, dated factor values, and veto evidence. Exchange Bhavcopy and the TRI are starting points. Missing or late evidence should remain visible in the 48-parameter workspace. See the [NSE report archive](https://www.nseindia.com/all-reports/) and the [NSE Indices historical reports](https://www.niftyindices.com/reports/historical-data).
2. Test the fixed monthly strategy, the defensive overlay, and one AI weight proposal against Nifty 100 TRI. Use Nifty100 Low Volatility 30 TRI as an additional defensive reference in the research review. Compare net returns, drawdowns, downside capture, recovery, and turnover over a declared holdout. Indian quality-factor research motivates testing a quality tilt. See [IIM Ahmedabad's quality-factor research](https://iima.ac.in/publication/performance-quality-factor-indian-equity-market) and the [Nifty100 Low Volatility 30 index](https://www.niftyindices.com/indices/equity/strategy-indices/nifty-100-low-volatility).
3. Run the existing paper pilot after the fixed baseline passes Gate G1. Use the paper order log to check signal timing, cash and position reconciliation, rejected orders, and execution costs. Any later live execution needs a separately validated broker API and its applicable controls. See the [SEBI retail algo framework implementation standards](https://www.sebi.gov.in/sebi_data/attachdocs/jun-2025/1750158789381.pdf).

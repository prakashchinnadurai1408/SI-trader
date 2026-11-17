# SI-Trader local user journey

Open [SI-Trader](http://127.0.0.1:8765/) on the machine running the app. This journey uses the local paper dashboard.

## Sign in and run a weekly paper strategy

1. On **Sign in**, enter the demo email `trader@example.com` and password `WeeklyDemo123!`. Select **Continue to authenticator code**.
2. Enter the demo code `123456`, then select **Continue to broker setup**.
3. Select **Open paper dashboard**. If you have authorized InvestRight API credentials, **Check API access** verifies the connection. The broker's sign-in link opens InvestRight separately.
4. Open **Strategy settings**. Under **LLM configuration**, select an installed Ollama model. If the list is empty, make sure Ollama is running and select **Check Ollama connection**.
5. Enter a strategy objective and maximum number of positions. For a first test, choose **Paper capital**, use ₹25,000 and a 10% minimum cash buffer, and leave **Simulate fills automatically** checked. **Generate parameters with AI** is optional. Select **Save configuration**.
6. On **Strategy overview**, select **Run AI strategy**. Review the NSE source date, selected stocks and quantities, cash used, and scenario ROI when a basket is available. The ROI field shows a price-move scenario. If no candidate qualifies, read the status message before changing the settings.
7. Open **Execution** and review **Paper fills**. If the run returns an empty basket, the screen shows no simulated fills. Use **Kill switch** to pause further paper runs in the tab and **Reset kill switch** to resume.
8. Open **Holdings & positions** for InvestRight holdings and positions. Use **Refresh broker** to retry a configured read-only connection. Live submission is disabled in this build.

## Inspect evidence and compare monthly strategies

9. Open **Strategy Lab** and select **Refresh NSE snapshot**. Check the source date, constituent coverage, market breadth, and industry performance.
10. Open **Full 48 research** and select **Check full catalogue**. Review missing, stale, and incomplete inputs. **Run full AI screen** becomes available when the required evidence and a configured model are available.
11. Open **AI strategy builder**, enter a monthly research objective, and select **Build research strategy**. Review the weighting proposal and risk flags. Select **Export proposal** to save `monthly-challenger.json`.
12. Return to **Strategy Lab → Monthly strategy comparison**. Enter the first and last unseen holdout months and starting capital. Select **Check data readiness**. If no bundle is configured, prepare the historical inputs using the [monthly backtest guide](MONTHLY_BACKTEST.md), set `SI_TRADER_STRATEGY_BUNDLE` for the app process, and restart it.
13. Once readiness passes, select **Run monthly comparison**. To include the proposal already generated in this session, select **Include the current AI factor challenger** before running. Compare net total return, net CAGR, drawdown, downside capture, and recovery. Review results alongside Nifty 100 TRI and the baseline's Gate G1 status.

## Restart the local app

Run in PowerShell when port 8765 is free.

```powershell
Set-Location 'C:\Users\Prakash\Downloads\SI-trader-deployed'
python -B -m nifty100_weekly.nifty100_adapter.web_app --port 8765
```

## Local verification on 17 November 2026

- Login, incorrect credential and code recovery, navigation, and the paper kill switch worked in Edge.
- The first weekly run timed out in Ollama. The retry used the already-loaded `gemma4:latest` model, a one-stock limit, and the objective “Build a one-stock paper basket, using weekly momentum as the only score.” It returned one simulated fill for four MAXHEALTH shares, which appeared under **Execution**. This records test output only.
- The Strategy Lab loaded 100 of 100 stocks from the 16 November NSE session. Full catalogue readiness showed 3 of 48 parameters complete.
- The monthly AI builder generated a proposal, exported it, and made it selectable in Strategy Lab. The comparison stopped at readiness because the historical research bundle was missing.
- InvestRight checks showed that the API key and access token were missing. The Holdings & positions and Execution screens displayed the broker sections. Broker-side balances, holdings, positions, orders and trades could not be verified.

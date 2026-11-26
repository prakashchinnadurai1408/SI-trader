# SI-Trader local user journey

Open [SI-Trader](http://127.0.0.1:8765/) on the machine running the app. This journey uses the local paper dashboard.

## Sign in and run a weekly paper strategy

1. On **Sign in**, enter the demo email `trader@example.com` and password `WeeklyDemo123!`. Select **Continue to authenticator code**.
2. Enter the demo code `123456`, then select **Continue to broker setup**.
3. Select **Open paper dashboard**. If you have authorized InvestRight API credentials, **Check API access** verifies the connection. The broker's sign-in link opens InvestRight separately.
4. Open **LLM Configuration**. Select a local Ollama model or add a cloud model connection, test it, then select **Save model**. Use **Refresh connections** to reload local models and saved connections.
5. Go back to the dashboard, open **Settings**, and enter a strategy objective and maximum number of positions. For a first test, choose **Paper capital**, use ₹25,000 and a 10% minimum cash buffer, and leave **Simulate fills automatically** checked. Select **Save configuration**. Weekly evaluates the 48-parameter catalogue automatically.
6. On **Weekly**, select **Run weekly strategy**. Review the NSE source date, selected stocks and quantities, cash used, and scenario ROI when a basket is available. The ROI field shows a price-move scenario. If no candidate qualifies, read the status message before changing the settings.
7. Open **Research & execution → Execution** and review **Paper fills**. If the run returns an empty basket, the screen shows no simulated fills. Use **Kill switch** to pause further paper runs in the tab and **Reset kill switch** to resume.
8. Open **Portfolio** for InvestRight holdings and positions. Use **Refresh broker** to retry a configured read-only connection. Live submission is disabled in this build.

## Inspect evidence and compare monthly strategies

9. Open **Research & execution → Strategy Lab** and select **Refresh NSE snapshot**. Check the source date, constituent coverage, market breadth, and industry performance.
10. Open **Research & execution → Full 48 research** and select **Check full catalogue**. Review missing, stale, and incomplete inputs. **Run full AI screen** becomes available when the required evidence and a configured model are available.
11. Open **Monthly**, enter a monthly research objective, and select **Generate monthly proposal**. Review the weighting proposal and risk flags. Select **Export proposal** to save `monthly-challenger.json`.
12. On the same page, find **Historical backtest**. Enter the first and last unseen holdout months and starting capital. Both dates must be in completed historical months; the latest allowed month is shown below the date fields. Select **Check data readiness**. If no bundle is configured, prepare the historical inputs using the [monthly backtest guide](MONTHLY_BACKTEST.md), set `SI_TRADER_STRATEGY_BUNDLE` for the app process, and restart it.
13. Once readiness passes, select **Run monthly comparison**. Select **Include an AI factor challenger** to include the current proposal. If no proposal exists, the comparison checks historical data readiness and then generates one using the saved LLM before running. Compare net total return, net CAGR, drawdown, downside capture, and recovery. Review results alongside Nifty 100 TRI and the baseline's Gate G1 status.

## Strategy workspace: migrated hub, Arena and paper orders

Open **Strategy workspace** from the main navigation. This is a separate, server-owned paper ledger; InvestRight account panels continue to show read-only broker data.

1. Choose existing MA templates or your saved AI model, optionally enter up to five Nifty 100 symbols, and select **Load strategy candidates**. Blank symbols use the five highest-turnover covered stocks passing the current-session liquidity screen. This is a research sample, not a buy recommendation. AI generation uses the existing LLM Configuration connection, can consume provider quota, and fails explicitly rather than silently substituting templates.
2. Enter ordered evaluation and subsequent holdout dates and select **Run Arena review**. With no configured historical bundle, every candidate remains unmeasured. With a research bundle, the server slices evaluation data before ranking. Holdout data is loaded only when its comparison checkbox is selected; it does not select the finalists. The existing backtester uses price-derived weights, not all 48 fundamental/news factors or a calibrated return forecast.
3. Choose a candidate and paper capital, per-trade risk and cash buffer. Select **Build risk-sized paper plan** to call the migrated execution bridge and BudgetManager. Inspect share counts, reference entry, stop, target scenario and blocking decisions. Numeric model exit percentages must satisfy risk checks; free-text exits cannot become orders.
4. Select **Simulate approved paper plan** to call the paper execution pipeline. It has no broker adapter and the API rejects live mode. Quotes are NSE reference closes; no actual market order is placed and no MA trigger is claimed. Plans expire after ten minutes and execute at most once. Buy-side modeled fees reduce paper cash. Five-position and capital-buffer checks apply.
5. Inspect simulated positions/fills and recent audit report IDs on the same screen. **Halt paper execution** invalidates a pending plan and blocks new workspace plans/fills and weekly paper generation. Resume explicitly. Halting does not cancel broker orders or liquidate positions. Paper fills, cash and halt state persist in `SI_TRADER_RESEARCH_STORE/workspace` (default `~/.si-trader/research/workspace`); plans and loaded candidates reset on process restart. The starting capital cannot change once this ledger has fills.

Audit JSON files are stored privately below that workspace's `reports` directory. They label paper mode and preserve research/plan/execution records for later inspection. A missing dataset or an unmeasured review never establishes profitability or readiness for live trading.

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


## Add and manage cloud models

In **LLM Configuration → Add model connection**, choose Claude, OpenAI, Gemini, Grok, DeepSeek, NVIDIA, OpenRouter, Qwen, Kimi or Custom OpenAI-compatible. Enter a connection name, the exact model ID enabled on your provider account, its API base URL and API key. The provider selector fills the default URL. Adjust it for the account region or service you use.

Select **Load available models** to retrieve model IDs from the provider, then choose or enter one in **Model ID** and select **Save connection**. In default local Windows mode, keys use Windows Data Protection and are stored in `~/.si-trader/llm.sqlite`, outside the repository. When `SI_TRADER_ENCRYPTION_KEY` is configured, new keys use portable authenticated encryption in the server's private model directory. Existing Windows entries remain readable on their original Windows account; re-enter those keys when moving to Linux. See the [hosted deployment guide](../deploy/README.md) for storage and backup requirements. The browser receives the connection name, provider, model and key status. Select **Test** on the saved row to send a short prompt, then **Save model** to select it for Weekly, Monthly and the research agents. API tests and cloud research runs can consume provider quota.

Use **Edit** to change the name or model, or to replace a key. Leave the password field blank to retain a saved key for the same provider and endpoint. **Delete key** removes the local saved key and clears that connection as the active model in the current browser. **Delete connection** removes the profile. Provider-side revocation is available in the provider's own account console.

Ollama continues to use the installed local models without a cloud key. Model availability and structured JSON support depend on the chosen model and account. The app validates structured strategy output before accepting it. Cloud connections currently support text research. Order-ticket screenshot transcription uses a local vision model.

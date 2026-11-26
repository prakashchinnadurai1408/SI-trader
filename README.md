# SI-Trader

A local research and paper-trading workspace for Nifty 100. It includes an NSE watchlist, a 48-parameter feed coverage screen, Ollama strategy research, and a monthly backtest and paper pilot.

**Strategy workspace** connects the migrated strategy hub, Arena review, risk-sized plan preview and paper execution pipeline. It supports existing MA templates or the saved AI model, shows evidence gaps explicitly, and persists simulated fills and audit reports. No live broker execution is exposed. See the [workspace journey](nifty100_weekly/USER_JOURNEY.md#strategy-workspace-migrated-hub-arena-and-paper-orders).

## Repository and source layout

The maintained repository is [prakashchinnadurai1408/SI-trader](https://github.com/prakashchinnadurai1408/SI-trader), on **main**. Both trading source histories are consolidated here.

- `nifty100_weekly/` contains the current application launched by `npm run start`.
- `legacy/phase-platform/` preserves the earlier phase-platform source from `master` for review and selective migration. It is not imported by the current application. See its [integration status](legacy/phase-platform/README.md).

The former `si-trader-app` and `master` branches are retained for compatibility and history. Start new development from `main`.

## Run locally

Use Python 3.12 or newer and run from the checkout root. The npm command also requires Node.js.

```powershell
python -m pip install -r requirements.txt
npm run start
```

To launch directly with Python, run `python -X utf8 -m nifty100_weekly.nifty100_adapter.web_app`.

Cloud model requests allow 600 seconds (10 minutes) by default. Set `SI_TRADER_LLM_TIMEOUT_SECONDS` to an integer from 30 to 1800 before starting the server to change that limit. Weekly strategy, monthly builder, full-catalogue and committee runs use background jobs with short authenticated polling requests and progress updates, so the browser does not hold a long inference connection open. Two research jobs can run at once; duplicate request IDs reuse the same job. Jobs are kept in memory for up to one hour after completion and are lost on server restart. Feed collection already runs independent source requests concurrently. The UI distinguishes parameters checked from parameters with complete evidence; a longer timeout does not create missing observations. Provider timeouts return HTTP 504 with recovery guidance; connectivity failures return HTTP 502. Requests are not automatically retried, and a failed weekly model call produces no new basket or paper fills. NVIDIA GLM-5.3 connections reserve output tokens for both reasoning and the final answer, following the [NVIDIA model API documentation](https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-flash).

Open http://127.0.0.1:8765. The local sign-in screen shows the demo credentials. Open **LLM Configuration** to add, test, and select local Ollama models or cloud connections for AI research. See the [model setup guide](nifty100_weekly/USER_JOURNEY.md#add-and-manage-cloud-models) for providers and API key management. **Data feeds** and its **Refresh data feeds** action work without a model.

By default the service binds to loopback and uses a demo sign-in. Keep that mode local. For a private hosted deployment, use the separate authenticated mode and reverse-proxy setup in the [deployment guide](deploy/README.md). InvestRight account views require INVESTRIGHT_API_KEY and INVESTRIGHT_ACCESS_TOKEN in the server environment. They are read-only. Keep account credentials and local evidence files outside Git.

- [Catalogue feed setup](nifty100_weekly/CATALOGUE_FEEDS.md)
- [Monthly backtesting and strategy comparison](nifty100_weekly/MONTHLY_BACKTEST.md)
- [Gate G1](nifty100_weekly/GATE_G1.md)
- [Six-rebalance paper pilot and screenshot review](nifty100_weekly/PAPER_PILOT.md)
- [Agent tools and filing review workflow](nifty100_weekly/AGENT_TOOLS.md)
- [CI, hosted authentication, Docker and Stormkit deployment](deploy/README.md)

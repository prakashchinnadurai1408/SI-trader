# SI-Trader

A local research and paper-trading workspace for Nifty 100. It includes an NSE watchlist, a 48-parameter feed coverage screen, Ollama strategy research, and a monthly backtest and paper pilot.

## Run locally

Use Python 3.12 or newer and run from the checkout root. The npm command also requires Node.js.

```powershell
python -m pip install -r requirements.txt
npm run start
```

To launch directly with Python, run `python -X utf8 -m nifty100_weekly.nifty100_adapter.web_app`.

Open http://127.0.0.1:8765. The local sign-in screen shows the demo credentials. Choose an installed Ollama model in **Strategy settings** to generate AI research. **Data feeds** and its **Refresh data feeds** action work without a model.

The service binds to loopback. The browser sign-in is a demo. Do not expose this deployment to the public internet. InvestRight account views require INVESTRIGHT_API_KEY and INVESTRIGHT_ACCESS_TOKEN in the server environment. They are read-only. Keep account credentials and local evidence files outside Git.

- [Catalogue feed setup](nifty100_weekly/CATALOGUE_FEEDS.md)
- [Monthly backtesting and strategy comparison](nifty100_weekly/MONTHLY_BACKTEST.md)
- [Gate G1](nifty100_weekly/GATE_G1.md)
- [Six-rebalance paper pilot and screenshot review](nifty100_weekly/PAPER_PILOT.md)
- [Agent tools and filing review workflow](nifty100_weekly/AGENT_TOOLS.md)

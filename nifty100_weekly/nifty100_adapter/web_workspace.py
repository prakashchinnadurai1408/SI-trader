"""Server-owned research -> Arena -> risk plan -> paper simulation workflow.

No broker adapter is accepted or connected here. Client input never supplies
prices, weights, fills, or executable order quantities.
"""
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
from threading import RLock
import time
from uuid import uuid4

from .data.nse_market import load_nifty100, MARKET_TIME
from .config.indian_cost_model import get_cost_model
from .observability.report_writer import ReportWriter
from .strategy.universal_hub import UniversalStrategyHub, HubConfig
from .strategy.execution_bridge import StrategyExecutionBridge
from .risk.execution_pipeline import OrderExecutionPipeline
from .risk.budget_manager import BudgetManager, BudgetRules
from .research.arena import ArenaConstraints
from .strategy.llm_client import LLMClient


class WorkspaceModel(LLMClient):
    """Reuse the app's saved provider/local model, without copying credentials."""
    def __init__(self, model, evidence):
        super().__init__(provider="ollama", model=model)
        self.completed = False
        self.evidence = evidence

    def has_credentials(self):
        return True

    def complete(self, system, prompt, **kwargs):
        from .ai_strategy import ollama
        response = ollama("/api/chat", {"model": self.model, "stream": False, "think": False,
            "options": {"temperature": .2, "num_predict": 1800},
            "messages": [{"role": "system", "content": system + " Use long-only cash equities. Provide numeric stop_loss_pct and target_pct percentages; target must be at least twice stop. Do not claim guaranteed returns. Available evidence is limited to the supplied price snapshot; treat other factors as unknown."}, {"role": "user", "content": prompt + "\nObserved evidence: " + json.dumps(self.evidence, allow_nan=False)}]})
        return response.get("message", {}).get("content", "")

    def generate_strategy_ideas(self, *args, **kwargs):
        ideas = super().generate_strategy_ideas(*args, **kwargs)
        self.completed = bool(ideas)
        return ideas


def amount(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return value


class WebWorkspace:
    def __init__(self):
        self.lock = RLock()
        self.hub = None
        self.plan = None
        self.review = None
        self.market = None
        self.prices = {}
        self.ledger = None

    def _ledger(self):
        if self.ledger is None:
            self.root = Path(os.environ.get("SI_TRADER_RESEARCH_STORE", str(Path.home() / ".si-trader" / "research"))) / "workspace"
            self.root.mkdir(parents=True, exist_ok=True)
            self.writer = ReportWriter(str(self.root / "reports"))
            path = self.root / "paper.json"
            self.ledger = json.loads(path.read_text()) if path.exists() else {"halted": False, "cash": None, "initialCapital": None, "fills": [], "holdings": {}}
        return self.ledger

    @property
    def halted(self):
        with self.lock:
            return self._ledger()["halted"]

    def _save(self):
        temporary = self.root / (uuid4().hex + ".tmp")
        temporary.write_text(json.dumps(self.ledger, allow_nan=False), encoding="utf-8")
        temporary.replace(self.root / "paper.json")

    def _record(self, kind, data):
        path = self.writer.emit(kind, {"inputs": {"mode": "PAPER", "source": self.market}, "metrics": data,
                                        "constraints": data.get("constraints", {k:data[k] for k in ("capital","risk","buffer") if k in data}),
                                        "labels": {"liveExecution": False, "forecast": False}})
        return Path(path).stem

    def status(self):
        ledger = self._ledger()
        recent = sorted([r for kind in ("candidates", "arena", "plan", "paper")
                         for r in self.writer.list_reports(kind=kind, limit=12)], key=lambda r:r["started_at"])[-12:]
        return {"mode": "PAPER", "candidates": [asdict(c) for c in self.hub.strategy_candidates] if self.hub else [],
                "market": self.market, "review": self.review, "plan": self.plan,
                "ledger": ledger, "reports": recent, "liveEnabled": False}

    def _load(self, payload):
        frame, market = load_nifty100()
        available = frame.loc[frame.daily_turnover_crore.ge(25) & frame.close.gt(0)].copy()
        text = payload.get("symbols", "")
        if not isinstance(text, str) or len(text) > 200:
            raise ValueError("Enter at most five NSE symbols.")
        symbols = list(dict.fromkeys(s.strip().upper() for s in text.split(",") if s.strip()))
        if not symbols:
            symbols = available.sort_values("daily_turnover_crore", ascending=False).head(5).symbol.tolist()
        if not symbols or len(symbols) > 5 or not set(symbols).issubset(set(available.symbol)):
            raise ValueError("Choose up to five covered Nifty 100 stocks passing the INR 25 crore session-turnover screen.")
        hub = UniversalStrategyHub(HubConfig(enable_vectorbt=False, enable_backtrader=False, enable_ai_strategy=False,
            enable_options=False, enable_pkscreener=False, enable_algo_india=False, enable_portfolio_optimizer=False))
        source = payload.get("source", "ma")
        if source == "ma":
            candidates = hub.ingest_ma_crossovers()
        elif source == "ai":
            from .ai_strategy import installed_models
            from .strategy.ai_strategy_generator import AIStrategyGenerator
            model = payload.get("model")
            if not isinstance(model, str) or model not in installed_models():
                raise ValueError("Select and save an available model in LLM Configuration first.")
            evidence = {"market": market, "stocks": [{"symbol": r.symbol, "close": float(r.close)} for r in available.itertuples() if r.symbol in symbols]}
            client = WorkspaceModel(model, evidence)
            hub.ai_generator = AIStrategyGenerator(llm_provider="ollama")
            hub.ai_generator._llm_client = client
            candidates = hub.ingest_ai_strategies(market_condition="unverified", time_horizon="weekly", risk_tolerance="moderate", num_ideas=3)
            if not client.completed or not candidates:
                raise ValueError("The model did not return valid strategy ideas. No template fallback was accepted; retry or select another model.")
        else:
            raise ValueError("Choose MA templates or the configured AI model.")
        if not candidates or len({c.name for c in candidates}) != len(candidates) or any(c.weight_total != 100 for c in candidates):
            raise ValueError("Candidates must have unique names and valid weights totalling 100.")
        for candidate in candidates:
            candidate.selected_stocks = symbols
        self.hub, self.market = hub, market
        self.prices = {row.symbol: float(row.close) for row in available.itertuples() if row.symbol in symbols}
        self.plan = self.review = None
        self._record("candidates", {"symbols": symbols, "source": source, "model": payload.get("model") if source == "ai" else None,
                                    "candidates": [asdict(c) for c in candidates]})

    def _arena(self, payload):
        if not self.hub:
            raise ValueError("Load candidates before running Arena.")
        names = ("evalStart", "evalEnd", "holdoutStart", "holdoutEnd")
        try:
            dates = [date.fromisoformat(payload[key]) for key in names]
        except (ValueError, TypeError, KeyError):
            raise ValueError("Enter four valid evaluation and holdout dates.") from None
        if not dates[0] < dates[1] < dates[2] < dates[3] < datetime.now(MARKET_TIME).date():
            raise ValueError("Use ordered, non-overlapping historical evaluation and holdout periods ending before today.")
        capital = amount(payload.get("capital", 25000), "Paper capital", 1000, 1_000_000_000)
        risk = amount(payload.get("risk", 500), "Maximum loss per trade", 1, capital*.05)
        constraints = ArenaConstraints(*(str(d) for d in dates), capital=capital,
            max_loss_per_trade=risk, max_positions=5, cost_pct=get_cost_model().roundtrip_cost_pct)
        evaluation, holdout = None, None
        issues = []
        issues.append("The stock subset and candidate proposals are formed now. Historical results on that retrospective selection can have selection/survivorship bias; they are not prospective holdout proof.")
        path = os.environ.get("SI_TRADER_STRATEGY_BUNDLE")
        if path:
            from .backtest.monthly_inputs import load_inputs
            manifest, prices, snapshots, tri = load_inputs(Path(path))
            if manifest["mode"] != "research":
                raise ValueError("Arena requires a declared research bundle; synthetic data is ineligible.")
            mapping = snapshots.reset_index()
            mapping = mapping.loc[mapping.date.le(str(dates[0]))]
            if mapping.empty:
                raise ValueError("The bundle has no membership snapshot at or before the evaluation start.")
            mapping = mapping.loc[mapping.date.eq(mapping.date.max())]
            history = {}
            for symbol in self.prices:
                matches = mapping.loc[mapping.symbol.eq(symbol), "isin"].unique()
                if len(matches) != 1 or matches[0] not in prices.index.get_level_values("isin"):
                    raise ValueError(f"{symbol} has no unique decision-time membership mapping.")
                bars = prices.xs(matches[0], level="isin").copy()
                # Use split/dividend-adjusted signal prices consistently for research.
                ratio = bars.signal_close / bars.close
                for column in ("open", "high", "low"):
                    bars[column] = bars[column] * ratio
                bars["close"] = bars.signal_close
                history[symbol] = bars
            def window(start, end):
                result = {}
                for symbol, bars in history.items():
                    selected = bars.loc[str(start):str(end)]
                    if len(selected) < 30:
                        raise ValueError(f"{symbol} needs at least 30 bars in each requested window.")
                    result[symbol] = selected.reset_index().to_dict("records")
                return result
            evaluation = window(dates[0], dates[1])
            if payload.get("compareHoldout") is True:
                holdout = window(dates[2], dates[3])
        else:
            issues.append("Historical research bundle not configured; no performance or ranking edge has been measured.")
        report = self.hub.arena_review(price_data=evaluation, holdout_data=holdout, constraints=constraints)
        for comparison in (report.get("holdout") or {}).get("comparisons", []):
            # The migrated module compares percentage drawdown with INR risk;
            # that boolean does not establish stop-risk compliance.
            comparison.get("risks", {}).pop("risk_at_stop_ok", None)
        report["issues"] = issues
        report["scope"] = "Existing weight-based research engine; price-derived inputs only. Not a calibrated forecast or full 48-factor validation."
        self.review = report
        self.plan = None
        report["reportId"] = self._record("arena", report)

    def _plan(self, payload):
        if not self.hub or not self.review:
            raise ValueError("Load candidates and run an Arena review first.")
        if self.halted:
            raise ValueError("Paper execution is halted. Resume it before planning.")
        candidate = next((c for c in self.hub.strategy_candidates if c.name == payload.get("candidate")), None)
        if candidate is None:
            raise ValueError("Select an available strategy candidate.")
        # Ambiguous/free-text model exits cannot silently become approved orders.
        for key in ("stop_loss_pct", "target_pct"):
            amount(candidate.exit_rules.get(key), "Candidate " + key, 1, 50)
        if candidate.exit_rules["target_pct"] < 2*candidate.exit_rules["stop_loss_pct"]:
            raise ValueError("Candidate target must be at least twice its stop percentage for paper sizing.")
        capital = amount(payload.get("capital"), "Paper capital", 1000, 1_000_000_000)
        risk = amount(payload.get("risk"), "Maximum loss per trade", 1, capital * .05)
        buffer = amount(payload.get("buffer"), "Cash buffer", 10, 90)
        if capital != self.review["constraints"]["capital"] or risk != self.review["constraints"]["max_loss_per_trade"]:
            raise ValueError("Capital or risk changed since the Arena review. Run Arena again with those settings.")
        ledger = self._ledger()
        if ledger["initialCapital"] is not None and capital != ledger["initialCapital"]:
            raise ValueError("This paper ledger already has a starting capital. Use its original capital.")
        cash = ledger["cash"] if ledger["cash"] is not None else capital
        if len(ledger["holdings"]) >= 5:
            raise ValueError("The paper portfolio already holds its five-position limit.")
        frame, market = load_nifty100()
        prices = {r.symbol: float(r.close) for r in frame.itertuples() if r.symbol in self.prices and math.isfinite(r.close) and r.close > 0}
        self.market = market
        selected = replace(candidate, selected_stocks=[s for s in candidate.selected_stocks if s not in ledger["holdings"]][:5-len(ledger["holdings"])])
        rules = BudgetRules(pilot_capital=capital, max_loss_per_trade=risk, cash_buffer_pct=buffer/100,
                            max_order_size=capital*.10, max_positions=5)
        pipeline = OrderExecutionPipeline(budget_manager=BudgetManager(rules), trading_mode="PAPER")
        plan = StrategyExecutionBridge(pipeline, top_n=5).build_plan([selected], prices, cash).as_dict()
        plan.update(id=uuid4().hex, capital=capital, risk=risk, buffer=buffer, createdEpoch=time.time(), consumed=False,
                    note="Paper sizing exercise at NSE reference closes, not a confirmed MA entry signal. No predicted ROI.")
        if not any(o["approved"] and o["shares"] > 0 for o in plan["orders"]):
            plan["tradable"] = False
        self.plan = plan
        plan["reportId"] = self._record("plan", plan)

    def _paper(self, payload):
        ledger = self._ledger()
        plan = self.plan
        if self.halted or not plan or plan["consumed"] or payload.get("planId") != plan["id"] or time.time()-plan["createdEpoch"] > 600:
            raise ValueError("Paper plan is missing, expired, consumed, or halted. Build a new plan.")
        if not plan["tradable"]:
            raise ValueError("No orders passed the risk checks.")
        # Consume first; retries must never execute the same plan twice.
        plan["consumed"] = True
        if ledger["initialCapital"] is None:
            ledger["initialCapital"], ledger["cash"] = plan["capital"], plan["capital"]
        results = []
        for order in plan["orders"]:
            if not order["approved"] or not order["shares"] or order["symbol"] in ledger["holdings"]:
                continue
            rules = BudgetRules(pilot_capital=plan["capital"], max_loss_per_trade=plan["risk"], cash_buffer_pct=plan["buffer"]/100,
                                max_order_size=order["shares"]*order["entry_price"], max_positions=5)
            if len(ledger["holdings"]) >= 5:
                break
            pipeline = OrderExecutionPipeline(budget_manager=BudgetManager(rules), trading_mode="PAPER", broker_adapter=None)
            result = pipeline.execute_order(symbol=order["symbol"], entry_price=order["entry_price"],
                stop_loss=order["stop_loss"], target=order["target"], current_cash=ledger["cash"]).to_dict()
            if result["order_placed"]:
                fees = get_cost_model().calculate_buy_costs(result["entry_price"], result["shares"])["total"]
                debit = result["position_value"] + fees
                if result["shares"] > order["shares"] or ledger["cash"]-debit < plan["capital"]*plan["buffer"]/100:
                    raise ValueError("Paper debit exceeded the approved quantity or cash reserve.")
                ledger["cash"] -= debit
                result["status"] = "SIMULATED"
                result["cashDebit"] = debit
                ledger["holdings"][order["symbol"]] = result
                ledger["fills"].append(result)
                self._save()
            results.append(result)
        self._record("paper", {"planId": plan["id"], "results": results, "cash": ledger["cash"]})

    def dispatch(self, payload):
        if payload.get("mode", "PAPER") != "PAPER":
            raise ValueError("Only PAPER simulation is enabled in this workspace.")
        with self.lock:
            self._ledger()
            action = payload.get("action", "status")
            if action == "load": self._load(payload)
            elif action == "arena": self._arena(payload)
            elif action == "plan": self._plan(payload)
            elif action == "paper": self._paper(payload)
            elif action in ("halt", "resume"):
                self.ledger["halted"] = action == "halt"
                self.plan = None
                self._save()
            elif action != "status": raise ValueError("Unknown workspace action.")
            return self.status()

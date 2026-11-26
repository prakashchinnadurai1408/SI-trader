import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import pandas as pd

from nifty100_weekly.nifty100_adapter.web_workspace import WebWorkspace

DATES = dict(evalStart="2023-01-01", evalEnd="2024-12-31", holdoutStart="2025-01-01", holdoutEnd="2025-12-31")


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = patch.dict(os.environ, {"SI_TRADER_RESEARCH_STORE": self.folder.name, "SI_TRADER_STRATEGY_BUNDLE": ""})
        self.env.start(); self.addCleanup(self.env.stop)
        self.frame = pd.DataFrame([dict(symbol="TEST", close=100., daily_turnover_crore=100.)])
        self.feed = patch("nifty100_weekly.nifty100_adapter.web_workspace.load_nifty100", return_value=(self.frame, {"source": "Test fixture", "asOf": "2026-11-25"}))
        self.feed.start(); self.addCleanup(self.feed.stop)
        self.service = WebWorkspace()

    def prepare(self):
        result = self.service.dispatch({"action": "load"})
        self.assertEqual(len(result["candidates"]), 4)
        self.assertTrue(all(c["weight_total"] == 100 for c in result["candidates"]))
        result = self.service.dispatch({"action": "arena", **DATES})
        self.assertTrue(all(r["label"] == "unmeasured" for r in result["review"]["ranking"]))
        return self.service.dispatch({"action": "plan", "candidate": result["candidates"][0]["name"], "capital": 25000, "risk": 500, "buffer": 10})

    def test_full_workflow_uses_real_modules_and_persists_paper_ledger(self):
        result = self.prepare()
        order = result["plan"]["orders"][0]
        self.assertGreater(order["shares"], 0)
        self.assertLessEqual(order["risk_at_stop"], 500)
        result = self.service.dispatch({"action": "paper", "planId": result["plan"]["id"], "orders": [{"shares": 999999}]})
        fill = result["ledger"]["fills"][0]
        self.assertEqual(fill["status"], "SIMULATED")
        self.assertEqual(fill["shares"], order["shares"])
        self.assertTrue(fill["order_id"].startswith("PAPER-"))
        self.assertLess(result["ledger"]["cash"], 25000-order["position_value"])
        self.assertGreaterEqual(result["ledger"]["cash"], 2500)
        self.assertEqual(WebWorkspace().dispatch({})["ledger"], result["ledger"])
        self.assertGreaterEqual(len(result["reports"]), 4)
        for file in Path(self.folder.name).rglob("*.json"):
            json.loads(file.read_text())

    def test_ai_uses_saved_model_and_refuses_silent_template_fallback(self):
        idea = {"name": "Fixture AI", "strategy_type": "momentum", "description": "Fixture", "exit_rules": {"stop_loss_pct": 5, "target_pct": 10}}
        with patch("nifty100_weekly.nifty100_adapter.ai_strategy.installed_models", return_value=["fixture"]), patch("nifty100_weekly.nifty100_adapter.ai_strategy.ollama", return_value={"message": {"content": json.dumps({"ideas": [idea]})}}) as model:
            result = self.service.dispatch({"action": "load", "source": "ai", "model": "fixture"})
            self.assertEqual(result["candidates"][0]["source"], "ai_llm")
            self.assertEqual(model.call_args.args[1]["model"], "fixture")
            self.assertIn("Observed evidence", model.call_args.args[1]["messages"][1]["content"])
        with patch("nifty100_weekly.nifty100_adapter.ai_strategy.installed_models", return_value=["fixture"]), patch("nifty100_weekly.nifty100_adapter.ai_strategy.ollama", side_effect=ValueError("Fixture failure")):
            with self.assertRaisesRegex(ValueError, "No template fallback"):
                self.service.dispatch({"action": "load", "source": "ai", "model": "fixture"})
        self.assertEqual(self.service.status()["candidates"][0]["name"], "Fixture AI")

    def test_repeated_plan_cannot_fill_twice(self):
        result = self.prepare()
        payload = {"action": "paper", "planId": result["plan"]["id"]}
        self.service.dispatch(payload)
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.service.dispatch(payload)
        self.assertEqual(len(self.service.status()["ledger"]["fills"]), 1)

    def test_expired_and_halted_plan_fail_and_halt_persists(self):
        result = self.prepare()
        self.service.plan["createdEpoch"] = time.time()-601
        with self.assertRaisesRegex(ValueError, "expired"):
            self.service.dispatch({"action": "paper", "planId": result["plan"]["id"]})
        self.service.dispatch({"action": "halt"})
        self.assertTrue(WebWorkspace().halted)
        with self.assertRaisesRegex(ValueError, "halted"):
            self.service.dispatch({"action": "plan"})
        self.service.dispatch({"action": "resume"})
        self.assertFalse(self.service.halted)

    def test_live_requests_and_unknown_candidates_fail(self):
        with self.assertRaisesRegex(ValueError, "Only PAPER"):
            self.service.dispatch({"action": "paper", "mode": "REAL_MONEY"})
        self.prepare()
        with self.assertRaisesRegex(ValueError, "available strategy"):
            self.service.dispatch({"action": "plan", "candidate": "fake"})

    def test_period_overlap_and_invalid_dates_are_rejected(self):
        self.service.dispatch({"action": "load"})
        for changes in ({"evalEnd": "2025-06-01"}, {"holdoutEnd": "2099-01-01"}, {"evalStart": "bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.dispatch({"action": "arena", **DATES, **changes})

    def test_symbols_and_nonfinite_budget_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Nifty 100"):
            self.service.dispatch({"action": "load", "symbols": "NOT_IN_UNIVERSE"})
        result = self.prepare()
        for capital in (0, float("nan"), True):
            with self.subTest(capital=capital), self.assertRaises(ValueError):
                self.service.dispatch({"action": "plan", "candidate": result["candidates"][0]["name"], "capital": capital, "risk": 500, "buffer": 10})

    def test_historical_windows_are_filtered_before_arena_receives_them(self):
        self.service.dispatch({"action": "load"})
        dates = pd.bdate_range("2022-01-01", "2026-01-01")
        prices = pd.DataFrame({"date": dates, "isin": "FIXTURE", "open": 100., "high": 101., "low": 99., "close": 100., "signal_close": 100., "volume": 1000000}).set_index(["date", "isin"])
        snapshots = pd.DataFrame([{"date": pd.Timestamp("2022-12-30"), "isin": "FIXTURE", "symbol": "TEST"}]).set_index(["date", "isin"])
        fixture = {"ranking": [], "unlabelled_results": [], "constraints": {}, "holdout": None}
        with patch.dict(os.environ, {"SI_TRADER_STRATEGY_BUNDLE": self.folder.name}), patch("nifty100_weekly.nifty100_adapter.backtest.monthly_inputs.load_inputs", return_value=({"mode": "research"}, prices, snapshots, None)), patch.object(self.service.hub, "arena_review", return_value=fixture) as review:
            self.service.dispatch({"action": "arena", **DATES})
            evaluation = review.call_args.kwargs["price_data"]["TEST"]
            self.assertTrue(all(pd.Timestamp(DATES["evalStart"]) <= r["date"] <= pd.Timestamp(DATES["evalEnd"]) for r in evaluation))
            self.assertIsNone(review.call_args.kwargs["holdout_data"])


if __name__ == "__main__":
    unittest.main()

"""Exercise the shipped weekly API with actual catalogue/ranking/sizing code."""
from contextlib import ExitStack
import http.client
import json
import os
import tempfile
from threading import Thread, Event
import time
import unittest
from unittest.mock import patch

import pandas as pd

from nifty100_weekly.nifty100_adapter.ai_parameters import PARAMETERS, LIVE_COLUMNS
from nifty100_weekly.nifty100_adapter.deployment import Runtime
from nifty100_weekly.nifty100_adapter.web_app import create_server
from nifty100_weekly.nifty100_adapter.llm_connections import ProviderTimeout, ProviderUnavailable


class WeeklyAPI(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.dict(os.environ, {"SI_TRADER_RESEARCH_STORE": folder,
            "SI_TRADER_FULL_CATALOGUE_FEED": "", "SI_TRADER_SOURCE_MANIFEST": ""}))
        self.frame = pd.DataFrame([dict(symbol=f"TEST{i:03}", company_name=f"Fixture {i}", isin=f"FIXTURE{i}",
            close=100.+i, daily_turnover_crore=100., price_momentum_daily=-1., price_momentum_weekly=-5.+i/10) for i in range(100)])
        self.market = dict(asOf="2026-11-25", source="Test fixture", covered=100, universeSize=100, unverifiedChecks=[])
        for target, value in (
            ("web_app.load_nifty100", (self.frame, self.market)),
            ("web_app.installed_models", ["fixture"]),
            ("full_catalogue.pe_data", {}), ("full_catalogue.ownership_data", {}),
            ("full_catalogue.collect_public_records", ({}, [])),
        ):
            self.stack.enter_context(patch("nifty100_weekly.nifty100_adapter."+target, return_value=value))
        self.planner = self.stack.enter_context(patch("nifty100_weekly.nifty100_adapter.web_app.generate_plan", return_value={
            "basket": [{"symbol": "TEST099", "price": 199., "weight": 20, "rationale": "Fixture"}], "title": "Fixture", "thesis": "Fixture"}))
        self.server = create_server(port=0, runtime=Runtime())
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, route="/api/strategy", body=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = body if body is not None else {"model": "fixture", "objective": "Fixture weekly study", "maxPositions": 5,
                "execution": {"funding": "paper", "paperCapital": 500000, "cashBuffer": 10, "scenarioMove": 5, "paperAuto": True}}
        client.request("POST", route, json.dumps(body), {"Origin":f"http://127.0.0.1:{self.server.server_port}", "Content-Type":"application/json"})
        response = client.getresponse()
        result = response.status, json.loads(response.read())
        client.close()
        return result

    def test_background_run_returns_promptly_and_halt_blocks_late_fills(self):
        entered, release = Event(), Event()
        plan = self.planner.return_value
        def slow_plan(*args, **kwargs):
            entered.set()
            release.wait(3)
            return plan
        self.planner.side_effect = slow_plan
        payload = {"route": "/api/strategy", "requestId": "a"*32, "body": {
            "model": "fixture", "objective": "Fixture", "maxPositions": 5,
            "execution": {"funding": "paper", "paperCapital": 500000, "cashBuffer": 10, "scenarioMove": 5, "paperAuto": True}}}
        try:
            started = time.monotonic()
            status, job = self.request("/api/research-jobs", payload)
            self.assertEqual(status, 202)
            self.assertLess(time.monotonic()-started, 2)
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.request("/api/research-jobs", payload)[1]["id"], job["id"])
            running = self.request("/api/research-jobs/status", {"id": job["id"]})[1]
            self.assertEqual(running["details"]["parametersEvaluated"], 48)
            self.server.workspace.dispatch({"action": "halt"})
        finally:
            release.set()
        for _ in range(100):
            result = self.request("/api/research-jobs/status", {"id": job["id"]})[1]
            if result["state"] == "failed":
                break
            time.sleep(.01)
        self.assertEqual(result["state"], "failed")
        self.assertIn("halted", result["result"]["error"])
        self.assertEqual(self.planner.call_count, 1)

    def test_migrated_catalogue_generates_weekly_paper_basket(self):
        self.assertNotIn("price_momentum_daily", PARAMETERS)
        self.assertTrue(LIVE_COLUMNS.issubset(PARAMETERS))
        status, result = self.request()
        self.assertEqual(status, 200, result)
        self.assertEqual(result["considered"], 100)
        self.assertEqual(result["parameterRunReport"]["total"], 48)
        self.assertEqual(len(result["parameterRunReport"]["rows"]), 48)
        self.assertGreater(result["execution"]["fills"][0]["quantity"], 0)
        self.assertGreaterEqual(result["execution"]["cashRemaining"], 50000)
        self.assertTrue(self.planner.called)

    def test_paper_broker_connect_does_not_require_credentials_or_invent_funds(self):
        with patch("nifty100_weekly.nifty100_adapter.web_app.broker_snapshot") as live:
            status, result = self.request("/api/broker/connect", {})
        self.assertEqual(status, 200)
        self.assertEqual(result["platform"], "paper")
        self.assertIsNone(result["cash"])
        self.assertFalse(result["liveEnabled"])
        live.assert_not_called()
        self.assertEqual(self.request("/api/broker/connect", {"platform": "unknown"})[0], 400)

    def test_live_broker_requires_verified_read_only_funds(self):
        with patch("nifty100_weekly.nifty100_adapter.web_app.broker_snapshot", return_value={"funds":{"error":"Configure InvestRight API credentials"}}):
            status, result = self.request("/api/broker/connect", {"platform":"investright"})
        self.assertEqual(status,400)
        self.assertIn("credentials",result["error"])

    def test_quant_scenario_endpoint(self):
        status, result = self.request("/api/quant-scenario", {"spot":100,"strike":100,"volatilityPct":20})
        self.assertEqual(status,200)
        self.assertIn("delta",result["greeks"])
        self.assertEqual(result["monteCarlo"]["paths"],10000)

    def test_missing_ranking_data_returns_empty_basket_not_an_exception(self):
        self.frame["price_momentum_weekly"] = float("nan")
        status, result = self.request()
        self.assertEqual(status, 200, result)
        self.assertEqual(result["basket"], [])
        self.assertFalse(self.planner.called)

    def test_provider_failure_returns_upstream_status_and_retry_can_succeed(self):
        for error in (ProviderTimeout("Provider timed out; check LLM Configuration."),
                      ProviderUnavailable("Provider unavailable; check LLM Configuration.")):
            with self.subTest(status=error.status):
                self.planner.side_effect = error
                with patch("nifty100_weekly.nifty100_adapter.web_app.paper_sizing") as sizing:
                    status, result = self.request()
                self.assertEqual(status, error.status)
                self.assertEqual(result["code"], error.code)
                sizing.assert_not_called()
                self.assertNotIn("basket", result)
                self.planner.side_effect = None
                self.assertEqual(self.request()[0], 200)

    def test_unexpected_internal_error_returns_json_and_server_stays_healthy(self):
        with patch("nifty100_weekly.nifty100_adapter.web_app.readiness", side_effect=KeyError("private-internal-fixture")):
            status, result = self.request()
        self.assertEqual(status, 500)
        self.assertIn("requestId", result)
        self.assertNotIn("private-internal-fixture", json.dumps(result))
        self.assertEqual(self.request()[0], 200)


if __name__ == "__main__":
    unittest.main()

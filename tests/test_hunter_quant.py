"""Source evidence must remain distinct from acquired pages and scenario maths."""
import math
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import pandas as pd
from nifty100_weekly.nifty100_adapter import evidence_hunter as hunter
from nifty100_weekly.nifty100_adapter.quantitative import greeks, scenario


class HunterTests(unittest.TestCase):
    def setUp(self):
        self.coverage = {"ready": False, "complete": 0, "sourceFeeds": [], "parameters": [
            {"key": key, "label": p.display_name, "role": p.role_type.value, "ready": False,
             "available": 0, "expected": 100, "invalid": 0, "conflicts": 0}
            for key,p in hunter.PARAMETERS.items()]}
        self.initial = pd.DataFrame({"symbol": ["TCS", "INFY"]}), {"asOf": "2026-11-26"}, self.coverage

    def test_all_48_have_acquisition_tasks_and_pages_do_not_become_facts(self):
        with patch.object(hunter, "download", return_value=b"<html>Source document</html>") as fetch:
            result = hunter.hunt({"url": "https://untrusted.example"}, initial=self.initial)
        self.assertEqual(len(result["parameters"]), 48)
        self.assertEqual(result["complete"], 0)
        self.assertFalse(result["tradeEligible"])
        self.assertLessEqual(fetch.call_count, 12)
        self.assertTrue(all(urlsplit(call.args[0]).hostname in hunter.OFFICIAL for call in fetch.call_args_list))
        self.assertTrue(all("Not promoted" in row["validation"] for row in result["attempts"]))
        self.assertTrue(all(row["sourceName"] and row["nextAction"] for row in result["parameters"]))

    def test_failures_are_visible_and_llm_cannot_mark_gaps_ready(self):
        with patch.object(hunter, "download", side_effect=OSError()), patch.object(hunter, "agent", return_value={"priority": ["invented"]}):
            result = hunter.hunt({"model": "fixture"}, initial=self.initial)
        self.assertTrue(result["aiError"])
        self.assertEqual(result["complete"], 0)
        self.assertTrue(all(row["status"] == "Unavailable or rejected" for row in result["attempts"]))

    def test_committee_receives_hunt_and_quantitative_context_without_fake_coverage(self):
        from nifty100_weekly.nifty100_adapter import research_committee as committee
        acquisition = {"note":"Candidate pages are not validated data", "attempts":[], "parameters":[]}
        inputs = {"spot":100,"strike":100,"volatilityPct":20}
        with patch.object(committee,"load_nifty100",return_value=self.initial[:2]), patch.object(committee,"readiness",return_value=(self.coverage,{})), patch.object(hunter,"hunt",return_value=acquisition) as search, patch.object(committee,"review_agents",return_value={}) as review:
            result = committee.build_committee("fixture","Research",[],inputs)
        search.assert_called_once()
        self.assertEqual(len(result["acquisitionPlan"]),48)
        self.assertIn("delta",review.call_args.args[6]["greeks"])
        self.assertFalse(review.call_args.args[6]["tradeEligible"])
        self.assertEqual(review.call_args.args[7]["note"],acquisition["note"])


class QuantTests(unittest.TestCase):
    def test_call_put_parity_and_greek_units_by_finite_differences(self):
        s,k,t,v,r,q = 100,100,1,.2,.05,.02
        call, put = greeks(s,k,t,v,r,q), greeks(s,k,t,v,r,q, "put")
        self.assertAlmostEqual(call["theoreticalPrice"], 9.2270055, places=6)
        self.assertAlmostEqual(call["theoreticalPrice"]-put["theoreticalPrice"],s*math.exp(-q*t)-k*math.exp(-r*t),places=9)
        step = .001
        up, down = greeks(s+step,k,t,v,r,q), greeks(s-step,k,t,v,r,q)
        self.assertAlmostEqual(call["delta"], (up["theoreticalPrice"]-down["theoreticalPrice"])/(2*step), places=7)
        self.assertAlmostEqual(call["gamma"], (up["theoreticalPrice"]-2*call["theoreticalPrice"]+down["theoreticalPrice"])/step**2, places=6)
        dv = 1e-5
        self.assertAlmostEqual(call["vegaPerVolPoint"], (greeks(s,k,t,v+dv,r,q)["theoreticalPrice"]-greeks(s,k,t,v-dv,r,q)["theoreticalPrice"])/(2*dv*100), places=6)
        self.assertAlmostEqual(call["thetaPerCalendarDay"], -(greeks(s,k,t+dv,v,r,q)["theoreticalPrice"]-greeks(s,k,t-dv,v,r,q)["theoreticalPrice"])/(2*dv*365), places=6)
        self.assertAlmostEqual(call["rhoPerRatePoint"], (greeks(s,k,t,v,r+dv,q)["theoreticalPrice"]-greeks(s,k,t,v,r-dv,q)["theoreticalPrice"])/(2*dv*100), places=6)

    def test_monte_carlo_is_seeded_ordered_and_not_a_forecast(self):
        inputs = {"spot":100,"strike":100,"volatilityPct":20,"sessions":21}
        result = scenario(inputs)
        self.assertEqual(result, scenario(inputs))
        stress = result["monteCarlo"]
        self.assertEqual(stress["paths"],10000)
        self.assertEqual(stress["terminalReturnsPct"],sorted(stress["terminalReturnsPct"]))
        self.assertGreaterEqual(stress["expectedShortfall95LossPct"],stress["var95LossPct"])
        self.assertFalse(result["tradeEligible"])
        self.assertNotIn("untrustedExtra",scenario({**inputs,"untrustedExtra":"not forwarded to agents"})["inputs"])
        for bad in ({"volatilityPct":0},{"spot":float("nan")},{"sessions":1000000},{"ratePct":10000},{"option":"invalid"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scenario({**inputs,**bad})

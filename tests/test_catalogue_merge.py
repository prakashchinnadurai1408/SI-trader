"""Regression checks for the incoming catalogue strategy integration."""

import unittest

from nifty100_weekly.nifty100_adapter import full_catalogue as catalogue
from nifty100_weekly.nifty100_adapter.backtest.monthly_backtester import run_prepared
from nifty100_weekly.nifty100_adapter.backtest.weekly_backtester import ScoreCalculator


class CatalogueMergeTests(unittest.TestCase):
    def test_positive_stock_scores_are_counted_and_missing_evidence_blocks(self):
        records = {}
        for key, definition in catalogue.PARAMETERS.items():
            value = 50
            if definition.role_type == catalogue.RoleType.FILTER:
                value = True
            elif definition.role_type == catalogue.RoleType.VETO:
                value = False
            if key in catalogue.THRESHOLDS:
                value = definition.min_value or 0
            if key == "cost_vs_edge_check":
                value = 1
            lookup = "*" if key in catalogue.MARKET_FACTORS else "TEST"
            records[key] = {lookup: {"value": value}}
        evidence = {"ready": True, "parameters": []}
        result = catalogue.score_individual_stock("TEST", records, evidence)
        self.assertGreater(result["score"], 0)
        self.assertTrue(result["tradeEligible"])
        unknown = catalogue.score_individual_stock("UNKNOWN", records, evidence)
        self.assertEqual(unknown["status"], "blocked")
        self.assertFalse(unknown["tradeEligible"])

    def test_weekly_pledging_and_net_edge_keep_numeric_meaning(self):
        calculator = ScoreCalculator()
        self.assertTrue(calculator.apply_vetoes({"promoter_pledging_pct": 10,
                                                 "cost_vs_edge_check": 2}))
        self.assertFalse(calculator.apply_vetoes({"promoter_pledging_pct": 26}))
        self.assertFalse(calculator.apply_vetoes({"cost_vs_edge_check": 0}))
        self.assertFalse(calculator.apply_vetoes({"auditor_resignations": True}))

    def test_weekly_rates_are_cost_inputs_not_stock_filters(self):
        self.assertTrue(ScoreCalculator().apply_filters({"stcg_tax_rate": 200}))

    def test_monthly_experiments_cannot_mix_weight_sources(self):
        for kwargs in ({"weights": {}, "catalogue_weights": {}},
                       {"defensive": True, "catalogue_weights": {}},
                       {"experiment": "sector_momentum", "catalogue_weights": {}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_prepared(None, {}, "2025-01", "2025-02", 100000, **kwargs)


if __name__ == "__main__":
    unittest.main()

"""Constrain model output without weakening the paper basket checks."""
import json
import unittest
from unittest.mock import patch
from nifty100_weekly.nifty100_adapter.ai_strategy import generate_plan


class WeeklyPlanFormat(unittest.TestCase):
    def setUp(self):
        self.candidates = [{"symbol": f"TEST{i}", "price": 100} for i in range(5)]

    def run_plan(self, basket):
        response = {"message": {"content": json.dumps({"title": "Research", "thesis": "Fixture", "basket": basket})}}
        with patch("nifty100_weekly.nifty100_adapter.ai_strategy.ollama", return_value=response) as client:
            result = generate_plan("fixture", "Research", self.candidates, 5)
        return result, client.call_args.args[1]["format"]

    def test_schema_limits_symbols_positions_and_weights(self):
        result, schema = self.run_plan([{"symbol": "TEST0", "weight": 18, "reason": "Observed fixture"}])
        self.assertEqual(result["basket"][0]["weight"], 18)
        items = schema["properties"]["basket"]["items"]["properties"]
        self.assertEqual(items["symbol"]["enum"], [item["symbol"] for item in self.candidates])
        self.assertEqual(items["weight"]["maximum"], 20)
        self.assertEqual(schema["properties"]["basket"]["maxItems"], 5)

    def test_risk_limits_still_reject_model_mistakes(self):
        baskets = [
            [{"symbol": "OUTSIDE", "weight": 10, "reason": "Fixture"}],
            [{"symbol": "TEST0", "weight": 21, "reason": "Fixture"}],
            [{"symbol": "TEST0", "weight": 10, "reason": "Fixture"}]*2,
            [{"symbol": f"TEST{i}", "weight": 20, "reason": "Fixture"} for i in range(5)],
        ]
        for basket in baskets:
            with self.subTest(basket=basket), self.assertRaisesRegex(ValueError, "model"):
                self.run_plan(basket)

    def test_empty_research_basket_remains_valid(self):
        self.assertEqual(self.run_plan([])[0]["basket"], [])

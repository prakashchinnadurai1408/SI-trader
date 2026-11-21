"""Strategy integrations, parameter catalogue and pipeline tests.

Dependency-free: every module under test degrades gracefully when optional
third-party packages (aiohttp, requests, vectorbt, backtrader) are missing,
so these tests run on the core requirements.txt only.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _looks_like_current_layout(root):
    """True when `root` holds the current 48-parameter catalogue."""
    cfg = os.path.join(root, "nifty100_adapter", "config",
                       "parameter_catalogue.py")
    if not os.path.isfile(cfg):
        return False
    try:
        with open(cfg, encoding="utf-8") as fh:
            return '"f_score"' in fh.read()
    except OSError:
        return False


# Prefer the layout that actually carries the current parameter catalogue.
CANDIDATE_ROOTS = [
    os.path.join(REPO_ROOT, "legacy", "phase-platform"),  # main layout
    os.path.join(REPO_ROOT, "nifty100_weekly"),           # older layout
    REPO_ROOT,
]
_resolved = next(
    (r for r in CANDIDATE_ROOTS if _looks_like_current_layout(r)), None)

if _resolved and _resolved not in sys.path:
    sys.path.insert(0, _resolved)


class ParameterCatalogueTests(unittest.TestCase):
    """BRD constraint: 48 enabled parameters, total weight 100."""

    @classmethod
    def setUpClass(cls):
        from nifty100_adapter.config import parameter_catalogue as pc
        cls.pc = pc

    def test_parameter_count_is_48(self):
        self.assertEqual(len(self.pc.PARAMETER_CATALOGUE), 48)

    def test_total_weight_is_100(self):
        self.assertEqual(self.pc.get_total_weight(), 100)

    def test_weight_total_validates(self):
        self.assertTrue(self.pc.validate_weight_total())

    def test_every_parameter_has_weight_at_least_one(self):
        for key, p in self.pc.PARAMETER_CATALOGUE.items():
            self.assertGreaterEqual(
                p.weight, 1, f"{key} must have weight >= 1")

    def test_role_breakdown(self):
        expected = {
            "Score": (13, 43),
            "Filter": (10, 20),
            "Veto": (6, 15),
            "Market dial": (2, 5),
            "Advisory": (12, 12),
            "Flag": (5, 5),
        }
        from nifty100_adapter.config.parameter_catalogue import (
            get_parameters_by_role, RoleType)
        for role_name, (count, weight) in expected.items():
            params = get_parameters_by_role(RoleType(role_name))
            self.assertEqual(len(params), count, role_name)
            self.assertEqual(sum(p.weight for p in params), weight, role_name)

    def test_fundamental_scores_present(self):
        for key in ("f_score", "altman_z_score"):
            self.assertIn(key, self.pc.PARAMETER_CATALOGUE)


class StrategyAdapterTests(unittest.TestCase):
    """Every strategy source must emit a 48-param, weight-100 config."""

    def _assert_config(self, config):
        self.assertEqual(
            sum(config["parameter_weights"].values()), 100,
            f"{config['strategy_name']} weight total")
        self.assertEqual(
            len(config["parameter_weights"]), 48,
            f"{config['strategy_name']} parameter count")

    def test_ma_crossover_strategies(self):
        from nifty100_adapter.strategy import (
            MACrossoverAdapter, get_ma_strategy_config)
        adapter = MACrossoverAdapter()
        self.assertEqual(len(adapter.MA_STRATEGIES), 4)
        for name in adapter.MA_STRATEGIES:
            self._assert_config(get_ma_strategy_config(name))

    def test_ai_strategy_generation(self):
        from nifty100_adapter.strategy import AIStrategyGenerator
        gen = AIStrategyGenerator(llm_provider="openai")
        result = gen.generate_strategy_ideas(
            market_condition="trending", sector="all",
            time_horizon="daily", risk_tolerance="medium", num_ideas=3)
        self.assertGreater(result.total_ideas, 0)
        for config in gen.generate_strategy_configs(result.ideas):
            self._assert_config(config)

    def test_options_strategies(self):
        from nifty100_adapter.strategy import (
            OptionsStrategyAdapter, get_option_strategy_config)
        adapter = OptionsStrategyAdapter()
        self.assertEqual(len(adapter.OPTION_STRATEGIES), 7)
        for name in adapter.OPTION_STRATEGIES:
            self._assert_config(get_option_strategy_config(name))

    def test_algo_india_strategies(self):
        from nifty100_adapter.strategy import AlgoIndiaAdapter
        adapter = AlgoIndiaAdapter()
        for strategy in adapter.load_strategies():
            self._assert_config(adapter.generate_strategy_config(strategy))

    def test_pkscreener_pattern_strategies(self):
        from nifty100_adapter.strategy import PKScreenerAdapter, PkScreenerSignal
        adapter = PKScreenerAdapter()
        signals = [
            PkScreenerSignal(symbol="RELIANCE", pattern_name="breakout_template",
                             pattern_type="breakout", confidence=80.0,
                             entry_price=2500.0),
            PkScreenerSignal(symbol="TCS", pattern_name="flag_template",
                             pattern_type="flag", confidence=70.0,
                             entry_price=3200.0),
        ]
        self._assert_config(adapter.generate_strategy_config(signals))

    def test_weight_normaliser_guarantees_total(self):
        from nifty100_adapter.strategy._weight_utils import normalize_weights
        self.assertEqual(sum(normalize_weights({"a": 3, "b": 5, "c": 1}).values()), 100)
        self.assertEqual(sum(normalize_weights({"a": 103, "b": 27}).values()), 100)
        self.assertEqual(sum(normalize_weights({"a": 1, "b": 1}).values()), 100)
        with self.assertRaises(ValueError):
            normalize_weights({})


class PortfolioOptimizerTests(unittest.TestCase):
    """Portfolio allocation must respect the BRD cash buffer."""

    def setUp(self):
        from nifty100_adapter.risk.portfolio_optimizer import PortfolioOptimizer
        self.optimizer = PortfolioOptimizer(capital=25000.0)

    def test_cash_buffer_is_preserved(self):
        strategies = [{"strategy_name": f"S{i}", "strategy_type": "momentum",
                       "weight_total": 100, "delivery_compatible": True}
                      for i in range(6)]
        result = self.optimizer.optimize_portfolio(strategies, max_strategies=6)
        self.assertGreaterEqual(result.cash_pct, 10.0 - 1e-6)
        self.assertTrue(result.brd_compliant)

    def test_position_sizing_respects_max_loss(self):
        rec = self.optimizer.get_position_sizing_recommendation(
            strategy_name="RELIANCE", entry_price=100.0, stop_loss=95.0)
        # max loss per trade = 2% of 25,000 = 500; risk/share = 5 -> 100 shares
        # position cap = 10% of 25,000 = 2,500 -> 25 shares; cap wins
        self.assertTrue(rec["valid"])
        self.assertEqual(rec["shares"], 25)
        self.assertEqual(rec["deciding_limit"], "position_cap")
        self.assertLessEqual(rec["total_risk_at_stop"], 500.0 + 1e-9)

    def test_empty_portfolio_is_compliant(self):
        result = self.optimizer.optimize_portfolio([])
        self.assertTrue(result.brd_compliant)
        self.assertEqual(result.cash_pct, 100.0)


class UniversalHubTests(unittest.TestCase):
    """The hub must ingest from every strategy source."""

    @classmethod
    def setUpClass(cls):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        cls.hub = UniversalStrategyHub(HubConfig(llm_provider="openai"))

    def test_ingests_all_sources(self):
        results = self.hub.ingest_all_strategy_sources(
            symbols=["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
            market_condition="trending", risk_tolerance="medium")
        for source in ("ma_crossover", "ai_llm", "options", "pkscreener",
                       "algo_india"):
            self.assertIn(source, results)
            self.assertGreater(len(results[source]), 0, source)

    def test_all_candidates_are_brd_compliant(self):
        self.hub.ingest_all_strategy_sources(symbols=["RELIANCE", "TCS"])
        non_compliant = [c.name for c in self.hub.strategy_candidates
                        if c.weight_total != 100 or not c.is_brd_compliant]
        self.assertEqual(non_compliant, [])

    def test_selection_returns_compliant_strategies(self):
        self.hub.ingest_all_strategy_sources(symbols=["RELIANCE"])
        selected = self.hub.select_strategies(min_confidence=40.0,
                                             max_strategies=5)
        self.assertGreater(len(selected), 0)
        for c in selected:
            self.assertTrue(c.is_brd_compliant)

    def test_portfolio_optimization_keeps_cash_buffer(self):
        self.hub.ingest_all_strategy_sources(symbols=["RELIANCE"])
        opt = self.hub.optimize_portfolio(max_strategies=5)
        self.assertTrue(opt["brd_compliant"])
        self.assertGreaterEqual(opt["cash_pct"], 10.0 - 1e-6)

    def test_status_reports_new_adapters(self):
        status = self.hub.get_status()
        self.assertTrue(status["ma_crossover_available"])
        self.assertTrue(status["ai_strategy_available"])
        self.assertTrue(status["options_available"])
        self.assertTrue(status["portfolio_optimizer_available"])
        self.assertIn("candidates_by_source", status)


class DataPipelineTests(unittest.TestCase):
    """The pipeline must register available adapters and skip the rest."""

    def test_build_default_pipeline(self):
        from nifty100_adapter.data.pipeline_orchestrator import (
            build_default_pipeline, DEFAULT_ADAPTER_SPECS)
        orchestrator = build_default_pipeline()
        self.assertGreater(len(orchestrator.adapters), 0)
        for name, adapter in orchestrator.adapters.items():
            self.assertIn(name, [s[0] for s in DEFAULT_ADAPTER_SPECS])
            self.assertIsNotNone(adapter)

    def test_pipeline_is_healthy(self):
        import asyncio
        from nifty100_adapter.data.pipeline_orchestrator import (
            build_default_pipeline)
        orchestrator = build_default_pipeline()
        asyncio.run(orchestrator.refresh_now(list(orchestrator.adapters)))
        health = orchestrator.get_health()
        self.assertEqual(health.overall_status, "HEALTHY")
        self.assertEqual(health.failed_sources, [])


class DataSourceCatalogueTests(unittest.TestCase):
    """Every catalogue parameter must map to a data source."""

    def test_all_parameters_mapped(self):
        from nifty100_adapter.config.parameter_catalogue import PARAMETER_CATALOGUE
        from nifty100_adapter.data.data_source_catalogue import (
            PARAMETER_TO_DATA_SOURCE)
        missing = set(PARAMETER_CATALOGUE) - set(PARAMETER_TO_DATA_SOURCE)
        self.assertEqual(missing, set())

    def test_known_mappings(self):
        from nifty100_adapter.data.data_source_catalogue import (
            PARAMETER_TO_DATA_SOURCE)
        self.assertEqual(
            PARAMETER_TO_DATA_SOURCE["price_momentum_weekly"].source_name,
            "NSE Price History")
        self.assertEqual(
            PARAMETER_TO_DATA_SOURCE["f_score"].source_name,
            "NSE Fundamentals")
        self.assertEqual(
            PARAMETER_TO_DATA_SOURCE["altman_z_score"].source_name,
            "NSE Financial Statements")


class BrokerLayerTests(unittest.TestCase):
    """Core broker types and adapters must be importable."""

    def test_core_types_available(self):
        from nifty100_adapter.broker import (
            BrokerPlatform, OrderSide, OrderType, ProductType, OrderStatus,
            OrderRequest, OrderResponse, Position, BrokerAdapter)
        self.assertEqual(BrokerPlatform.OPEN_ALGO.value, "open_algo")
        self.assertEqual(ProductType.CNC.value, "CNC")
        self.assertEqual(OrderSide.BUY.value, "BUY")

    def test_adapters_import(self):
        from nifty100_adapter.broker import (
            OpenAlgoAdapter, KiteConnectAdapter, FenixAdapter)
        self.assertIsNotNone(OpenAlgoAdapter)
        self.assertIsNotNone(KiteConnectAdapter)
        self.assertIsNotNone(FenixAdapter)

    def test_openalgo_adapter_instantiates(self):
        from nifty100_adapter.broker import OpenAlgoAdapter, BrokerConfig, BrokerPlatform
        adapter = OpenAlgoAdapter(
            BrokerConfig(platform=BrokerPlatform.OPEN_ALGO,
                         base_url="http://localhost:5000"))
        self.assertFalse(adapter.is_connected())
        self.assertIn("open_algo", repr(adapter))


if __name__ == "__main__":
    unittest.main()
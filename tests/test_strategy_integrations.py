"""Strategy integrations, parameter catalogue and pipeline tests.

Dependency-free: every module under test degrades gracefully when optional
third-party packages (aiohttp, requests, vectorbt, backtrader) are missing,
so these tests run on the core requirements.txt only.
"""

import json
import os
import shutil
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
# nifty100_weekly is now the single source of truth (48-parameter catalogue).
CANDIDATE_ROOTS = [
    os.path.join(REPO_ROOT, "nifty100_weekly"),   # current layout (migrated)
    os.path.join(REPO_ROOT, "legacy", "phase-platform"),  # legacy layout
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


class LLMClientTests(unittest.TestCase):
    """The AI generator must be able to call a real model, and degrade."""

    def test_all_ten_providers_have_specs(self):
        from nifty100_adapter.strategy.llm_client import PROVIDERS, SUPPORTED_PROVIDERS
        expected = {"openai", "anthropic", "nvidia", "gemini", "deepseek",
                    "grok", "z.ai", "kimi", "qwen", "ollama"}
        self.assertEqual(set(SUPPORTED_PROVIDERS), expected)
        for name, spec in PROVIDERS.items():
            self.assertTrue(spec.base_url.startswith("http"), name)
            self.assertTrue(spec.default_model, name)
            # ollama runs locally and needs no key
            if name != "ollama":
                self.assertTrue(spec.env_var, name)

    def test_unknown_provider_rejected(self):
        from nifty100_adapter.strategy.llm_client import LLMClient
        with self.assertRaises(ValueError):
            LLMClient(provider="not-a-provider")

    def test_credentials_gate(self):
        from nifty100_adapter.strategy.llm_client import LLMClient
        import os
        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self.assertFalse(LLMClient(provider="openai").has_credentials())
            os.environ["OPENAI_API_KEY"] = "test-key"
            self.assertTrue(LLMClient(provider="openai").has_credentials())
            # ollama is local and keyless
            self.assertTrue(LLMClient(provider="ollama").has_credentials())
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved

    def test_json_extraction_from_prose(self):
        from nifty100_adapter.strategy.llm_client import _extract_json
        self.assertEqual(_extract_json('[{\"a\": 1}]'), [{"a": 1}])
        self.assertEqual(_extract_json({'k': 'v'}), {"k": "v"})
        self.assertEqual(
            _extract_json('Sure! ```json\n{\"x\": 2}\n``` thanks'), {"x": 2})
        self.assertIsNone(_extract_json("no json here"))
        self.assertIsNone(_extract_json(""))

    def test_complete_returns_empty_without_key(self):
        from nifty100_adapter.strategy.llm_client import LLMClient
        import os
        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            client = LLMClient(provider="openai")
            self.assertEqual(client.complete("sys", "prompt"), "")
            self.assertEqual(client.generate_strategy_ideas("s", "p"), [])
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved

    def test_generator_falls_back_without_credentials(self):
        from nifty100_adapter.strategy import AIStrategyGenerator
        import os
        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            gen = AIStrategyGenerator(llm_provider="openai")
            self.assertFalse(gen.has_live_llm())
            result = gen.generate_strategy_ideas(market_condition="trending",
                                                num_ideas=3)
            self.assertGreater(result.total_ideas, 0)
            for cfg in gen.generate_strategy_configs(result.ideas):
                self.assertEqual(cfg["weight_total"], 100)
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved

    def test_generator_reports_live_when_key_present(self):
        from nifty100_adapter.strategy import AIStrategyGenerator
        import os
        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            os.environ["OPENAI_API_KEY"] = "test-key"
            gen = AIStrategyGenerator(llm_provider="openai")
            self.assertTrue(gen.has_live_llm())
            # a bad key must not raise - it degrades to templates
            result = gen.generate_strategy_ideas(market_condition="ranging",
                                                num_ideas=2)
            self.assertGreater(result.total_ideas, 0)
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved


class WeightedBacktestTests(unittest.TestCase):
    """Different weights must produce different backtest results."""

    @staticmethod
    def _bars(n=320, drift=0.001, vol=0.012, seed=11):
        import random
        rng = random.Random(seed)
        price = 100.0
        out = []
        for _ in range(n):
            price *= 1 + drift + rng.gauss(0, vol)
            out.append({"close": round(price, 2), "volume": int(1e6),
                        "open": round(price, 2), "high": round(price, 2),
                        "low": round(price, 2)})
        return out

    @classmethod
    def _prices(cls):
        return {"RELIANCE": cls._bars(drift=0.0025),
                "TCS": cls._bars(drift=0.0005, seed=12),
                "HDFCBANK": cls._bars(drift=-0.0008, seed=13)}

    def test_different_weights_give_different_results(self):
        from nifty100_adapter.backtest.sitrader_strategy_backtester import (
            StrategyBacktester)
        from nifty100_adapter.strategy import get_ma_strategy_config
        bt = StrategyBacktester(capital=25000.0, top_n=1)
        a = bt.run("MA5_MA10",
                   get_ma_strategy_config("MA5_MA10")["parameter_weights"],
                   self._prices())
        b = bt.run("MA20_MA50",
                   get_ma_strategy_config("MA20_MA50")["parameter_weights"],
                   self._prices())
        self.assertNotEqual(a.total_return_pct, b.total_return_pct)

    def test_costs_are_applied(self):
        from nifty100_adapter.backtest.sitrader_strategy_backtester import (
            StrategyBacktester)
        from nifty100_adapter.strategy import get_ma_strategy_config
        bt = StrategyBacktester(capital=25000.0, top_n=1)
        result = bt.run("x", get_ma_strategy_config("MA5_MA10")["parameter_weights"],
                        self._prices())
        # the BRD quotes ~0.38% round-trip; the cost model computes the exact
        # figure, so compare against the model rather than the headline number
        self.assertEqual(result.cost_pct, bt.cost_model.roundtrip_cost_pct)
        self.assertGreater(result.cost_pct, 0.3)
        self.assertGreater(result.total_trades, 0)

    def test_metrics_are_consistent(self):
        from nifty100_adapter.backtest.sitrader_strategy_backtester import (
            StrategyBacktester)
        from nifty100_adapter.strategy import get_ma_strategy_config
        bt = StrategyBacktester(capital=25000.0, top_n=1)
        result = bt.run("x", get_ma_strategy_config("MA5_MA10")["parameter_weights"],
                        self._prices())
        self.assertGreaterEqual(result.win_rate, 0)
        self.assertLessEqual(result.win_rate, 100)
        self.assertGreaterEqual(result.max_drawdown_pct, 0)
        d = result.as_dict()
        for key in ("total_return", "net_profit", "sharpe", "max_drawdown",
                    "win_rate", "total_trades", "avg_trade", "expectancy",
                    "final_value", "cost_pct"):
            self.assertIn(key, d)

    def test_empty_prices_is_safe(self):
        from nifty100_adapter.backtest.sitrader_strategy_backtester import (
            StrategyBacktester)
        result = StrategyBacktester().run("x", {"price_momentum_weekly": 5}, {})
        self.assertEqual(result.total_trades, 0)
        self.assertFalse(result.brd_compliant)

    def test_hub_backtest_populates_candidate(self):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        hub = UniversalStrategyHub(HubConfig(llm_provider="openai",
                                            max_positions=1))
        hub.ingest_ma_crossovers(["MA5_MA10", "MA20_MA50"])
        results = [hub.backtest_candidate(c, self._prices())
                   for c in hub.strategy_candidates]
        self.assertEqual(len(results), 2)
        self.assertNotEqual(results[0]["total_return"],
                            results[1]["total_return"])
        for c in hub.strategy_candidates:
            self.assertIsNotNone(c.backtest_results)
            self.assertIn("net_edge", c.edge_validation)


class OptionsPayoffTests(unittest.TestCase):
    """Option strategies must price with sensible, distinct economics."""

    SPOT = 19000.0

    def test_debit_spread_has_capped_risk_and_reward(self):
        from nifty100_adapter.strategy.options_strategy_adapter import (
            OptionsStrategyAdapter)
        c = OptionsStrategyAdapter().get_strategy_config("bull_call_spread",
                                                         self.SPOT)
        self.assertEqual(c["weight_total"], 100)
        self.assertTrue(c["brd_compliant"])
        self.assertGreater(c["max_profit"], 0)
        self.assertGreater(c["max_loss"], 0)
        self.assertLess(c["reward_risk_ratio"], 2.0)  # debit spread, not credit

    def test_credit_spread_profit_exceeds_loss(self):
        from nifty100_adapter.strategy.options_strategy_adapter import (
            OptionsStrategyAdapter)
        c = OptionsStrategyAdapter().get_strategy_config("iron_condor", self.SPOT)
        self.assertGreater(c["max_profit"], c["max_loss"])
        self.assertEqual(len(c["breakeven"]), 2)

    def test_long_volatility_loss_equals_premium(self):
        from nifty100_adapter.strategy.options_strategy_adapter import (
            OptionsStrategyAdapter)
        c = OptionsStrategyAdapter().get_strategy_config("long_straddle",
                                                        self.SPOT)
        # max loss is the premium paid; max profit is effectively unbounded
        self.assertGreater(c["max_loss"], 0)
        self.assertGreater(c["max_profit"], c["max_loss"] * 10)

    def test_covered_call_loss_dominates_profit(self):
        from nifty100_adapter.strategy.options_strategy_adapter import (
            OptionsStrategyAdapter)
        c = OptionsStrategyAdapter().get_strategy_config("covered_call",
                                                        self.SPOT)
        self.assertGreater(c["max_loss"], c["max_profit"])

    def test_breakevens_bracket_the_spot(self):
        from nifty100_adapter.strategy.options_strategy_adapter import (
            OptionsStrategyAdapter)
        c = OptionsStrategyAdapter().get_strategy_config("long_strangle",
                                                        self.SPOT)
        bes = c["breakeven"]
        self.assertEqual(len(bes), 2)
        self.assertLess(bes[0], self.SPOT)
        self.assertGreater(bes[1], self.SPOT)

    def test_all_strategies_price(self):
        from nifty100_adapter.strategy.options_strategy_adapter import (
            OptionsStrategyAdapter)
        adapter = OptionsStrategyAdapter()
        for name, config in adapter.OPTION_STRATEGIES.items():
            result = adapter.get_strategy_config(name, self.SPOT)
            self.assertEqual(result["weight_total"], 100, name)
            self.assertGreater(result["margin_required"], 0, name)
            self.assertTrue(result["breakeven"], name)


class ExecutionBridgeTests(unittest.TestCase):
    """Selected strategies must become sized, stoppped, executable orders."""

    PRICES = {"RELIANCE": 2500.0, "TCS": 3200.0, "HDFCBANK": 1600.0}

    @classmethod
    def setUpClass(cls):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        cls.hub = UniversalStrategyHub(HubConfig(llm_provider="openai",
                                                max_positions=2))
        cls.hub.ingest_pkscreener_signals(["RELIANCE", "TCS", "HDFCBANK"])
        cls.hub.select_strategies(min_confidence=40, max_strategies=2)
        cls.plan = cls.hub.build_trading_plan(
            candidate_names=[c.name for c in cls.hub.selected_strategies],
            prices=dict(cls.PRICES), cash=25000.0)

    def test_pipeline_can_be_constructed(self):
        """Regression: OrderExecution.__init__ referenced BudgetManager
        without importing it, so the pipeline had never been instantiable."""
        from nifty100_adapter.risk.execution_pipeline import (
            OrderExecutionPipeline)
        pipeline = OrderExecutionPipeline()
        self.assertIsNotNone(pipeline.budget_manager)
        self.assertIsNotNone(pipeline.stop_target_engine)

    def test_plan_sizes_orders(self):
        self.assertTrue(self.plan["tradable"])
        self.assertGreater(len(self.plan["orders"]), 0)
        executable = [o for o in self.plan["orders"] if o["approved"]]
        self.assertGreater(len(executable), 0)
        for o in self.plan["orders"]:
            self.assertGreater(o["stop_loss"], 0)
            self.assertLess(o["stop_loss"], o["entry_price"])

    def test_plan_totals_match_orders(self):
        expected = sum(o["risk_at_stop"] for o in self.plan["orders"])
        self.assertAlmostEqual(self.plan["total_risk_at_stops"], expected, 3)

    def test_risk_stays_within_daily_limit(self):
        # every planned order's loss at stop must fit the per-trade cap
        for o in self.plan["orders"]:
            self.assertLessEqual(o["risk_at_stop"], 500.0 + 1e-9)

    def test_stop_and_target_come_from_exit_rules(self):
        orders = self.plan["orders"]
        self.assertTrue(any(o["target"] for o in orders))
        for o in orders:
            if o["target"]:
                self.assertGreater(o["target"], o["entry_price"])

    def test_execute_routes_approved_orders(self):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        with open("/dev/null", "w") if sys.platform != "win32" else \
                open("nul", "w") as devnull:
            import contextlib
            with contextlib.redirect_stdout(devnull):
                report = self.hub.execute_trading_plan(self.plan)
        approved = sum(1 for o in self.plan["orders"] if o["approved"])
        self.assertEqual(report["attempted"], approved)
        self.assertEqual(report["filled"], approved)
        self.assertEqual(report["rejected"], 0)

    def test_daily_limit_blocks_plan(self):
        from nifty100_adapter.strategy.execution_bridge import (
            StrategyExecutionBridge)
        bridge = StrategyExecutionBridge()
        bridge.budget.daily_trades_count = bridge.budget.rules.max_trades_per_day
        plan = bridge.build_plan(self.hub.strategy_candidates[:1],
                                 self.PRICES, 25000.0)
        self.assertFalse(plan.tradable)
        self.assertTrue(plan.blocked_reason)

    def test_bridge_respects_cash(self):
        from nifty100_adapter.strategy.execution_bridge import (
            StrategyExecutionBridge)
        bridge = StrategyExecutionBridge()
        plan = bridge.build_plan(self.hub.strategy_candidates[:2],
                                 self.PRICES, cash=2000.0)
        # with Rs 2,000 and a 10% buffer the bridge can barely fund anything
        for o in plan.orders:
            self.assertLessEqual(o.position_value, 1800.0 + 1e-9)


class ParameterValueStoreTests(unittest.TestCase):
    """The 48-parameter stores must record honest, fresh values."""

    @classmethod
    def setUpClass(cls):
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        cls.store = ParameterValueStore()

    def _bars(self, symbol, n=40, drift=0.002):
        import random
        rng = random.Random(hash(symbol) % 1000)
        price = 100.0
        out = []
        for _ in range(n):
            price *= 1 + drift + rng.gauss(0, 0.012)
            out.append({"symbol": symbol, "close": round(price, 2),
                        "volume": 100000})
        return out

    def test_record_and_read_back(self):
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        store = ParameterValueStore()
        store.record("price_momentum_weekly", "RELIANCE", 3.05,
                     "NSE Price History", observed=True)
        value = store.get("price_momentum_weekly", "RELIANCE")
        self.assertIsNotNone(value)
        self.assertEqual(value.value, 3.05)
        self.assertTrue(value.observed)
        self.assertEqual(store.usable("price_momentum_weekly", "RELIANCE"), 3.05)

    def test_unknown_symbol_returns_none(self):
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        store = ParameterValueStore()
        self.assertIsNone(store.usable("f_score", "RELIANCE"))
        self.assertIsNone(store.get("f_score", "RELIANCE"))

    def test_unavailable_is_reported_not_fabricated(self):
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        store = ParameterValueStore()
        store.mark_unavailable("f_score", "no feed configured")
        cov = store.coverage(["f_score"])
        self.assertEqual(cov["available_count"], 0)
        self.assertEqual(cov["missing_count"], 1)
        self.assertEqual(cov["reasons"]["f_score"], "no feed configured")

    def test_coverage_covers_all_48_catalogue_parameters(self):
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        store = ParameterValueStore()
        cov = store.coverage()
        self.assertEqual(cov["total_parameters"], 48)

    def test_stale_values_are_not_usable(self):
        from datetime import datetime, timedelta
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        store = ParameterValueStore()
        store.set_schedule("price_momentum_weekly", "weekly")
        old = (datetime.now() - timedelta(days=30)).isoformat()
        store.record("price_momentum_weekly", "RELIANCE", 5.0,
                     "NSE Price History", observed=True, as_of=old)
        self.assertIsNone(store.usable("price_momentum_weekly", "RELIANCE"))
        fresh = (datetime.now() - timedelta(days=2)).isoformat()
        store.record("price_momentum_weekly", "TCS", 4.0,
                     "NSE Price History", observed=True, as_of=fresh)
        self.assertEqual(store.usable("price_momentum_weekly", "TCS"), 4.0)


class PriceAdapterValueTests(unittest.TestCase):
    """Price-derived parameters must be observable without any network."""

    def test_fetch_from_supplied_bars_is_observed(self):
        import random
        from nifty100_adapter.data.nse_price_adapter import NSEPriceAdapter
        rng = random.Random(11)
        bars = []
        price = 100.0
        for _ in range(40):
            price *= 1 + 0.002 + rng.gauss(0, 0.012)
            bars.append({"symbol": "RELIANCE", "close": round(price, 2),
                         "volume": 100000})
        result = NSEPriceAdapter().fetch_parameter_values(
            ["RELIANCE"], bars_by_symbol={"RELIANCE": bars})
        self.assertIn("price_momentum_weekly", result["observed"])
        self.assertGreater(result["parameters"]["price_momentum_weekly"]["RELIANCE"],
                           0)

    def test_fetch_without_network_is_unavailable_not_fabricated(self):
        from nifty100_adapter.data.nse_price_adapter import NSEPriceAdapter
        result = NSEPriceAdapter().fetch_parameter_values(["RELIANCE"])
        # no aiohttp and no bars supplied: honest unavailability
        self.assertEqual(result["parameters"], {})


class PipelineCollectionTests(unittest.TestCase):
    """The data pipeline must produce values and honest coverage."""

    @staticmethod
    def _bars(symbol, n=40, drift=0.002, seed=7):
        import random
        rng = random.Random(seed)
        price = 100.0
        out = []
        for _ in range(n):
            price *= 1 + drift + rng.gauss(0, 0.012)
            out.append({"symbol": symbol, "close": round(price, 2),
                        "volume": int(1e5)})
        return out

    def test_collect_populates_store(self):
        from nifty100_adapter.data.pipeline_orchestrator import (
            collect_parameter_values)
        data = {"RELIANCE": self._bars("RELIANCE"),
                "TCS": self._bars("TCS", drift=0.004, seed=8)}
        result = collect_parameter_values(["RELIANCE", "TCS"],
                                          bars_by_symbol=data)
        store = result["store"]
        self.assertGreater(result["coverage"]["available_count"], 0)
        self.assertIsNotNone(
            store.usable("price_momentum_weekly", "RELIANCE"))

    def test_coverage_is_honest_about_unwired_feeds(self):
        from nifty100_adapter.data.pipeline_orchestrator import (
            collect_parameter_values)
        result = collect_parameter_values(["RELIANCE"])
        cov = result["coverage"]
        # fundamentals/legal/credit feeds are not installed: they must be
        # reported missing, never filled with a neutral default
        self.assertIn("f_score", cov["missing"])
        self.assertIn("legal_cases_directors", cov["missing"])
        self.assertLess(cov["coverage_pct"], 100.0)


class HubParameterValueTests(unittest.TestCase):
    """The hub must expose store-backed collection and coverage."""

    def test_hub_collect_and_coverage(self):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        hub = UniversalStrategyHub(HubConfig(llm_provider="openai"))
        hub.ingest_pkscreener_signals(["RELIANCE", "TCS"])
        result = hub.collect_parameter_values()
        self.assertEqual(result["coverage"]["total_parameters"], 48)

    def test_backtester_prefers_stored_values(self):
        from nifty100_adapter.backtest.sitrader_strategy_backtester import (
            StrategyBacktester)
        from nifty100_adapter.data.parameter_store import ParameterValueStore
        import random
        rng = random.Random(3)
        bars = []
        price = 100.0
        for _ in range(40):
            price *= 1 + 0.002 + rng.gauss(0, 0.012)
            bars.append({"symbol": "RELIANCE", "close": round(price, 2),
                         "volume": 100000})

        store = ParameterValueStore()
        store.set_schedule("price_momentum_weekly", "daily")
        store.record("price_momentum_weekly", "RELIANCE", 42.0,
                     "NSE Price History", observed=True)

        bt = StrategyBacktester(value_store=store)
        features = bt._features(bars, len(bars) - 1)
        # the stored, provenance-tracked value must win over on-bar derivation
        self.assertEqual(features["price_momentum_weekly"], 42.0)


class DatasetFeedTests(unittest.TestCase):
    """Caller-supplied datasets must extend coverage honestly."""

    def test_supplied_values_are_recorded_with_provenance(self):
        from nifty100_adapter.data.dataset_feed import DatasetFeed
        feed = DatasetFeed()
        result = feed.fetch_parameter_values(
            ["RELIANCE"], datasets={"RELIANCE": {"f_score": 8,
                                                 "altman_z_score": 3.4}})
        self.assertIn("f_score", result["observed"])
        self.assertEqual(result["parameters"]["f_score"]["RELIANCE"], 8.0)
        self.assertEqual(result["source"], "Caller-supplied dataset")

    def test_unsupplied_parameters_reported_unavailable(self):
        from nifty100_adapter.data.dataset_feed import DatasetFeed
        feed = DatasetFeed()
        result = feed.fetch_parameter_values(
            ["RELIANCE"], datasets={"RELIANCE": {"f_score": 8}})
        self.assertIn("swot_analytics", result["unavailable"])
        self.assertNotIn("swot_analytics", result["observed"])

    def test_unknown_keys_are_ignored_not_remapped(self):
        from nifty100_adapter.data.dataset_feed import DatasetFeed
        feed = DatasetFeed()
        result = feed.fetch_parameter_values(
            ["RELIANCE"], datasets={"RELIANCE": {"not_a_catalogue_key": 5}})
        self.assertEqual(result["observed"], [])
        self.assertEqual(result["parameters"], {})

    def test_pipeline_coverage_rises_with_datasets(self):
        from nifty100_adapter.data.pipeline_orchestrator import (
            collect_parameter_values)
        base = collect_parameter_values(["RELIANCE"])["coverage"]["available_count"]
        extra = collect_parameter_values(
            ["RELIANCE"],
            datasets={"RELIANCE": {"f_score": 8, "roe_trend": 18.0,
                                   "promoter_holding_pct": 50.0}}
        )["coverage"]["available_count"]
        self.assertGreater(extra, base)

    def test_values_expire_on_the_catalogue_schedule(self):
        from nifty100_adapter.data.dataset_feed import DatasetFeed
        feed = DatasetFeed()
        result = feed.fetch_parameter_values(
            ["RELIANCE"], datasets={"RELIANCE": {"f_score": 8}})
        # f_score refreshes quarterly per the catalogue
        self.assertEqual(result["schedules"]["f_score"], "quarterly")


class StateChecklistTests(unittest.TestCase):
    """The 08:30 checklist must be derived from real state."""

    @staticmethod
    def _session(**over):
        defaults = dict(
            connected=True, static_ip_verified=True, algo_id_registered=True,
            gates_passed={"backtest": True, "paper_trading": True,
                          "compliance": True, "risk": True, "capital": True},
            pilot_capital=25000.0, max_weekly_loss=5000.0, max_positions=10,
            kill_switch_active=False, weekly_loss_tracker=1200.0,
            llm_configuration_manager=None)
        defaults.update(over)
        return type("S", (), defaults)()

    def test_checklist_derives_from_budget_and_gates(self):
        from nifty100_adapter.risk.daily_checklist import DailyChecklist
        from nifty100_adapter.risk.budget_manager import BudgetManager
        budget = BudgetManager()
        budget.record_trade("RELIANCE", -300.0, 5, 2500.0)
        cl = DailyChecklist.build_from_state(session=self._session(),
                                            budget=budget)
        self.assertEqual(cl["total_items"], 14)
        item = next(i for i in cl["items"] if "Weekly loss" in i["name"])
        self.assertEqual(item["status"], "PASS")
        gate = next(i for i in cl["items"] if "compliance gates" in i["name"])
        self.assertEqual(gate["status"], "PASS")

    def test_kill_switch_fails_the_checklist(self):
        from nifty100_adapter.risk.daily_checklist import DailyChecklist
        from nifty100_adapter.risk.kill_switch import KillSwitchManager
        ks = KillSwitchManager()
        ks.trigger("test", triggered_by="manual")
        cl = DailyChecklist.build_from_state(session=self._session(),
                                            kill_switch=ks)
        item = next(i for i in cl["items"] if "Kill switch" in i["name"])
        self.assertEqual(item["status"], "FAIL")
        self.assertFalse(cl["summary"]["ready_to_trade"])

    def test_legal_check_is_not_assumed_true(self):
        from nifty100_adapter.risk.daily_checklist import DailyChecklist
        cl = DailyChecklist.build_from_state(session=self._session())
        item = next(i for i in cl["items"] if "Legal" in i["name"])
        self.assertEqual(item["status"], "FAIL")
        self.assertFalse(cl["summary"]["ready_to_trade"])


class ArenaReviewTests(unittest.TestCase):
    """CLAUDE.md's Arena workflow: fixed constraints, labelled results."""

    @staticmethod
    def _bars(symbol, n=320, drift=0.002, seed=31):
        import random
        rng = random.Random(seed)
        price = 100.0
        out = []
        for _ in range(n):
            price *= 1 + drift + rng.gauss(0, 0.012)
            out.append({"symbol": symbol, "close": round(price, 2),
                        "volume": int(1e5)})
        return out

    @classmethod
    def _data(cls):
        return {"RELIANCE": cls._bars("RELIANCE"),
                "TCS": cls._bars("TCS", drift=0.004, seed=32)}

    def _hub_with_candidates(self):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        hub = UniversalStrategyHub(HubConfig(llm_provider="openai",
                                            max_positions=2))
        hub.ingest_ma_crossovers(["MA5_MA10", "MA20_MA50", "MA50_MA200"])
        return hub

    def test_submission_must_total_100(self):
        from nifty100_adapter.research.arena import (
            ArenaReview, ArenaStrategy, DEFAULT_CONSTRAINTS)
        review = ArenaReview(DEFAULT_CONSTRAINTS)
        with self.assertRaises(ValueError):
            review.add_strategy(ArenaStrategy(
                name="bad", source="test",
                parameter_weights={"price_momentum_weekly": 5}))

    def test_metrics_are_measured_and_ranked(self):
        hub = self._hub_with_candidates()
        hub.select_strategies(min_confidence=40, max_strategies=3)
        report = hub.arena_review(price_data=self._data())
        measured = [r for r in report["ranking"] if r["label"] == "measured"]
        self.assertEqual(len(measured), 3)
        self.assertEqual([r["rank"] for r in report["ranking"]],
                         list(range(1, 4)))
        self.assertEqual(report["unlabelled_results"], [])

    def test_no_data_is_labelled_not_scored_zero(self):
        hub = self._hub_with_candidates()
        report = hub.arena_review(price_data=None)
        self.assertTrue(all(r["label"] == "unmeasured"
                            for r in report["ranking"]))
        self.assertEqual(len(report["unlabelled_results"]), 3)
        for r in report["ranking"]:
            self.assertTrue(r["notes"])

    def test_weights_change_the_score(self):
        """Weight differences must change the score at a fixed bar."""
        from nifty100_adapter.backtest.sitrader_strategy_backtester import (
            StrategyBacktester)
        from nifty100_adapter.strategy import get_ma_strategy_config
        data = self._data()
        bars = data["RELIANCE"]
        bt = StrategyBacktester(capital=25000.0, top_n=1)
        feats = bt._features(bars, len(bars) - 1)
        score_a = bt._score(get_ma_strategy_config("MA5_MA10")["parameter_weights"], feats)
        score_b = bt._score(get_ma_strategy_config("MA20_MA50")["parameter_weights"], feats)
        self.assertNotEqual(score_a, score_b)

    def test_basket_larger_than_universe_gives_tied_rankings(self):
        """When every stock fits in the basket, weights cannot change the
        holdings, so tied rankings are correct behaviour and must be reported
        as measured rather than hidden."""
        hub = self._hub_with_candidates()
        report = hub.arena_review(price_data=self._data())
        scores = [r["metrics"].get("avg_trade") for r in report["ranking"]]
        self.assertEqual(len(set(scores)), 1)
        for r in report["ranking"]:
            self.assertEqual(r["label"], "measured")

    def test_holdout_does_not_drive_selection(self):
        hub = self._hub_with_candidates()
        data = self._data()
        holdout = {"RELIANCE": self._bars("RELIANCE", drift=0.003, seed=33),
                   "TCS": self._bars("TCS", drift=0.001, seed=34)}
        report = hub.arena_review(price_data=data, holdout_data=holdout)
        hold = report["holdout"]
        self.assertTrue(hold["holdout_compared"])
        self.assertEqual(hold["selection_used"], "evaluation window only")
        for c in hold["comparisons"]:
            self.assertIn("risks", c)

    def test_reports_have_no_promotion_authority(self):
        hub = self._hub_with_candidates()
        report = hub.arena_review(price_data=self._data())
        self.assertIn("read-only", report["promotion_policy"])
        self.assertEqual(hub.paper_trading_strategies, [])

    def test_constraints_are_identical_for_every_solver(self):
        from nifty100_adapter.research.arena import (
            ArenaReview, ArenaStrategy, DEFAULT_CONSTRAINTS)
        review = ArenaReview(DEFAULT_CONSTRAINTS)
        review.add_strategy(ArenaStrategy(
            name="a", source="test",
            parameter_weights={"price_momentum_weekly": 100},
            decision_evidence={"custom": "x"}))
        review.add_strategy(ArenaStrategy(
            name="b", source="test",
            parameter_weights={"price_momentum_weekly": 100},
            decision_evidence={"custom": "y"}))
        report = review.report(None)
        # both entries carry the catalogue snapshot in their decision evidence
        snapshots = {s["decision_evidence"]["parameter_catalogue_size"]
                     for s in report["submissions"]}
        self.assertEqual(snapshots, {48})
        self.assertEqual(report["constraints"]["capital"], 25000.0)
        self.assertEqual(report["constraints"]["cost_pct"], 0.38)


class ObservabilityTests(unittest.TestCase):
    """Every run must leave a durable, enumerable, honest artefact."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="sitrader_obs_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_report_written_and_loadable(self):
        from nifty100_adapter.observability import ReportWriter
        writer = ReportWriter(records_dir=self.tmp)
        path = writer.emit("arena", {"constraints": {"capital": 25000},
                                    "metrics": {"x": 1},
                                    "labels": {"unmeasured": ["a"]}})
        self.assertTrue(os.path.exists(path))
        loaded = ReportWriter(records_dir=self.tmp).load_report(
            json.load(open(path))["run_id"], "arena")
        self.assertEqual(loaded["kind"], "arena")
        self.assertEqual(loaded["labels"]["unmeasured"], ["a"])

    def test_index_enumerates_runs(self):
        from nifty100_adapter.observability import ReportWriter
        writer = ReportWriter(records_dir=self.tmp)
        writer.emit("weekly", {"metrics": {"n": 1}})
        writer.emit("weekly", {"metrics": {"n": 2}})
        entries = ReportWriter(records_dir=self.tmp).list_reports(kind="weekly")
        self.assertEqual(len(entries), 2)
        self.assertEqual({e["kind"] for e in entries}, {"weekly"})

    def test_runs_are_append_only(self):
        from nifty100_adapter.observability import ReportWriter
        writer = ReportWriter(records_dir=self.tmp)
        first = writer.emit("weekly", {"metrics": {"n": 1}})
        snapshot = open(first).read()
        writer.emit("weekly", {"metrics": {"n": 2}})
        # the first artefact must not have been mutated by the second run
        self.assertEqual(open(first).read(), snapshot)

    def test_hub_review_emits_report(self):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        hub = UniversalStrategyHub(HubConfig(
            llm_provider="openai", max_positions=2, records_dir=self.tmp))
        hub.ingest_ma_crossovers(["MA5_MA10", "MA20_MA50"])
        report = hub.arena_review(price_data=None)
        self.assertTrue(os.path.exists(report["report_path"]))
        loaded = json.load(open(report["report_path"]))
        self.assertEqual(loaded["kind"], "arena")
        # unmeasured results must be recorded as unmeasured, never scored
        self.assertEqual(len(loaded["labels"]["unmeasured"]), 2)
        self.assertEqual(loaded["labels"]["measured"], [])

    def test_no_records_dir_means_no_artefact(self):
        from nifty100_adapter.strategy import UniversalStrategyHub, HubConfig
        hub = UniversalStrategyHub(HubConfig(llm_provider="openai",
                                            max_positions=2))
        hub.ingest_ma_crossovers(["MA5_MA10"])
        report = hub.arena_review(price_data=None)
        self.assertNotIn("report_path", report)


if __name__ == "__main__":
    unittest.main()
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


if __name__ == "__main__":
    unittest.main()
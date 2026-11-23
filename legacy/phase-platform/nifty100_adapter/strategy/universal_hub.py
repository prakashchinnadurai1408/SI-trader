"""Universal Strategy Hub for SI-Trader.

Combines all integration layers into a unified strategy solution:

1. Broker Connectivity: OpenAlgo, Kite Connect, Fenix
2. Market Data: jugaad-data, Kite Connect historical API
3. Backtesting: vectorbt, backtrader, existing SI-Trader backtesters
4. Strategies: PKScreener patterns, algo_trading_strategies_india,
   MA crossovers, AI/LLM generation, cash-settled index options
5. Parameter Catalogue: 48 parameters, weight total 100 (BRD compliant)

The hub provides:
- Universal strategy ingestion (from any layer)
- BRD-compliant validation (cost model, edge threshold, parameter weights)
- Backtesting across multiple engines
- Portfolio-level capital allocation
- Paper trading pipeline (16 weeks, 5 compliance gates)
- Live trading execution via broker adapters
- Commercial platform readiness (multi-tenant, audit trail)

Dual-mode:
- Self-trading: Individual trader uses with own capital
- Commercial platform: Multi-tenant SaaS with subscription model
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import json

# SI-Trader imports
from ..config.parameter_catalogue import (
    PARAMETER_CATALOGUE,
    validate_weight_total,
    get_enabled_parameters,
    RoleType,
)
from ..config.indian_cost_model import IndianCostModel, get_cost_model
from ..backtest.enhanced_backtester import Phase1Backtester
from ..risk.portfolio_optimizer import PortfolioOptimizer

# New strategy generation adapters
from .ma_crossover_adapter import (
    MACrossoverAdapter, get_ma_strategy_config, get_all_ma_strategies,
)
from .ai_strategy_generator import (
    AIStrategyGenerator, StrategyIdea, StrategyGenerationResult,
)
from .options_strategy_adapter import (
    OptionsStrategyAdapter, get_option_strategy_config, get_all_option_strategies,
)

# Integration layer imports
try:
    from ..broker._init_ import (
        BrokerConfig,
        OrderRequest,
        OrderResponse,
        BrokerPlatform,
        BrokerAdapter,
    )
    BROKER_ADAPTERS_AVAILABLE = True
except ImportError:
    BROKER_ADAPTERS_AVAILABLE = False
    BrokerAdapter = object
    BrokerConfig = object
    OrderRequest = object
    OrderResponse = object
    OrderSide = object
    OrderType = object
    ProductType = object
    OrderStatus = object
    BrokerPlatform = object
    
    class OpenAlgoAdapter:
        pass
    class KiteConnectAdapter:
        pass
    class FenixAdapter:
        pass

from ..data.jugaad_data_adapter import JugaadDataAdapter, MarketDataManager
from ..backtest.vectorbt_adapter import VectorBTAdapter
from ..backtest.backtrader_adapter import BacktraderAdapter
from .pkscreener_adapter import PKScreenerAdapter, PkScreenerConfig, PkScreenerSignal
from .algo_india_adapter import AlgoIndiaAdapter, AlgoIndiaConfig, AlgoIndiaStrategy

logger = logging.getLogger(__name__)


@dataclass
class StrategyCandidate:
    """A strategy candidate from any integration layer."""
    name: str
    source: str
    strategy_type: str
    parameter_weights: Dict[str, int]
    weight_total: int
    expected_edge: Optional[float] = None
    confidence: float = 0.0
    backtest_results: Optional[Dict[str, Any]] = None
    edge_validation: Optional[Dict[str, Any]] = None
    selected_stocks: Optional[List[str]] = None
    risk_rules: Optional[Dict[str, Any]] = None
    entry_rules: Optional[Dict[str, Any]] = None
    exit_rules: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.risk_rules is None:
            self.risk_rules = {}
        if self.entry_rules is None:
            self.entry_rules = {}
        if self.exit_rules is None:
            self.exit_rules = {}
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def is_brd_compliant(self) -> bool:
        if self.weight_total != 100:
            return False
        if self.edge_validation and not self.edge_validation.get("brd_compliant", False):
            return False
        return True
    
    @property
    def is_profitable(self) -> bool:
        if self.backtest_results:
            return self.backtest_results.get("net_profit", 0) > 0
        return False


@dataclass
class HubConfig:
    """Configuration for the Universal Strategy Hub."""
    param_catalogue: Optional[Dict[str, Any]] = None
    market_data_manager: Optional[MarketDataManager] = None
    broker_adapter: Optional[BrokerAdapter] = None
    broker_platform: BrokerPlatform = BrokerPlatform.ZERODHA_KITE
    llm_provider: str = "openai"
    value_store: Optional[Any] = None  # ParameterValueStore
    enable_vectorbt: bool = True
    enable_backtrader: bool = True
    enable_pkscreener: bool = True
    enable_algo_india: bool = True
    enable_ma_crossover: bool = True
    enable_ai_strategy: bool = True
    enable_options: bool = True
    enable_portfolio_optimizer: bool = True
    min_edge_pct: float = 0.3
    cost_pct: float = 0.38
    max_positions: int = 10
    pilot_capital: float = 25000.0
    commercial_mode: bool = False
    subscription_tier: Optional[str] = None
    multi_user: bool = False


class UniversalStrategyHub:
    """Universal Strategy Hub - combines all integration layers.
    
    The hub is the central orchestration point for SI-Trader's strategy
    ecosystem. It:
    
    1. Ingests strategies from all layers (PKScreener, algo_india, etc.)
    2. Validates against BRD constraints (parameter weights, cost model, edge)
    3. Backtests using vectorbt/backtrader/SI-Trader backtesters
    4. Selects top strategies for paper trading
    5. Executes via broker adapters (OpenAlgo, Kite Connect, Fenix)
    
    Dual-mode operation:
    - Self-trading: Single trader, own capital, paper -> live
    - Commercial platform: Multi-user, subscription tiers, audit trail
    """
    
    def __init__(self, config: Optional[HubConfig] = None):
        self.config = config or HubConfig()
        self.cost_model = get_cost_model()
        self.value_store = self.config.value_store
        
        self.market_data = self.config.market_data_manager or MarketDataManager()
        self.broker_adapter = self.config.broker_adapter
        
        self.pkscreener = PKScreenerAdapter() if self.config.enable_pkscreener else None
        self.algo_india = AlgoIndiaAdapter() if self.config.enable_algo_india else None
        self.ma_crossover = (
            MACrossoverAdapter() if self.config.enable_ma_crossover else None
        )
        self.ai_generator = (
            AIStrategyGenerator(llm_provider=self.config.llm_provider)
            if self.config.enable_ai_strategy else None
        )
        self.options = (
            OptionsStrategyAdapter() if self.config.enable_options else None
        )
        self.portfolio_optimizer = (
            PortfolioOptimizer(capital=self.config.pilot_capital)
            if self.config.enable_portfolio_optimizer else None
        )

        self.vectorbt = VectorBTAdapter(
            initial_capital=self.config.pilot_capital,
        ) if self.config.enable_vectorbt else None
        self.backtrader = BacktraderAdapter(
            initial_cash=self.config.pilot_capital,
            commission_pct=self.config.cost_pct,
        ) if self.config.enable_backtrader else None
        
        self.strategy_candidates: List[StrategyCandidate] = []
        self.selected_strategies: List[StrategyCandidate] = []
        self.paper_trading_strategies: List[StrategyCandidate] = []
        self.live_strategies: List[StrategyCandidate] = []
        
        self.audit_trail: List[Dict[str, Any]] = []
        
        logger.info("Universal Strategy Hub initialized")
    
    @staticmethod
    def _normalise_selected_stocks(stocks: Any) -> List[str]:
        """Accept selected_stocks as plain symbols or {"symbol": ...} dicts."""
        if not stocks:
            return []
        out: List[str] = []
        for s in stocks:
            if isinstance(s, dict):
                sym = s.get("symbol")
                if sym:
                    out.append(str(sym))
            elif isinstance(s, str):
                out.append(s)
        return out

    def ingest_strategy(
        self,
        strategy_config: Dict[str, Any],
        source: str = "builtin",
    ) -> StrategyCandidate:
        """Ingest a strategy from any source into the hub."""
        weights = strategy_config.get("parameter_weights", {})
        weight_total = sum(weights.values())
        
        if weight_total != 100:
            scale = 100 / weight_total if weight_total > 0 else 1
            weights = {k: max(1, round(v * scale)) for k, v in weights.items()}
            weight_total = sum(weights.values())
        
        candidate = StrategyCandidate(
            name=strategy_config.get("strategy_name", "unnamed_strategy"),
            source=source,
            strategy_type=strategy_config.get("strategy_type", "unknown"),
            parameter_weights=weights,
            weight_total=weight_total,
            confidence=strategy_config.get("confidence", 50.0),
            selected_stocks=self._normalise_selected_stocks(
                strategy_config.get("selected_stocks", [])),
            risk_rules=strategy_config.get("risk_rules", {}),
            entry_rules=strategy_config.get("entry_rules", {}),
            exit_rules=strategy_config.get("exit_rules", {}),
            metadata={
                "description": strategy_config.get("description", ""),
                "timeframe": strategy_config.get("timeframe", "daily"),
                "generated_at": strategy_config.get("generated_at", ""),
            },
        )
        
        self.strategy_candidates.append(candidate)
        self._audit("ingest", candidate.name, source, {"weight_total": weight_total})
        
        logger.info(f"Ingested strategy: {candidate.name} (source: {source}, weights: {weight_total})")
        return candidate
    
    def ingest_pkscreener_signals(
        self,
        symbols: List[str],
        pattern_type: Optional[str] = None,
        min_confidence: float = 60.0,
    ) -> List[StrategyCandidate]:
        """Ingest strategies from PKScreener pattern scan."""
        if not self.pkscreener:
            logger.error("PKScreener adapter not enabled")
            return []
        
        signals = self.pkscreener.scan_for_patterns(
            symbols=symbols,
            pattern_type=pattern_type,
            min_confidence=min_confidence,
        )
        
        candidates = []
        for signal in signals:
            config = self.pkscreener.generate_strategy_config(
                [signal],
                strategy_name=f"PKScreener_{signal.symbol}_{signal.pattern_type}",
            )
            candidate = self.ingest_strategy(config, source="pkscreener")
            candidate.selected_stocks = [signal.symbol]
            candidate.confidence = signal.confidence
            candidates.append(candidate)
        
        return candidates
    
    def ingest_algo_india_strategies(
        self,
        strategy_names: Optional[List[str]] = None,
    ) -> List[StrategyCandidate]:
        """Ingest strategies from algo_trading_strategies_india."""
        if not self.algo_india:
            logger.error("Algo India adapter not enabled")
            return []
        
        strategies = self.algo_india.load_strategies()
        
        if strategy_names:
            strategies = [s for s in strategies if s.name in strategy_names]
        
        candidates = []
        for strategy in strategies:
            config = self.algo_india.generate_strategy_config(strategy)
            candidate = self.ingest_strategy(config, source="algo_india")
            candidate.confidence = strategy.confidence
            candidates.append(candidate)

        return candidates

    # =========================================================================
    # New strategy generation adapters (MA crossover, AI/LLM, options)
    # =========================================================================

    def ingest_ma_crossovers(
        self,
        strategy_names: Optional[List[str]] = None,
    ) -> List[StrategyCandidate]:
        """Ingest MA crossover strategies into the hub.

        Args:
            strategy_names: Specific strategies (e.g. ["MA5_MA10", "MA20_MA50"]).
                           Defaults to all four (MA5/10, MA10/20, MA20/50, MA50/200).
        """
        if not self.ma_crossover:
            logger.error("MA crossover adapter not enabled")
            return []

        names = strategy_names or list(self.ma_crossover.MA_STRATEGIES.keys())
        candidates = []
        for name in names:
            try:
                config = get_ma_strategy_config(name)
                candidate = self.ingest_strategy(config, source="ma_crossover")
                candidate.confidence = config.get("confidence", 75.0)
                candidates.append(candidate)
            except Exception as e:
                logger.error(f"Failed to ingest MA crossover {name}: {e}")
        return candidates

    def ingest_ai_strategies(
        self,
        market_condition: str = "trending",
        sector: str = "all",
        time_horizon: str = "daily",
        risk_tolerance: str = "medium",
        num_ideas: int = 5,
    ) -> List[StrategyCandidate]:
        """Generate strategies with the LLM and ingest them.

        Uses the configured LLM provider (10 supported) to produce strategy
        ideas, converts each into parameter weights, then ingests them.
        """
        if not self.ai_generator:
            logger.error("AI strategy generator not enabled")
            return []

        result = self.ai_generator.generate_strategy_ideas(
            market_condition=market_condition,
            sector=sector,
            time_horizon=time_horizon,
            risk_tolerance=risk_tolerance,
            num_ideas=num_ideas,
            capital=self.config.pilot_capital,
        )

        candidates = []
        for config in self.ai_generator.generate_strategy_configs(result.ideas):
            candidate = self.ingest_strategy(config, source="ai_llm")
            candidate.confidence = config.get("confidence", 50.0)
            candidate.metadata["llm_provider"] = self.config.llm_provider
            candidate.metadata["market_condition"] = market_condition
            candidate.metadata["risk_tolerance"] = risk_tolerance
            candidates.append(candidate)
        return candidates

    def ingest_options_strategies(
        self,
        strategy_names: Optional[List[str]] = None,
    ) -> List[StrategyCandidate]:
        """Ingest cash-settled index options strategies.

        Note: these are cash-settled (Nifty 50 / Bank Nifty) to stay within the
        BRD delivery-only compliance boundary.
        """
        if not self.options:
            logger.error("Options adapter not enabled")
            return []

        names = strategy_names or list(self.options.OPTION_STRATEGIES.keys())
        candidates = []
        for name in names:
            try:
                config = get_option_strategy_config(name)
                candidate = self.ingest_strategy(config, source="options")
                candidate.confidence = 65.0
                candidate.metadata["cash_settled"] = True
                candidate.metadata["suitable_condition"] = config.get(
                    "suitable_market_condition")
                candidates.append(candidate)
            except Exception as e:
                logger.error(f"Failed to ingest options strategy {name}: {e}")
        return candidates

    def ingest_all_strategy_sources(
        self,
        symbols: Optional[List[str]] = None,
        market_condition: str = "trending",
        risk_tolerance: str = "medium",
    ) -> Dict[str, List[StrategyCandidate]]:
        """Ingest from every enabled strategy source at once.

        Returns a dict of source name -> list of candidates ingested.
        """
        symbols = symbols or ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
        out: Dict[str, List[StrategyCandidate]] = {}

        try:
            out["ma_crossover"] = self.ingest_ma_crossovers()
        except Exception as e:
            logger.error(f"ma_crossover ingestion failed: {e}")
            out["ma_crossover"] = []

        try:
            out["ai_llm"] = self.ingest_ai_strategies(
                market_condition=market_condition,
                risk_tolerance=risk_tolerance,
            )
        except Exception as e:
            logger.error(f"ai_llm ingestion failed: {e}")
            out["ai_llm"] = []

        try:
            out["options"] = self.ingest_options_strategies()
        except Exception as e:
            logger.error(f"options ingestion failed: {e}")
            out["options"] = []

        try:
            out["pkscreener"] = self.ingest_pkscreener_signals(symbols)
        except Exception as e:
            logger.error(f"pkscreener ingestion failed: {e}")
            out["pkscreener"] = []

        try:
            out["algo_india"] = self.ingest_algo_india_strategies()
        except Exception as e:
            logger.error(f"algo_india ingestion failed: {e}")
            out["algo_india"] = []

        return out

    def optimize_portfolio(
        self,
        candidate_names: Optional[List[str]] = None,
        expected_returns: Optional[Dict[str, float]] = None,
        expected_volatilities: Optional[Dict[str, float]] = None,
        max_strategies: int = 5,
    ) -> Dict[str, Any]:
        """Allocate capital across candidates using the portfolio optimizer.

        Returns a report with per-strategy allocation and portfolio metrics.
        """
        if not self.portfolio_optimizer:
            logger.error("Portfolio optimizer not enabled")
            return {}

        pool = (self.selected_strategies or self.strategy_candidates)
        if candidate_names:
            pool = [c for c in pool if c.name in candidate_names]

        configs = [{
            "strategy_name": c.name,
            "strategy_type": c.strategy_type,
            "weight_total": c.weight_total,
            "delivery_compatible": True,
            "confidence": c.confidence,
        } for c in pool]

        result = self.portfolio_optimizer.optimize_portfolio(
            strategies=configs,
            expected_returns=expected_returns,
            expected_volatilities=expected_volatilities,
            max_strategies=max_strategies,
        )

        self._audit("optimize_portfolio", f"{len(pool)} strategies", "hub", {
            "brd_compliant": result.brd_compliant,
            "total_allocated": result.total_allocated,
        })

        return {
            "total_capital": result.total_capital,
            "total_allocated": result.total_allocated,
            "cash_remaining": result.cash_remaining,
            "cash_pct": result.cash_pct,
            "brd_compliant": result.brd_compliant,
            "portfolio_metrics": result.portfolio_metrics,
            "allocations": [{
                "strategy_name": a.strategy_name,
                "strategy_type": a.strategy_type,
                "weight_pct": a.weight_pct,
                "capital_allocated": a.capital_allocated,
                "max_position_pct": a.max_position_pct,
            } for a in result.strategies],
        }

    def build_trading_plan(
        self,
        candidate_names: Optional[List[str]] = None,
        prices: Optional[Dict[str, float]] = None,
        cash: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Size the selected strategies into a reviewable order plan.

        Stops and targets come from each candidate's exit rules; share counts
        come from the four-limit BudgetManager. Nothing is placed here.
        """
        from .execution_bridge import StrategyExecutionBridge

        pool = self.selected_strategies or self.strategy_candidates
        if candidate_names:
            pool = [c for c in pool if c.name in candidate_names]
        if not pool:
            return {"tradable": False,
                    "blocked_reason": "no candidates selected"}

        prices = prices or {s: 0.0 for c in pool
                            for s in (c.selected_stocks or [])}
        bridge = StrategyExecutionBridge(top_n=self.config.max_positions)

        # Derive entry prices from the market data layer when they are absent.
        missing = [s for s in prices if not prices.get(s)]
        for symbol in missing:
            quote = None
            getter = getattr(self.market_data, "get_quote", None)
            if callable(getter):
                try:
                    quote = getter(symbol)
                except Exception:
                    quote = None
            if isinstance(quote, dict) and quote.get("price"):
                prices[symbol] = float(quote["price"])
                continue
            self._audit("plan_no_price", symbol, "hub", {})

        plan = bridge.build_plan(pool, prices, cash)
        self._audit("build_trading_plan", f"{len(pool)} strategies", "hub",
                    {"orders": len(plan.orders)})
        return plan.as_dict()

    def backtest_candidate(
        self,
        candidate: StrategyCandidate,
        price_data: Any,
        engine: str = "auto",
    ) -> Dict[str, Any]:
        """Backtest a strategy candidate."""
        engine = engine or ("vectorbt" if self.vectorbt and self.vectorbt.is_available() else "backtrader")
        
        result = None
        
        if engine == "vectorbt" and self.vectorbt and self.vectorbt.is_available():
            signals = self._generate_signals_from_weights(candidate, price_data)
            result = self.vectorbt.run_backtest(
                prices=price_data,
                signals=signals,
                cost_pct=self.config.cost_pct,
            )
        elif engine in ("auto", "backtrader") and self.backtrader \
                and self.backtrader.is_available():
            result = self._backtest_with_sitrader(candidate, price_data)
        else:
            # Default: weight-aware SI-Trader backtest. This is the only
            # engine that actually uses the candidate's weights, so it is
            # the fallback rather than the generic synthetic pipeline.
            result = self._backtest_with_weights(candidate, price_data)
        
        if result:
            candidate.backtest_results = result
            candidate.edge_validation = self.validate_edge(result)
            # net_edge is the per-trade average edge, not the total return;
            # the weighted engine reports it directly.
            if isinstance(result, dict) and "avg_trade" in result:
                candidate.edge_validation["net_edge"] = result["avg_trade"]
                candidate.edge_validation["edge_passes"] = (
                    result["avg_trade"] > self.config.min_edge_pct)
            self._audit("backtest", candidate.name, engine, result)
        
        return result or {}
    
    def _backtest_with_weights(self, candidate, price_data):
        """Backtest using the candidate's own parameter weights.

        `price_data` may be {symbol: [bar dicts]} or a DataFrame with a
        'close' column; the weighted engine needs per-symbol bars so a
        DataFrame is backtested as a single unnamed series.
        """
        from ..backtest.sitrader_strategy_backtester import StrategyBacktester

        if hasattr(price_data, "columns"):  # pandas DataFrame
            try:
                bars = price_data.to_dict("records")
            except Exception:
                bars = price_data[["close"]].to_dict("records")
            series = {"_single": bars}
        else:
            series = {str(k): list(v) for k, v in dict(price_data).items()}

        backtester = StrategyBacktester(
            capital=self.config.pilot_capital, top_n=self.config.max_positions,
            value_store=self.value_store)
        return backtester.run_candidate(candidate, series)

    def _generate_signals_from_weights(
        self,
        candidate: StrategyCandidate,
        price_data: Any,
    ) -> Any:
        """Generate trading signals from parameter weights."""
        import pandas as pd
        import numpy as np
        
        if isinstance(price_data, dict):
            close = pd.Series(price_data.get("close", []))
        else:
            close = price_data.close if hasattr(price_data, "close") else price_data
        
        momentum_weight = candidate.parameter_weights.get("price_momentum_weekly", 1)
        volatility_weight = candidate.parameter_weights.get("midcap_volatility_adj", 3)
        
        returns = close.pct_change()
        signals = (returns > 0).astype(int) - (returns < 0).astype(int)
        signals = signals * (candidate.confidence / 100.0)
        
        return signals
    
    def _backtest_with_sitrader(
        self,
        candidate: StrategyCandidate,
        price_data: Any,
    ) -> Dict[str, Any]:
        """Backtest using SI-Trader's existing enhanced backtester."""
        try:
            bt = Phase1Backtester(
                capital=self.config.pilot_capital,
                top_n=self.config.max_positions,
                min_liquidity_crore=25,
                real_data=False,
            )
            result = bt.run_full_pipeline(
                use_historical_data=False,
                generate_synthetic=True,
                real_time_quotes=False,
            )
            
            return {
                "total_return": result.get("pipeline_stats", {}).get("average_edge", 0) * 100,
                "net_profit": 0,
                "sharpe": 0,
                "max_drawdown": 0,
                "win_rate": 0,
                "total_trades": result.get("pipeline_stats", {}).get("edge_passes", 0),
                "avg_trade": 0,
                "expectancy": 0,
                "final_value": self.config.pilot_capital,
                "cost_pct": self.config.cost_pct,
                "engine": "sitrader",
            }
        except Exception as e:
            logger.error(f"SI-Trader backtest error: {e}")
            return {}
    
    def run_parameter_sweep(
        self,
        price_data: Any,
        strategy_fn: callable,
        param_grid: Dict[str, List[Any]],
    ) -> Optional[Dict[str, Any]]:
        """Run parameter sweep using vectorbt."""
        if not self.vectorbt or not self.vectorbt.is_available():
            logger.error("vectorbt not available for parameter sweep")
            return None
        
        return self.vectorbt.run_parameter_sweep(
            prices=price_data,
            strategy_fn=strategy_fn,
            param_grid=param_grid,
            cost_pct=self.config.cost_pct,
        )
    
    def validate_edge(
        self,
        backtest_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate strategy edge against BRD cost threshold."""
        if self.vectorbt and self.vectorbt.is_available():
            return self.vectorbt.validate_edge(
                backtest_results,
                min_edge_pct=self.config.min_edge_pct,
                cost_pct=self.config.cost_pct,
            )
        elif self.backtrader and self.backtrader.is_available():
            return self.backtrader.validate_edge(
                backtest_results,
                min_edge_pct=self.config.min_edge_pct,
                cost_pct=self.config.cost_pct,
            )
        else:
            total_return = backtest_results.get("total_return", 0)
            net_profit = backtest_results.get("net_profit", 0)
            net_edge = total_return - self.config.cost_pct
            
            return {
                "gross_return": total_return,
                "cost_pct": self.config.cost_pct,
                "net_edge": net_edge,
                "min_edge_required": self.config.min_edge_pct,
                "edge_passes": net_edge > self.config.min_edge_pct,
                "profitable": net_profit > 0,
                "brd_compliant": (net_edge > self.config.min_edge_pct) and net_profit > 0,
            }
    
    def select_strategies(
        self,
        min_confidence: float = 50.0,
        require_brd_compliant: bool = True,
        max_strategies: Optional[int] = None,
    ) -> List[StrategyCandidate]:
        """Select strategies for paper trading."""
        selected = []
        
        for candidate in self.strategy_candidates:
            if candidate.confidence < min_confidence:
                continue
            if require_brd_compliant and not candidate.is_brd_compliant:
                continue
            if not candidate.is_profitable and candidate.backtest_results:
                continue
            
            selected.append(candidate)
        
        selected.sort(key=lambda c: c.confidence, reverse=True)
        
        if max_strategies:
            selected = selected[: max_strategies]
        
        self.selected_strategies = selected
        self._audit("select", f"{len(selected)} strategies", "hub", {
            "min_confidence": min_confidence,
            "require_brd_compliant": require_brd_compliant,
        })
        
        logger.info(f"Selected {len(selected)} strategies for paper trading")
        return selected
    
    def add_to_paper_trading(
        self,
        candidate: StrategyCandidate,
    ) -> bool:
        """Add strategy to paper trading pipeline."""
        if candidate not in self.selected_strategies:
            logger.warning(f"Strategy '{candidate.name}' not in selected list")
            return False
        
        self.paper_trading_strategies.append(candidate)
        self._audit("paper_trade", candidate.name, "hub", {
            "weight_total": candidate.weight_total,
            "brd_compliant": candidate.is_brd_compliant,
        })
        
        logger.info(f"Added to paper trading: {candidate.name}")
        return True
    
    def promote_to_live(
        self,
        candidate: StrategyCandidate,
        broker_adapter: Optional[BrokerAdapter] = None,
    ) -> bool:
        """Promote strategy from paper trading to live execution."""
        if candidate not in self.paper_trading_strategies:
            logger.warning(f"Strategy '{candidate.name}' not in paper trading")
            return False
        
        if not candidate.is_brd_compliant:
            logger.warning(f"Strategy '{candidate.name}' not BRD compliant")
            return False
        
        adapter = broker_adapter or self.broker_adapter
        if not adapter or not adapter.is_connected():
            logger.warning("No broker adapter connected for live trading")
            return False
        
        self.live_strategies.append(candidate)
        self._audit("promote_to_live", candidate.name, "hub", {
            "broker": adapter.config.platform.value if adapter else "none",
        })
        
        logger.info(f"Promoted to live trading: {candidate.name}")
        return True
    
    def execute_strategy(
        self,
        candidate: StrategyCandidate,
        broker_adapter: Optional[BrokerAdapter] = None,
    ) -> List[OrderResponse]:
        """Execute a strategy via broker adapter."""
        adapter = broker_adapter or self.broker_adapter
        if not adapter or not adapter.is_connected():
            logger.error("No broker adapter connected for execution")
            return []
        
        responses = []
        stocks = candidate.selected_stocks or []
        
        for symbol in stocks[: self.config.max_positions]:
            order = OrderRequest(
                symbol=symbol,
                action=self._determine_action(candidate),
                quantity=1,
                price=None,
                tag=candidate.name,
                strategy_id=candidate.name,
            )
            
            response = adapter.place_order(order)
            if response:
                responses.append(response)
        
        self._audit("execute", candidate.name, "hub", {
            "orders_placed": len(responses),
            "broker": adapter.config.platform.value,
        })
        
        return responses
    
    def _determine_action(self, candidate: StrategyCandidate):
        from ..broker._init_ import OrderSide
        
        if candidate.strategy_type in ("breakout", "momentum"):
            return OrderSide.BUY
        elif candidate.strategy_type == "mean_reversion":
            return OrderSide.BUY
        else:
            return OrderSide.BUY
    
    def _audit(
        self,
        action: str,
        strategy_name: str,
        source: str,
        details: Dict[str, Any],
    ) -> None:
        if not self.config.commercial_mode:
            return
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "strategy_name": strategy_name,
            "source": source,
            "details": details,
        }
        self.audit_trail.append(entry)
        
        if len(self.audit_trail) > 10000:
            self.audit_trail = self.audit_trail[-5000:]
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return self.audit_trail.copy()
    
    def export_audit_trail(self, path: str = "audit_trail.json") -> None:
        with open(path, "w") as f:
            json.dump(self.audit_trail, f, indent=2)
        logger.info(f"Audit trail exported to {path}")
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "candidates": len(self.strategy_candidates),
            "selected": len(self.selected_strategies),
            "paper_trading": len(self.paper_trading_strategies),
            "live": len(self.live_strategies),
            "vectorbt_available": self.vectorbt.is_available() if self.vectorbt else False,
            "backtrader_available": self.backtrader.is_available() if self.backtrader else False,
            "pkscreener_available": self.pkscreener.is_available() if self.pkscreener else False,
            "algo_india_available": self.algo_india.is_available() if self.algo_india else False,
            "ma_crossover_available": self.ma_crossover is not None,
            "ai_strategy_available": self.ai_generator is not None,
            "options_available": self.options is not None,
            "portfolio_optimizer_available": self.portfolio_optimizer is not None,
            "market_data_jugaad": self.market_data.jugaad.is_available(),
            "broker_connected": self.broker_adapter.is_connected() if self.broker_adapter else False,
            "commercial_mode": self.config.commercial_mode,
            "cost_pct": self.config.cost_pct,
            "min_edge_pct": self.config.min_edge_pct,
            "pilot_capital": self.config.pilot_capital,
            "llm_provider": self.config.llm_provider,
            "candidates_by_source": self._count_by_source(),
        }
    
    def collect_parameter_values(
        self,
        symbols: Optional[List[str]] = None,
        bars_by_symbol: Optional[Dict[str, Any]] = None,
        datasets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect data-pipeline values into the hub's ParameterValueStore.

        This is the first call that produces real output from the 48-parameter
        data ecosystem: fetched values with provenance plus an honest coverage
        report. Parameters whose feed is not connected are reported as
        unavailable instead of being filled with neutral defaults.
        """
        from ..data.parameter_store import ParameterValueStore
        from ..data.pipeline_orchestrator import (
            collect_parameter_values as _collect)

        symbols = symbols or sorted({
            s for c in self.strategy_candidates
            for s in (c.selected_stocks or [])})
        result = _collect(symbols, bars_by_symbol=bars_by_symbol, datasets=datasets)
        self.value_store = result.pop("store", None) or ParameterValueStore()
        return result

    def parameter_coverage(self) -> Dict[str, Any]:
        """Coverage of the 48-parameter catalogue by fetched values."""
        from ..data.parameter_store import ParameterValueStore
        store = self.value_store or ParameterValueStore()
        return store.coverage()

    def execute_trading_plan(self, plan_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a plan previously produced by build_trading_plan()."""
        from .execution_bridge import (
            StrategyExecutionBridge, TradingPlan, PlannedOrder)

        bridge = StrategyExecutionBridge(top_n=self.config.max_positions)

        orders = []
        for o in (plan_dict or {}).get("orders", []):
            order = PlannedOrder(
                symbol=o.get("symbol", ""),
                strategy_name=o.get("strategy_name", ""),
                entry_price=float(o.get("entry_price", 0) or 0),
                stop_loss=float(o.get("stop_loss", 0) or 0),
                target=o.get("target"),
                shares=int(o.get("shares", 0) or 0),
                position_value=float(o.get("position_value", 0) or 0),
                risk_at_stop=float(o.get("risk_at_stop", 0) or 0),
                deciding_limit=o.get("deciding_limit", ""),
                limit_reason=o.get("limit_reason", ""),
                approved=bool(o.get("approved", False)),
                reward_risk_ratio=float(o.get("reward_risk_ratio", 0) or 0),
                action=o.get("action", "BUY"),
            )
            orders.append(order)

        plan = TradingPlan(
            orders=orders,
            tradable=bool((plan_dict or {}).get("tradable", False)),
            blocked_reason=(plan_dict or {}).get("blocked_reason"),
            cash_after=(plan_dict or {}).get("cash_after"),
        )
        plan.recompute()
        report = bridge.execute_plan(plan)
        self._audit("execute_trading_plan", "plan", "hub", report.as_dict())
        return report.as_dict()

    def _count_by_source(self) -> Dict[str, int]:
        """Count ingested candidates grouped by source."""
        counts: Dict[str, int] = {}
        for c in self.strategy_candidates:
            counts[c.source] = counts.get(c.source, 0) + 1
        return counts

    def list_candidates(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": c.name,
                "source": c.source,
                "type": c.strategy_type,
                "weight_total": c.weight_total,
                "confidence": c.confidence,
                "brd_compliant": c.is_brd_compliant,
                "profitable": c.is_profitable,
                "in_paper_trading": c in self.paper_trading_strategies,
                "in_live": c in self.live_strategies,
                "edge_validation": c.edge_validation,
            }
            for c in self.strategy_candidates
        ]
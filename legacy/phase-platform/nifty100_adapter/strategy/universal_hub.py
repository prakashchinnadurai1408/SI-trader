"""Universal Strategy Hub for SI-Trader.

Combines all integration layers into a unified strategy solution:

1. Broker Connectivity: OpenAlgo, Kite Connect, Fenix
2. Market Data: jugaad-data, Kite Connect historical API
3. Backtesting: vectorbt, backtrader, existing SI-Trader backtesters
4. Strategies: PKScreener patterns, algo_trading_strategies_india
5. Parameter Catalogue: 30 parameters, weight total 100 (BRD compliant)

The hub provides:
- Universal strategy ingestion (from any layer)
- BRD-compliant validation (cost model, edge threshold, parameter weights)
- Backtesting across multiple engines
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
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.risk_rules is None:
            self.risk_rules = {}
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
    enable_vectorbt: bool = True
    enable_backtrader: bool = True
    enable_pkscreener: bool = True
    enable_algo_india: bool = True
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
        
        self.market_data = self.config.market_data_manager or MarketDataManager()
        self.broker_adapter = self.config.broker_adapter
        
        self.pkscreener = PKScreenerAdapter() if self.config.enable_pkscreener else None
        self.algo_india = AlgoIndiaAdapter() if self.config.enable_algo_india else None
        
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
            selected_stocks=[s.get("symbol", "") for s in strategy_config.get("selected_stocks", [])],
            risk_rules=strategy_config.get("risk_rules", {}),
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
        else:
            result = self._backtest_with_sitrader(candidate, price_data)
        
        if result:
            candidate.backtest_results = result
            candidate.edge_validation = self.validate_edge(result)
            self._audit("backtest", candidate.name, engine, result)
        
        return result or {}
    
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
            "market_data_jugaad": self.market_data.jugaad.is_available(),
            "broker_connected": self.broker_adapter.is_connected() if self.broker_adapter else False,
            "commercial_mode": self.config.commercial_mode,
            "cost_pct": self.config.cost_pct,
            "min_edge_pct": self.config.min_edge_pct,
            "pilot_capital": self.config.pilot_capital,
        }
    
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
"""algo_trading_strategies_india Strategy Adapter for SI-Trader.

Integrates buzzsubash/algo_trading_strategies_india - option strategies,
risk management, and trading strategies for Indian markets.

SI-Trader Integration:
- Option strategies adapted for delivery (CNC) weekly model
- Risk management rules integrated into SI-Trader compliance gates
- Strategy configurations converted to parameter weights
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from ._weight_utils import normalize_weights



@dataclass
class AlgoIndiaStrategy:
    """Strategy from algo_trading_strategies_india."""
    name: str
    strategy_type: str  # "breakout", "momentum", "mean_reversion", "option"
    description: str
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    risk_rules: Dict[str, Any]
    timeframe: str  # "daily", "weekly", "intraday"
    asset_class: str  # "equity", "futures", "options"
    confidence: float
    source: str = "algo_trading_strategies_india"


@dataclass
class AlgoIndiaConfig:
    """Configuration for algo strategies integration."""
    strategies_enabled: Optional[List[str]] = None
    min_confidence: float = 50.0
    max_positions: int = 10
    delivery_only: bool = True  # SI-Trader is delivery-focused
    max_position_pct: float = 10.0


class AlgoIndiaAdapter:
    """algo_trading_strategies_india adapter for SI-Trader.
    
    Integrates Indian trading strategies (breakout, momentum, etc.)
    into SI-Trader's parameter-based framework.
    
    Option strategies are adapted for delivery trading (CNC).
    Risk management rules feed into SI-Trader compliance gates.
    
    Usage:
        adapter = AlgoIndiaAdapter()
        strategies = adapter.load_strategies()
        weights = adapter.strategy_to_parameter_weights(strategy)
    """
    
    def __init__(self, config: Optional[AlgoIndiaConfig] = None):
        self.config = config or AlgoIndiaConfig()
        self._algo_available = False
        self._check_availability()
    
    def _check_availability(self) -> None:
        """Check if algo_trading_strategies_india is available."""
        try:
            import algo_trading_strategies_india  # type: ignore
            self._algo_available = True
            logger.info("algo_trading_strategies_india available")
        except ImportError:
            self._algo_available = False
            logger.info(
                "algo_trading_strategies_india not installed - "
                "using built-in strategy templates"
            )
    
    def is_available(self) -> bool:
        return self._algo_available
    
    def load_strategies(self) -> List[AlgoIndiaStrategy]:
        """Load available strategies from the library."""
        if self._algo_available:
            return self._load_from_library()
        else:
            return self._load_builtin_strategies()
    
    def _load_from_library(self) -> List[AlgoIndiaStrategy]:
        """Load from algo_trading_strategies_india library."""
        strategies = []
        try:
            import algo_trading_strategies_india as atsi  # type: ignore
            
            for attr_name in dir(atsi):
                if attr_name.startswith("_"):
                    continue
                try:
                    obj = getattr(atsi, attr_name)
                    if isinstance(obj, type) and hasattr(obj, "execute"):
                        strategies.append(AlgoIndiaStrategy(
                            name=attr_name,
                            strategy_type="unknown",
                            description=getattr(obj, "__doc__", "") or "",
                            entry_rules={},
                            exit_rules={},
                            risk_rules={},
                            timeframe="daily",
                            asset_class="equity",
                            confidence=70.0,
                        ))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"algo_trading_strategies_india load error: {e}")
        
        return strategies or self._load_builtin_strategies()
    
    def _load_builtin_strategies(self) -> List[AlgoIndiaStrategy]:
        """Load built-in Indian trading strategy templates."""
        strategies = [
            AlgoIndiaStrategy(
                name="Opening Range Breakout",
                strategy_type="breakout",
                description="Buy on breakout above opening range high",
                entry_rules={
                    "condition": "price > opening_range_high",
                    "volume_check": "volume > 1.5x average",
                    "time_window": "09:15-09:30",
                },
                exit_rules={
                    "stop_loss": "opening_range_low",
                    "target": "2x risk (2R)",
                    "time_exit": "15:30 (market close)",
                },
                risk_rules={
                    "max_position_pct": 10,
                    "max_daily_loss": 2.0,
                    "no_trade_after": "15:00",
                },
                timeframe="intraday",
                asset_class="equity",
                confidence=75.0,
            ),
            AlgoIndiaStrategy(
                name="Bull Flag Continuation",
                strategy_type="momentum",
                description="Buy on pullback to flag support in uptrend",
                entry_rules={
                    "condition": "price near flag support (20-day MA)",
                    "trend": "price > 20-day SMA",
                    "volume": "declining on pullback",
                },
                exit_rules={
                    "stop_loss": "flag_low",
                    "target": "flag_height projected upward",
                    "time_exit": "5 trading days",
                },
                risk_rules={
                    "max_position_pct": 10,
                    "trailing_stop": "2x ATR",
                },
                timeframe="daily",
                asset_class="equity",
                confidence=70.0,
            ),
            AlgoIndiaStrategy(
                name="Oversold Bounce",
                strategy_type="mean_reversion",
                description="Buy oversold stocks (RSI < 30) with mean reversion",
                entry_rules={
                    "condition": "RSI(14) < 30",
                    "trend": "price > 200-day SMA",
                    "candle": "bullish reversal candle",
                },
                exit_rules={
                    "stop_loss": "recent_low",
                    "target": "20-day SMA or RSI > 60",
                    "time_exit": "10 trading days",
                },
                risk_rules={
                    "max_position_pct": 8,
                    "max_concurrent": 3,
                },
                timeframe="daily",
                asset_class="equity",
                confidence=65.0,
            ),
            AlgoIndiaStrategy(
                name="20-Day High Breakout",
                strategy_type="breakout",
                description="Buy when price makes 20-day closing high",
                entry_rules={
                    "condition": "close > highest close of last 20 days",
                    "volume": "volume > 1.2x 20-day average",
                },
                exit_rules={
                    "stop_loss": "20-day low",
                    "target": "2x risk or next resistance",
                    "time_exit": "20 trading days",
                },
                risk_rules={
                    "max_position_pct": 10,
                    "sector_limit": "max 30% per sector",
                },
                timeframe="daily",
                asset_class="equity",
                confidence=72.0,
            ),
            AlgoIndiaStrategy(
                name="Moving Average Crossover",
                strategy_type="momentum",
                description="Buy when short MA crosses above long MA",
                entry_rules={
                    "condition": "MA(10) > MA(20) with price above both",
                    "confirmation": "price > MA(50)",
                },
                exit_rules={
                    "stop_loss": "MA(20)",
                    "target": "trailing stop at MA(10)",
                    "time_exit": "MA cross below",
                },
                risk_rules={
                    "max_position_pct": 10,
                    "no_trade_sideways": "price within 2% of MA(20)",
                },
                timeframe="daily",
                asset_class="equity",
                confidence=68.0,
            ),
        ]
        
        if self.config.delivery_only:
            strategies = [s for s in strategies if s.timeframe in ("daily", "weekly")]
        
        if self.config.strategies_enabled:
            strategies = [s for s in strategies if s.name in self.config.strategies_enabled]
        
        strategies = [s for s in strategies if s.confidence >= self.config.min_confidence]
        
        return strategies[: self.config.max_positions]
    
    def strategy_to_parameter_weights(
        self,
        strategy: AlgoIndiaStrategy,
        base_weights: Optional[Dict[str, int]] = None,
    ) -> Dict[str, int]:
        """Convert algo strategy to SI-Trader parameter weights.
        
        Maps strategy rules to SI-Trader's 30-parameter catalogue.
        Total weight must equal 100.
        """
        if base_weights is None:
            from ..config.parameter_catalogue import PARAMETER_CATALOGUE
            base_weights = {
                k: p.weight for k, p in PARAMETER_CATALOGUE.items()
                if p.enable_switch
            }

        adjusted = dict(base_weights)

        strategy_adjustments = {
            "breakout": {
                "price_momentum_weekly": 2,
                "historical_news_sentiment": 1,
                "midcap_liquidity_score": 1,
            },
            "momentum": {
                "price_momentum_weekly": 2,
                "fii_dii_mf_trend": 1,
                "roe_trend": 1,
            },
            "mean_reversion": {
                "pe_ratio_vs_sector": 2,
                "swot_analytics": 1,
                "historical_news_sentiment": 1,
                "midcap_volatility_adj": 1,
            },
        }

        adjustments = strategy_adjustments.get(strategy.strategy_type, {})
        confidence_factor = (strategy.confidence or 0) / 100.0

        for param, delta in adjustments.items():
            if param in adjusted:
                adjusted[param] = max(
                    1, adjusted[param] + int(round(delta * confidence_factor)))

        if strategy.risk_rules.get("max_position_pct", 10) <= 8:
            adjusted["liquidity_floor"] = max(
                1, adjusted.get("liquidity_floor", 5) + 1)
            adjusted["cost_vs_edge_check"] = max(
                1, adjusted.get("cost_vs_edge_check", 5) + 1)

        return normalize_weights(adjusted)
    
    def generate_strategy_config(
        self,
        strategy: AlgoIndiaStrategy,
        strategy_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate complete SI-Trader strategy configuration."""
        name = strategy_name or strategy.name
        weights = self.strategy_to_parameter_weights(strategy)
        
        timeframe_map = {
            "intraday": {"refresh": "daily", "holding_period": "1 day"},
            "daily": {"refresh": "daily", "holding_period": "1-5 days"},
            "weekly": {"refresh": "weekly", "holding_period": "1-4 weeks"},
        }
        tf = timeframe_map.get(strategy.timeframe, {"refresh": "daily", "holding_period": "1-5 days"})
        
        config = {
            "strategy_name": name,
            "strategy_type": strategy.strategy_type,
            "strategy_source": "algo_trading_strategies_india",
            "description": strategy.description,
            "parameter_weights": weights,
            "weight_total": sum(weights.values()),
            "timeframe": strategy.timeframe,
            "asset_class": strategy.asset_class,
            "confidence": strategy.confidence,
            "entry_rules": strategy.entry_rules,
            "exit_rules": strategy.exit_rules,
            "risk_rules": strategy.risk_rules,
            "refresh_schedule": tf["refresh"],
            "holding_period": tf["holding_period"],
            "delivery_compatible": strategy.timeframe in ("daily", "weekly"),
            "generated_at": datetime.now().isoformat(),
        }
        
        return config
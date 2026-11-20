"""VectorBT Backtesting Adapter for SI-Trader.

Integrates polakowo/vectorbt - fast, vectorised backtests of parameter sweeps.

vectorbt is ideal for:
- Rapid parameter sweep testing (thousands of parameter combinations)
- Vectorised operations (fast, no Python loops)
- Portfolio-level backtesting with position sizing
- Monte Carlo simulation integration
- Risk metrics calculation

SI-Trader Integration:
- Complements existing weekly/monthly backtesters
- Fast parameter sweep for the 30-parameter catalogue
- Edge validation against BRD cost model (0.38% roundtrip)
- Production readiness scoring
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class VectorBTAdapter:
    """VectorBT backtesting adapter for SI-Trader.
    
    Provides fast vectorised backtesting for parameter sweep testing.
    Complements SI-Trader's existing weekly/monthly backtesters.
    
    Usage:
        adapter = VectorBTAdapter()
        results = adapter.run_parameter_sweep(
            data=ohlcv_df,
            strategy_fn=my_strategy,
            param_grid={"momentum_weight": [1,2,3], "volatility_weight": [2,3,4]},
        )
    """
    
    def __init__(self, initial_capital: float = 25000.0):
        self.initial_capital = initial_capital
        self._vbt_available = False
        self._check_availability()
    
    def _check_availability(self) -> None:
        try:
            import vectorbt as vbt  # type: ignore
            self._vbt_available = True
            logger.info("vectorbt available for backtesting")
        except ImportError:
            self._vbt_available = False
            logger.warning(
                "vectorbt not installed - pip install vectorbt. "
                "Parameter sweep backtesting will be unavailable."
            )
    
    def is_available(self) -> bool:
        return self._vbt_available
    
    def run_backtest(
        self,
        prices: Any,
        signals: Any,
        position_size: float = 0.1,
        cost_pct: float = 0.38,
    ) -> Optional[Dict[str, Any]]:
        """Run a single backtest with vectorbt."""
        if not self._vbt_available:
            logger.error("vectorbt not available")
            return None
        
        try:
            import vectorbt as vbt
            import pandas as pd
            
            close = prices["close"] if isinstance(prices, dict) else prices.close
            
            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=signals > 0,
                exits=signals < 0,
                size=position_size,
                init_cash=self.initial_capital,
                fees=cost_pct / 100,
                freq="D",
            )
            
            stats = pf.stats()
            
            return {
                "total_return": float(stats.get("Total Return [%]", 0)),
                "cagr": float(stats.get("CAGR [%]", 0)),
                "sharpe": float(stats.get("Sharpe Ratio", 0)),
                "max_drawdown": float(stats.get("Max Drawdown [%]", 0)),
                "win_rate": float(stats.get("Win Rate [%]", 0)),
                "total_trades": int(stats.get("Total Trades", 0)),
                "avg_trade": float(stats.get("Avg Trade [%]", 0)),
                "expectancy": float(stats.get("Expectancy [%]", 0)),
                "final_value": float(stats.get("Final Value", self.initial_capital)),
                "net_profit": float(stats.get("Net Profit", 0)),
                "cost_pct": cost_pct,
            }
        except Exception as e:
            logger.error(f"VectorBT backtest error: {e}")
            return None
    
    def run_parameter_sweep(
        self,
        prices: Any,
        strategy_fn: callable,
        param_grid: Dict[str, List[Any]],
        cost_pct: float = 0.38,
        metric: str = "sharpe",
    ) -> Optional[Dict[str, Any]]:
        """Run parameter sweep with vectorbt."""
        if not self._vbt_available:
            logger.error("vectorbt not available")
            return None
        
        try:
            import itertools
            
            results = []
            param_names = list(param_grid.keys())
            
            for combo in itertools.product(*param_grid.values()):
                params = dict(zip(param_names, combo))
                
                signals = strategy_fn(prices, params)
                
                result = self.run_backtest(prices, signals, cost_pct=cost_pct)
                if result:
                    result["parameters"] = params
                    results.append(result)
            
            results.sort(key=lambda r: r.get(metric, 0), reverse=True)
            
            return {
                "best_parameters": results[0]["parameters"] if results else {},
                "best_metric": results[0].get(metric, 0) if results else 0,
                "best_result": results[0] if results else None,
                "total_combinations": len(results),
                "all_results": results[:10],
                "cost_pct": cost_pct,
            }
        except Exception as e:
            logger.error(f"VectorBT parameter sweep error: {e}")
            return None
    
    def validate_edge(
        self,
        results: Dict[str, Any],
        min_edge_pct: float = 0.3,
        cost_pct: float = 0.38,
    ) -> Dict[str, Any]:
        """Validate strategy edge against BRD cost threshold."""
        total_return = results.get("total_return", 0)
        net_profit = results.get("net_profit", 0)
        net_edge = total_return - cost_pct
        
        return {
            "gross_return": total_return,
            "cost_pct": cost_pct,
            "net_edge": net_edge,
            "min_edge_required": min_edge_pct,
            "edge_passes": net_edge > min_edge_pct,
            "profitable": net_profit > 0,
            "brd_compliant": net_edge > min_edge_pct and net_profit > 0,
        }
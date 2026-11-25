"""Backtrader Backtesting Adapter for SI-Trader.

Integrates mementum/backtrader - event-driven backtesting framework.

Note: backtrader is no longer actively developed but is easy to learn
and works well for event-driven backtesting of trading strategies.

Features:
- Event-driven backtesting (bar-by-bar)
- Easy strategy definition with Python classes
- Multiple data feeds support
- Built-in indicators and analyzers
- Position sizing and risk management

SI-Trader Integration:
- Event-driven backtesting for intraday strategies
- Complements vectorbt's vectorised approach
- Strategy development and testing
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BacktraderAdapter:
    """Backtrader adapter for SI-Trader.
    
    Provides event-driven backtesting for strategy development.
    
    Usage:
        adapter = BacktraderAdapter(initial_cash=25000.0)
        results = adapter.run_backtest(
            data=ohlcv_df,
            strategy_class=MyStrategy,
            strategy_params={"period": 20},
        )
    """
    
    def __init__(self, initial_cash: float = 25000.0, commission_pct: float = 0.38):
        self.initial_cash = initial_cash
        self.commission_pct = commission_pct
        self._bt_available = False
        self._check_availability()
    
    def _check_availability(self) -> None:
        try:
            import backtrader as bt
            self._bt_available = True
            logger.info("backtrader available for backtesting")
        except ImportError:
            self._bt_available = False
            logger.warning(
                "backtrader not installed - pip install backtrader. "
                "Event-driven backtesting will be unavailable."
            )
    
    def is_available(self) -> bool:
        return self._bt_available
    
    def run_backtest(
        self,
        data_feed: Any,
        strategy_class: Any,
        strategy_params: Optional[Dict[str, Any]] = None,
        cash: Optional[float] = None,
        commission: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Run event-driven backtest with backtrader."""
        if not self._bt_available:
            logger.error("backtrader not available")
            return None
        
        try:
            import backtrader as bt
            import pandas as pd
            
            cerebro = bt.Cerebro()
            cerebro.broker.setcash(cash or self.initial_cash)
            cerebro.broker.setcommission(commission=(commission or self.commission_pct) / 100)
            
            if isinstance(data_feed, pd.DataFrame):
                data = bt.feeds.PandasData(dataname=data_feed)
            else:
                data = data_feed
            cerebro.adddata(data)
            
            if strategy_params:
                cerebro.addstrategy(strategy_class, **strategy_params)
            else:
                cerebro.addstrategy(strategy_class)
            
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
            cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
            
            results = cerebro.run()
            strat = results[0]
            
            sharpe = strat.analyzers.sharpe.get_analysis()
            drawdown = strat.analyzers.drawdown.get_analysis()
            trades = strat.analyzers.trades.get_analysis()
            returns = strat.analyzers.returns.get_analysis()
            
            final_value = cerebro.broker.getvalue()
            
            return {
                "initial_cash": cash or self.initial_cash,
                "final_value": float(final_value),
                "net_profit": float(final_value - (cash or self.initial_cash)),
                "total_return": float(((final_value - (cash or self.initial_cash)) / (cash or self.initial_cash)) * 100),
                "sharpe": float(sharpe.get("sharperatio", 0) or 0),
                "max_drawdown": float(drawdown.get("max", {}).get("drawdown", 0)),
                "total_trades": int(trades.get("total", {}).get("total", 0)),
                "won_trades": int(trades.get("won", {}).get("total", 0)),
                "lost_trades": int(trades.get("lost", {}).get("total", 0)),
                "win_rate": float(
                    (trades.get("won", {}).get("total", 0) / trades.get("total", {}).get("total", 1)) * 100
                    if trades.get("total", {}).get("total", 0) > 0 else 0
                ),
                "commission_pct": commission or self.commission_pct,
            }
        except Exception as e:
            logger.error(f"Backtrader backtest error: {e}")
            return None
    
    def run_strategy_comparison(
        self,
        data_feed: Any,
        strategies: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results = []
        for s in strategies:
            result = self.run_backtest(
                data_feed=data_feed,
                strategy_class=s["class"],
                strategy_params=s.get("params", {}),
            )
            if result:
                result["strategy_name"] = s.get("name", s["class"].__name__)
                results.append(result)
        
        results.sort(key=lambda r: r.get("total_return", 0), reverse=True)
        return results
    
    def validate_edge(
        self,
        results: Dict[str, Any],
        min_edge_pct: float = 0.3,
        cost_pct: float = 0.38,
    ) -> Dict[str, Any]:
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
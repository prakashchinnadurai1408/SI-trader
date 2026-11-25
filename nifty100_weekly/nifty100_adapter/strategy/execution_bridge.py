"""Bridge from selected strategies to risk-sized, executable orders.

The hub can ingest strategies, backtest them and select the winners, and the
execution pipeline can place an order for an explicit symbol/price/stop - but
nothing connected the two: `execute_strategy` fired raw orders at quantity 1
with no stop-loss, no target and no sizing.

This module closes the loop:

    selected candidates + entry prices
        -> stop/target taken from the candidate's exit rules
        -> position sized by the four-limit BudgetManager
        -> kill switch, daily/weekly limits and compliance gates re-checked
        -> OrderRequest routed through OrderExecutionPipeline

Nothing here places an order on its own; a TradingPlan is produced first and
executed separately so the plan can be reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class PlannedOrder:
    """One planned, fully sized order for a symbol."""
    symbol: str
    strategy_name: str
    entry_price: float
    stop_loss: float
    target: Optional[float]
    shares: int = 0
    position_value: float = 0.0
    risk_at_stop: float = 0.0
    deciding_limit: str = ""
    limit_reason: str = ""
    approved: bool = False
    rejection_reason: Optional[str] = None
    reward_risk_ratio: float = 0.0
    action: str = "BUY"  # every SI-Trader strategy is long-only for now

    @property
    def is_executable(self) -> bool:
        return self.approved and self.shares > 0


@dataclass
class TradingPlan:
    """The full sized plan for a set of candidates."""
    orders: List[PlannedOrder] = field(default_factory=list)
    total_risk_at_stops: float = 0.0
    total_position_value: float = 0.0
    total_reward: float = 0.0
    cash_after: Optional[float] = None
    tradable: bool = False
    blocked_reason: Optional[str] = None
    skipped: List[str] = field(default_factory=list)
    created_at: Optional[str] = None

    def __post_init__(self):
        from datetime import datetime
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        self.recompute()

    def recompute(self) -> None:
        """Recompute totals from the current order list.

        Plans are usually built empty and filled afterwards, so totals must be
        recomputed once orders are appended.
        """
        self.total_risk_at_stops = sum(o.risk_at_stop for o in self.orders)
        self.total_position_value = sum(o.position_value for o in self.orders)
        self.total_reward = sum(
            max(0.0, (o.target or o.entry_price) - o.entry_price) * o.shares
            for o in self.orders)

    @property
    def executable_orders(self) -> List[PlannedOrder]:
        return [o for o in self.orders if o.is_executable]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "orders": [o.__dict__ for o in self.orders],
            "total_risk_at_stops": round(self.total_risk_at_stops, 2),
            "total_position_value": round(self.total_position_value, 2),
            "total_reward": round(self.total_reward, 2),
            "cash_after": self.cash_after,
            "tradable": self.tradable,
            "blocked_reason": self.blocked_reason,
            "skipped": self.skipped,
            "created_at": self.created_at,
        }


@dataclass
class ExecutionReport:
    """Outcome of executing a TradingPlan."""
    attempted: int = 0
    filled: int = 0
    rejected: int = 0
    net_risk: float = 0.0
    results: List[Any] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "attempted": self.attempted,
            "filled": self.filled,
            "rejected": self.rejected,
            "net_risk": round(self.net_risk, 2),
            "results": [r if isinstance(r, dict) else r.__dict__
                        for r in self.results],
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
        }


class StrategyExecutionBridge:
    """Turns selected strategies into sized, risk-checked orders."""

    def __init__(self, execution_pipeline=None, top_n: Optional[int] = None):
        from ..risk.execution_pipeline import OrderExecutionPipeline
        from ..risk.budget_manager import BudgetManager

        self.pipeline = execution_pipeline or OrderExecutionPipeline()
        self.budget: BudgetManager = getattr(
            self.pipeline, "budget_manager", None) or BudgetManager()
        self.top_n = top_n

    # ------------------------------------------------------------------
    # Stop/target derivation
    # ------------------------------------------------------------------

    def _stop_and_target(self, candidate: Any, entry: float,
                         fallback_stop_pct: float = 5.0
                         ) -> tuple:
        """Read stop/target out of a candidate's exit rules."""
        rules = getattr(candidate, "exit_rules", None) or {}
        # weights-only strategies may not carry exit rules
        stop = rules.get("stop_loss") or rules.get("stop_loss_pct")
        target = rules.get("target") or rules.get("target_pct")

        stop_price = None
        if isinstance(stop, (int, float)) and stop > 0:
            # a fraction below 1.0 or a small number is treated as a percent
            if stop < 1:  # absolute price fraction, e.g. 0.05
                stop_price = entry * (1 - stop * 100)
            elif stop < 100:  # percent
                stop_price = entry * (1 - stop / 100)
            else:  # absolute price
                stop_price = stop
        if stop_price is None or stop_price >= entry:
            stop_price = entry * (1 - fallback_stop_pct / 100)

        target_price = None
        if isinstance(target, (int, float)) and target > 0:
            if target < 1:
                target_price = entry * (1 + target * 100)
            elif target < 1000:
                target_price = entry * (1 + target / 100)
            else:
                target_price = target
        if target_price is not None and target_price <= entry:
            target_price = entry + (entry - stop_price) * 2  # 2R default

        return round(stop_price, 2), (
            round(target_price, 2) if target_price else None)

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    def build_plan(self, candidates: List[Any],
                   prices: Dict[str, float],
                   cash: Optional[float] = None) -> TradingPlan:
        """Size every executable candidate/stock combination."""
        can_trade, reason = self.budget.can_trade_today()
        if not can_trade:
            return TradingPlan(tradable=False, blocked_reason=reason,
                               orders=[])

        plan = TradingPlan(tradable=True, cash_after=cash)
        for candidate in candidates:
            stocks = list(getattr(candidate, "selected_stocks", []) or [])[
                : self.top_n or 10]
            if not stocks:
                plan.skipped.append(f"{getattr(candidate, 'name', '?')}: no "
                                    "selected stocks")
                continue
            for symbol in stocks:
                entry = float(prices.get(symbol, 0) or 0)
                if entry <= 0:
                    plan.skipped.append(f"{symbol}: no price")
                    continue
                stop, target = self._stop_and_target(candidate, entry)

                ok, sizing = self.budget.validate_order(
                    symbol=symbol, entry_price=entry, stop_loss=stop,
                    target=target, current_cash=cash)
                order = PlannedOrder(
                    symbol=symbol,
                    strategy_name=getattr(candidate, "name", "?"),
                    entry_price=entry,
                    stop_loss=stop,
                    target=target,
                    shares=sizing.recommended_shares,
                    position_value=sizing.position_value,
                    risk_at_stop=sizing.total_risk_at_stop,
                    deciding_limit=sizing.deciding_limit,
                    limit_reason=sizing.limit_reason,
                    approved=ok,
                    rejection_reason=None if ok else sizing.limit_reason,
                    reward_risk_ratio=sizing.reward_risk_ratio,
                )
                if order.is_executable and cash is not None:
                    cash -= order.position_value
                plan.orders.append(order)
        plan.cash_after = cash
        plan.recompute()
        return plan

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute_plan(self, plan: TradingPlan) -> ExecutionReport:
        """Route an already-built plan through the execution pipeline."""
        report = ExecutionReport(attempted=len(plan.executable_orders))
        if not plan.tradable or not plan.executable_orders:
            report.blocked = True
            report.blocked_reason = plan.blocked_reason or "nothing executable"
            return report

        from ..risk.execution_pipeline import ExecutionResult

        from ..broker._init_ import OrderSide

        for order in plan.executable_orders:
            result = self.pipeline.execute_order(
                symbol=order.symbol,
                action=(OrderSide(order.action)
                        if isinstance(order.action, str) else order.action),
                entry_price=order.entry_price,
                stop_loss=order.stop_loss,
                target=order.target,
                budget_rules=None,
                current_cash=getattr(self.budget, "rules", None).pilot_capital
                if getattr(self.budget, "rules", None) else None,
            )
            report.results.append(result)
            if getattr(result, "order_placed", False):
                report.filled += 1
                report.net_risk += order.risk_at_stop
            else:
                report.rejected += 1
        return report

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def plan_and_execute(self, candidates: List[Any],
                         prices: Dict[str, float],
                         cash: Optional[float] = None
                         ) -> tuple:
        plan = self.build_plan(candidates, prices, cash)
        report = self.execute_plan(plan)
        return plan, report


__all__ = [
    "StrategyExecutionBridge", "TradingPlan", "PlannedOrder", "ExecutionReport",
]
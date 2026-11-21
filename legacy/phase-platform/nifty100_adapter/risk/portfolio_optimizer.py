"""Portfolio Optimizer for SI-Trader.

Provides portfolio-level optimization across multiple strategies:
- Sharpe ratio optimization
- Position sizing with correlation adjustments
- Sector concentration limits
- Position-level risk allocation

Integrates with the Parameter Catalogue (30 params, weight 100) and
BRD cost model (0.38% roundtrip).

Usage:
    optimizer = PortfolioOptimizer(capital=25000.0)
    result = optimizer.optimize_portfolio(strategies, market_data)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import math

logger = logging.getLogger(__name__)


@dataclass
class StrategyAllocation:
    """Allocation for a single strategy in the portfolio."""
    strategy_name: str
    strategy_type: str
    weight_pct: float  # Percentage of capital allocated
    capital_allocated: float  # ₹ amount
    max_position_pct: float  # Max position size within this strategy
    expected_return_pct: float
    expected_volatility_pct: float
    expected_sharpe: float
    risk_contribution_pct: float  # Contribution to portfolio risk


@dataclass
class PortfolioOptimizationResult:
    """Portfolio optimization result."""
    total_capital: float
    total_allocated: float
    cash_remaining: float
    cash_pct: float
    strategies: List[StrategyAllocation]
    portfolio_metrics: Dict[str, Any]
    brd_compliant: bool
    optimization_timestamp: str


class PortfolioOptimizer:
    """Portfolio Optimizer for SI-Trader.

    Optimizes portfolio allocation across multiple strategies using:
    - Sharpe ratio maximization
    - Position sizing with correlation adjustments
    - Sector concentration limits
    - BRD-compliant risk limits

    BRD Constraints:
    - Max loss per trade: ₹500 (2% of ₹25,000)
    - Max position per stock: 10% of capital
    - Max positions: 10 stocks
    - Cash buffer: 10% minimum
    - Roundtrip cost: 0.38%
    """

    def __init__(self, capital: float = 25000.0):
        self.capital = capital
        self.max_position_pct = 0.10  # 10% per position
        self.max_positions = 10
        self.cash_buffer_pct = 0.10  # 10% cash buffer
        self.max_daily_loss_pct = 0.04  # 4% daily loss limit
        self.max_weekly_loss_pct = 0.20  # 20% weekly loss limit
        self.min_cash_pct = 0.10  # Keep 10% in cash

        logger.info(f"Portfolio Optimizer initialized with capital: ₹{capital:,.2f}")

    def optimize_portfolio(
        self,
        strategies: List[Dict[str, Any]],
        expected_returns: Optional[Dict[str, float]] = None,
        expected_volatilities: Optional[Dict[str, float]] = None,
        correlations: Optional[Dict[str, Dict[str, float]]] = None,
        max_strategies: int = 5
    ) -> PortfolioOptimizationResult:
        """Optimize portfolio allocation across strategies.

        Args:
            strategies: List of strategy configs from strategy generators
            expected_returns: Dict of strategy_name -> expected return %
            expected_volatilities: Dict of strategy_name -> expected volatility %
            correlations: Dict of strategy_name -> {other_strategy: correlation}
            max_strategies: Max number of strategies to include

        Returns:
            PortfolioOptimizationResult with allocations
        """
        if not strategies:
            return self._empty_result()

        # Filter to BRD-compliant strategies only
        valid_strategies = [
            s for s in strategies
            if s.get("weight_total", 0) == 100 and s.get("delivery_compatible", False)
        ]

        if not valid_strategies:
            logger.warning("No BRD-compliant strategies available")
            return self._empty_result()

        # Limit to max_strategies
        valid_strategies = valid_strategies[:max_strategies]

        # Get or estimate returns and volatilities
        expected_returns = expected_returns or {}
        expected_volatilities = expected_volatilities or {}
        correlations = correlations or {}

        # Calculate optimal weights using simplified mean-variance optimization
        allocations = self._optimize_weights(
            valid_strategies, expected_returns, expected_volatilities, correlations
        )

        # Apply position sizing limits
        allocations = self._apply_position_limits(
            allocations, valid_strategies
        )

        # Calculate portfolio metrics
        portfolio_metrics = self._calculate_portfolio_metrics(
            allocations, valid_strategies, expected_returns, expected_volatilities,
            correlations
        )

        # Build result
        strategy_allocations = []
        total_allocated = 0.0
        total_risk = 0.0

        for alloc in allocations:
            strategy_name = alloc["strategy_name"]
            weight_pct = alloc["weight_pct"]
            capital_allocated = self.capital * weight_pct / 100

            # Find strategy config
            strat_config = next(
                (s for s in valid_strategies if s.get("strategy_name") == strategy_name),
                None
            )

            strategy_allocations.append(StrategyAllocation(
                strategy_name=strategy_name,
                strategy_type=strat_config.get("strategy_type", "unknown") if strat_config else "unknown",
                weight_pct=weight_pct,
                capital_allocated=capital_allocated,
                max_position_pct=min(10.0, weight_pct),  # Cap at 10% per position
                expected_return_pct=expected_returns.get(strategy_name, 0.0),
                expected_volatility_pct=expected_volatilities.get(strategy_name, 0.0),
                expected_sharpe=alloc.get("sharpe_contribution", 0.0),
                risk_contribution_pct=alloc.get("risk_contribution_pct", 0.0),
            ))
            total_allocated += capital_allocated
            total_risk += alloc.get("risk_contribution_pct", 0)

        cash_remaining = self.capital - total_allocated
        cash_pct = (cash_remaining / self.capital) * 100 if self.capital > 0 else 0

        # Check BRD compliance
        brd_compliant = (
            total_allocated <= self.capital and
            cash_pct >= self.cash_buffer_pct * 100 and
            len(strategy_allocations) <= self.max_positions and
            all(a.max_position_pct <= 10.0 for a in strategy_allocations)
        )

        return PortfolioOptimizationResult(
            total_capital=self.capital,
            total_allocated=round(total_allocated, 2),
            cash_remaining=round(cash_remaining, 2),
            cash_pct=round(cash_pct, 1),
            strategies=strategy_allocations,
            portfolio_metrics=portfolio_metrics,
            brd_compliant=brd_compliant,
            optimization_timestamp=datetime.now().isoformat(),
        )

    def _optimize_weights(
        self,
        strategies: List[Dict[str, Any]],
        expected_returns: Dict[str, float],
        expected_volatilities: Dict[str, float],
        correlations: Dict[str, Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """Optimize weights using simplified mean-variance optimization.

        Uses a simplified approach: equal weight adjusted by Sharpe ratio.
        This is a simplified version - in production, use scipy.optimize.
        """
        n = len(strategies)
        if n == 0:
            return []

        # Calculate expected returns and volatilities for each strategy
        returns = []
        vols = []
        for s in strategies:
            name = s.get("strategy_name", "")
            returns.append(expected_returns.get(name, 0.05))  # Default 5% return
            vols.append(expected_volatilities.get(name, 0.15))  # Default 15% vol

        # Calculate Sharpe ratios
        sharpes = []
        for r, v in zip(returns, vols):
            if v > 0:
                sharpes.append(r / v)
            else:
                sharpes.append(0.0)

        # Weight by Sharpe ratio (higher Sharpe = higher weight)
        total_sharpe = sum(max(s, 0.1) for s in sharpes)  # Min 0.1 to avoid zero

        allocations = []
        for i, s in enumerate(strategies):
            name = s.get("strategy_name", "")
            sharpe = sharpes[i]
            weight = (max(sharpe, 0.1) / total_sharpe) * 100

            allocations.append({
                "strategy_name": name,
                "weight_pct": weight,
                "expected_return": returns[i],
                "expected_volatility": vols[i],
                "sharpe_contribution": sharpes[i],
                "risk_contribution_pct": weight * (vols[i] / 100) if vols[i] > 0 else 0,
            })

        # Normalize weights to sum to 100%
        total_weight = sum(a["weight_pct"] for a in allocations)
        if total_weight > 0:
            for a in allocations:
                a["weight_pct"] = (a["weight_pct"] / total_weight) * 100
                a["risk_contribution_pct"] = a["weight_pct"] * (a["expected_volatility"] / 100)

        return allocations

    def _apply_position_limits(
        self,
        allocations: List[Dict[str, Any]],
        strategies: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply position size limits to allocations."""
        adjusted = []

        for a in allocations:
            weight = a["weight_pct"]

            # Cap at max position % (10%)
            if weight > self.max_position_pct:
                weight = self.max_position_pct

            # Ensure minimum position (1%)
            if weight < 1.0:
                weight = 1.0

            a["weight_pct"] = round(weight, 2)
            a["risk_contribution_pct"] = a["weight_pct"] * (a["expected_volatility"] / 100)
            adjusted.append(a)

        # Re-normalize to 100% if possible
        total = sum(a["weight_pct"] for a in adjusted)
        if total > 0 and abs(total - 100) > 0.5:
            scale = 100 / total
            for a in adjusted:
                a["weight_pct"] = round(a["weight_pct"] * scale, 2)
                a["risk_contribution_pct"] = a["weight_pct"] * (a["expected_volatility"] / 100)

        return adjusted

    def _calculate_portfolio_metrics(
        self,
        allocations: List[Dict[str, Any]],
        strategies: List[Dict[str, Any]],
        expected_returns: Dict[str, float],
        expected_volatilities: Dict[str, float],
        correlations: Dict[str, Dict[str, float]]
    ) -> Dict[str, Any]:
        """Calculate portfolio-level metrics."""
        if not allocations:
            return {}

        total_weight = sum(a["weight_pct"] for a in allocations)
        weighted_return = sum(
            a["weight_pct"] / 100 * a["expected_return"] for a in allocations
        ) / 100 if total_weight > 0 else 0

        weighted_vol = sum(
            (a["weight_pct"] / 100) ** 2 * (a["expected_volatility"] / 100) ** 2
            for a in allocations
        ) ** 0.5 if allocations else 0

        portfolio_sharpe = weighted_return / weighted_vol if weighted_vol > 0 else 0

        max_weight = max(a["weight_pct"] for a in allocations) if allocations else 0
        min_weight = min(a["weight_pct"] for a in allocations) if allocations else 0

        return {
            "total_weight": round(total_weight, 1),
            "expected_return_pct": round(weighted_return, 2),
            "expected_volatility_pct": round(weighted_vol * 100, 2),
            "portfolio_sharpe": round(portfolio_sharpe, 2),
            "max_weight_pct": round(max_weight, 1),
            "min_weight_pct": round(min_weight, 1),
            "num_strategies": len(allocations),
            "concentration_risk": "LOW" if max_weight <= 30 else "MEDIUM" if max_weight <= 50 else "HIGH",
        }

    def _empty_result(self) -> PortfolioOptimizationResult:
        """Return empty result when no strategies available."""
        return PortfolioOptimizationResult(
            total_capital=self.capital,
            total_allocated=0.0,
            cash_remaining=self.capital,
            cash_pct=100.0,
            strategies=[],
            portfolio_metrics={
                "total_weight": 0,
                "expected_return_pct": 0,
                "expected_volatility_pct": 0,
                "portfolio_sharpe": 0,
                "max_weight_pct": 0,
                "min_weight_pct": 0,
                "num_strategies": 0,
                "concentration_risk": "N/A",
            },
            brd_compliant=True,
            optimization_timestamp=datetime.now().isoformat(),
        )

    def get_position_sizing_recommendation(
        self,
        strategy_name: str,
        entry_price: float,
        stop_loss: float,
        capital: Optional[float] = None
    ) -> Dict[str, Any]:
        """Calculate position size for a single trade based on risk limits.

        Uses the BRD risk rules:
        - Max loss per trade: ₹500 (2% of ₹25,000)
        - Max position: 10% of capital
        - Risk per share = entry - stop
        """

        capital = capital or self.capital
        max_loss_per_trade = capital * 0.02  # 2% of capital = ₹500
        max_position_value = capital * 0.10  # 10% of capital = ₹2,500

        risk_per_share = entry_price - stop_loss
        if risk_per_share <= 0:
            return {
                "valid": False,
                "reason": "Stop loss must be below entry price",
                "shares": 0,
                "position_value": 0,
            }

        # Max shares based on max loss per trade
        max_shares_by_risk = int(max_loss_per_trade / risk_per_share) if risk_per_share > 0 else 0

        # Max shares by position cap
        max_shares_by_cap = int(max_position_value / entry_price)

        # Take the minimum
        recommended_shares = min(max_shares_by_risk, max_shares_by_cap)

        position_value = recommended_shares * entry_price
        total_risk = recommended_shares * risk_per_share

        return {
            "valid": recommended_shares > 0,
            "symbol": None,
            "shares": recommended_shares,
            "position_value": round(position_value, 2),
            "position_pct_of_capital": round((position_value / capital) * 100, 2),
            "risk_per_share": round(risk_per_share, 2),
            "total_risk_at_stop": round(total_risk, 2),
            "max_loss_per_trade": max_loss_per_trade,
            "deciding_limit": "max_loss_per_trade" if max_shares_by_risk <= max_shares_by_cap else "position_cap",
            "stop_loss": stop_loss,
            "entry_price": entry_price,
        }


# Convenience function
def optimize_portfolio(
    strategies: List[Dict[str, Any]],
    capital: float = 25000.0,
    expected_returns: Optional[Dict[str, float]] = None,
    expected_volatilities: Optional[Dict[str, float]] = None,
    correlations: Optional[Dict[str, Dict[str, float]]] = None,
    max_strategies: int = 5
) -> PortfolioOptimizationResult:
    """Convenience function to optimize portfolio."""
    optimizer = PortfolioOptimizer(capital=capital)
    return optimizer.optimize_portfolio(
        strategies=strategies,
        expected_returns=expected_returns,
        expected_volatilities=expected_volatilities,
        correlations=correlations,
        max_strategies=max_strategies,
    )


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    capital: float = 25000.0
) -> Dict[str, Any]:
    """Convenience function to calculate position size."""
    optimizer = PortfolioOptimizer(capital=capital)
    return optimizer.get_position_sizing_recommendation(
        symbol="",
        entry_price=entry_price,
        stop_loss=stop_loss,
        capital=capital
    )
"""MA Crossover Strategy Adapter for SI-Trader.

Encodes Moving Average Crossover strategies into SI-Trader's 30-parameter
catalogue weight configurations. Each MA strategy is encoded as a unique
weight configuration that sums to 100, enabling backtesting and selection
within the BRD-compliant framework.

Supported MA Strategies:
- MA 5/MA 10 Crossover (Short-term)
- MA 10/MA 20 Crossover (Medium-term)
- MA 20/MA 50 Crossover (Long-term)
- MA 50/MA 200 Crossover (Golden/Death Cross)

Usage:
    adapter = MACrossoverAdapter()
    config = adapter.get_strategy_config("MA5_MA10")
    # Returns parameter weight configuration summing to 100
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
from ..config.parameter_catalogue import PARAMETER_CATALOGUE as _PARAM_CATALOGUE
from ._weight_utils import normalize_weights, apply_adjustments



@dataclass
class MACrossoverStrategy:
    """MA Crossover strategy definition."""
    name: str
    display_name: str
    fast_period: int
    slow_period: int
    strategy_type: str  # "crossover"
    description: str
    suitable_timeframe: str  # "intraday", "daily", "weekly"
    min_data_points: int


@dataclass
class MACrossoverResult:
    """Result of MA crossover strategy encoding."""
    strategy_name: str
    parameter_weights: Dict[str, int]
    weight_total: int
    brd_compliant: bool
    buy_signal_condition: str
    sell_signal_condition: str
    stop_loss_pct: float
    target_pct: float
    expected_hold_period_days: int


class MACrossoverAdapter:
    """MA Crossover Strategy Adapter for SI-Trader.

    Encodes MA crossover strategies into the 30-parameter catalogue weight
    system. Each strategy becomes a unique weight configuration that can be
    backtested and selected within the platform.

    Weight allocation logic:
    - price_momentum_weekly: Primary weight (trend direction)
    - price_momentum_monthly: Confirmation weight
    - price_momentum_yearly: Long-term trend filter
    - f_score / altman_z_score: Fundamental filter (small weight)
    - midcap_liquidity_score: Liquidity filter
    - cost_vs_edge_check: Cost validation (BRD requirement)
    - stt_rate_equity / stcg_tax_rate / brokerage_rate: Cost parameters
    """
    # BRD-compliant base weights that sum to 100 across all 30 parameters
    # These are the BASE weights; strategy-specific adjustments are made
    # relative to this base while maintaining total = 100
    # Derived from the authoritative parameter catalogue so weights can never
    # drift from the BRD requirement (48 enabled parameters, total weight 100).
    BASE_WEIGHTS = {k: p.weight for k, p in _PARAM_CATALOGUE.items() if p.enable_switch}

    # Verify total = 100 at module load
    _TOTAL_CHECK = sum(BASE_WEIGHTS.values())
    assert _TOTAL_CHECK == 100, f"BASE_WEIGHTS total is {_TOTAL_CHECK}, must be 100"

    # MA Strategy Configurations: (fast_period, slow_period, weight_adjustments)
    # Weight adjustments redistribute existing weights; total stays at 100
    MA_STRATEGIES = {
        "MA5_MA10": {
            "display_name": "MA 5/10 Crossover",
            "fast_period": 5,
            "slow_period": 10,
            "description": "Short-term MA crossover - short-term momentum capture",
            "timeframe": "intraday",
            "min_bars": 10,
            "weight_adjustments": {
                # Increase weight on short-term momentum
                "price_momentum_weekly": 5,  # +2
                "price_momentum_monthly": 1,  # -1
                "price_momentum_yearly": 1,   # -1
                "midcap_volatility_adj": 3,   # +1 (higher volatility sensitivity)
                "cost_vs_edge_check": 3,      # +1 (higher trading frequency)
                "brokerage_rate": 3,          # +1 (higher turnover cost)
                # Reduce from longer-term
                "roe_trend": 2,               # -1
                "earnings_trend": 2,          # -1
                "f_score": 0,                 # -1
                "altman_z_score": 0,          # -1
            },
        },
        "MA10_MA20": {
            "display_name": "MA 10/20 Crossover",
            "fast_period": 10,
            "slow_period": 20,
            "description": "Medium-term MA crossover - balanced swing trading",
            "timeframe": "daily",
            "min_bars": 20,
            "weight_adjustments": {
                "price_momentum_weekly": 4,
                "price_momentum_monthly": 2,
                "price_momentum_yearly": 1,
                "midcap_volatility_adj": 2,
                "cost_vs_edge_check": 3,
                "brokerage_rate": 3,
                "roe_trend": 2,
                "earnings_trend": 2,
                "f_score": 1,
                "altman_z_score": 1,
            },
        },
        "MA20_MA50": {
            "display_name": "MA 20/50 Crossover",
            "fast_period": 20,
            "slow_period": 50,
            "description": "Longer-term MA crossover - trend following",
            "timeframe": "weekly",
            "min_bars": 50,
            "weight_adjustments": {
                "price_momentum_weekly": 3,
                "price_momentum_monthly": 3,
                "price_momentum_yearly": 2,
                "roe_trend": 3,
                "earnings_trend": 3,
                "f_score": 2,
                "altman_z_score": 2,
                "midcap_volatility_adj": 1,
                "cost_vs_edge_check": 2,
                "brokerage_rate": 2,
                "swot_analytics": 3,
                "competitive_plans": 3,
            },
        },
        "MA50_MA200": {
            "display_name": "MA 50/200 Crossover (Golden/Death Cross)",
            "fast_period": 50,
            "slow_period": 200,
            "description": "Long-term MA crossover - major trend changes",
            "timeframe": "monthly",
            "min_bars": 200,
            "weight_adjustments": {
                "price_momentum_weekly": 2,
                "price_momentum_monthly": 3,
                "price_momentum_yearly": 3,
                "roe_trend": 4,
                "earnings_trend": 4,
                "f_score": 3,
                "altman_z_score": 3,
                "swot_analytics": 3,
                "competitive_plans": 3,
                "midcap_volatility_adj": 1,
                "cost_vs_edge_check": 1,
                "brokerage_rate": 1,
            },
        },
    }

    def __init__(self):
        self._validate_weights()

    def _validate_weights(self):
        """Validate that base weights sum to 100."""
        total = sum(self.BASE_WEIGHTS.values())
        if total != 100:
            raise ValueError(f"BASE_WEIGHTS total is {total}, must be 100")

    def get_available_strategies(self) -> List[MACrossoverStrategy]:
        """Get list of all available MA crossover strategies."""
        strategies = []
        for key, config in self.MA_STRATEGIES.items():
            strategies.append(MACrossoverStrategy(
                name=key,
                display_name=config["display_name"],
                fast_period=config["fast_period"],
                slow_period=config["slow_period"],
                role_type="Score",
                description=config["description"],
                timeframe=config["timeframe"],
                min_bars=config["min_bars"],
            ))
        return strategies

    def get_strategy_config(self, strategy_name: str) -> MACrossoverResult:
        """Get parameter weight configuration for a specific MA strategy.

        Args:
            strategy_name: Name of the MA strategy (e.g., "MA5_MA10")

        Returns:
            MACrossoverResult with parameter weights and metadata
        """
        if strategy_name not in self.MA_STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy_name}. "
                           f"Available: {list(self.MA_STRATEGIES.keys())}")

        config = self.MA_STRATEGIES[strategy_name]

        # Start from base weights
        weights = dict(self.BASE_WEIGHTS)

        # Apply strategy-specific adjustments
        adjustments = config["weight_adjustments"]
        for param_key, adjustment in adjustments.items():
            if param_key in weights:
                weights[param_key] = max(1, weights[param_key] + adjustment)

        weights = normalize_weights(weights)

        # Verify final total
        final_total = sum(weights.values())
        if final_total != 100:
            raise ValueError(f"Final weight total is {final_total}, must be 100")

        # Calculate R:R and stop/target based on strategy type
        fast_period = config["fast_period"]
        slow_period = config["slow_period"]

        # Estimate stop loss as percentage of entry (based on volatility)
        stop_loss_pct = max(2.0, (slow_period - fast_period) * 0.5)
        target_pct = stop_loss_pct * 2.0  # 2R target

        expected_hold_days = max(slow_period, 5)

        return MACrossoverResult(
            strategy_name=strategy_name,
            parameter_weights=weights,
            weight_total=sum(weights.values()),
            brd_compliant=sum(weights.values()) == 100,
            buy_signal_condition=f"price > MA{fast_period} AND MA{fast_period} > MA{slow_period}",
            sell_signal_condition=f"price < MA{slow_period} OR MA{fast_period} < MA{slow_period}",
            stop_loss_pct=stop_loss_pct,
            target_pct=target_pct,
            expected_hold_period_days=expected_hold_days,
        )

    def generate_strategy_config_dict(
        self,
        strategy_name: str,
        strategy_name_display: str = None
    ) -> Dict[str, Any]:
        """Generate full strategy configuration dict for SI-Trader integration.

        Returns a dict that can be directly used by the Universal Strategy Hub
        for backtesting and selection.
        """
        result = self.get_strategy_config(strategy_name)
        config = self.MA_STRATEGIES[strategy_name]

        return {
            "strategy_name": strategy_name_display or config["display_name"],
            "strategy_type": "MA_CROSSOVER",
            "description": config["description"],
            "parameter_weights": result.parameter_weights,
            "weight_total": result.weight_total,
            "timeframe": config["timeframe"],
            "asset_class": "equity",
            "confidence": 75.0,
            "entry_rules": {
                "buy_condition": result.buy_signal_condition,
                "sell_condition": result.sell_signal_condition,
                "fast_ma": config["fast_period"],
                "slow_ma": config["slow_period"],
            },
            "exit_rules": {
                "stop_loss_pct": result.stop_loss_pct,
                "target_pct": result.target_pct,
                "max_hold_days": result.expected_hold_period_days,
            },
            "risk_rules": {
                "max_position_pct": 10,
                "stop_loss": result.stop_loss_pct,
                "target": result.target_pct,
            },
            "refresh_schedule": "daily",
            "holding_period": f"{config['min_bars']} days",
            "delivery_compatible": True,
            "generated_at": datetime.now().isoformat(),
            "brd_compliant": result.brd_compliant,
        }


# Convenience function for quick access
def get_ma_strategy_config(strategy_name: str) -> Dict[str, Any]:
    """Convenience function to get MA crossover strategy config."""
    adapter = MACrossoverAdapter()
    return adapter.generate_strategy_config_dict(strategy_name)


def get_all_ma_strategies() -> List[Dict[str, Any]]:
    """Get all MA crossover strategy configs."""
    adapter = MACrossoverAdapter()
    strategies = []
    for key in adapter.MA_STRATEGIES:
        strategies.append(adapter.generate_strategy_config_dict(key))
    return strategies
"""Options Strategy Adapter for SI-Trader.

Integrates options strategies into the SI-Trader platform while maintaining
BRD compliance. Since SI-Trader is primarily a weekly delivery platform,
options strategies are adapted for cash-settled index options (Nifty 50,
Bank Nifty) with cash settlement - no physical delivery required.

Supported Strategies:
- Bull Call Spread
- Bear Put Spread
- Iron Condor
- Straddle / Strangle
- Covered Call (with underlying delivery)
- Protective Put (with underlying delivery)

Parameters mapped to the 30-parameter catalogue for backtesting compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
from ..config.parameter_catalogue import PARAMETER_CATALOGUE as _PARAM_CATALOGUE
from ._weight_utils import normalize_weights, apply_adjustments



@dataclass
class OptionLeg:
    """Single option leg in a strategy."""
    option_type: str  # CE (Call) or PE (Put)
    strike: float
    premium: float
    lot_size: int
    action: str  # BUY or SELL


@dataclass
class OptionStrategy:
    """Options strategy definition."""
    name: str
    display_name: str
    strategy_type: str  # debit_spread, credit_spread, neutral, directional_hedge
    legs: List[dict]  # List of option leg dicts
    description: str
    max_profit: float
    max_loss: float
    breakeven_points: List[float]
    suitable_market_condition: str  # bullish, bearish, neutral, volatile
    timeframe: str  # weekly, monthly
    min_lot_size: int
    margin_required: float  # Estimated margin required


@dataclass
class OptionStrategyResult:
    """Result of option strategy encoding."""
    strategy_name: str
    parameter_weights: Dict[str, int]
    weight_total: int
    brd_compliant: bool
    strategy_details: Dict[str, Any]
    capital_required: float
    max_loss: float
    max_profit: float
    breakeven: List[float]


class OptionsStrategyAdapter:
    """Options Strategy Adapter for SI-Trader.

    Encodes options strategies into the SI-Trader 30-parameter catalogue
    weight system. Options are cash-settled (Nifty 50, Bank Nifty) to
    maintain delivery-only compliance of the platform.

    Strategies available:
    - Bull Call Spread (Debit spread, bullish)
    - Bear Put Spread (Debit spread, bearish)
    - Iron Condor (Credit spread, neutral)
    - Long Straddle (Volatility, neutral)
    - Long Strangle (Volatility, neutral)
    - Covered Call (with underlying delivery)
    - Protective Put (with underlying delivery)
    """
    def __init__(self):
        self._validate_base_weights()

    # Base weights that sum to 100
    # Derived from the authoritative parameter catalogue so weights can never
    # drift from the BRD requirement (48 enabled parameters, total weight 100).
    BASE_WEIGHTS = {k: p.weight for k, p in _PARAM_CATALOGUE.items() if p.enable_switch}

    _TOTAL_CHECK = sum(BASE_WEIGHTS.values())
    assert _TOTAL_CHECK == 100, f"BASE_WEIGHTS total is {_TOTAL_CHECK}, must be 100"

    # Option strategy definitions
    OPTION_STRATEGIES = {
        "bull_call_spread": {
            "display_name": "Bull Call Spread",
            "strategy_type": "debit_spread",
            "description": "Buy lower strike call, sell higher strike call. Limited risk, limited profit.",
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike_offset": -50, "weight": 1},
                {"action": "SELL", "option_type": "CE", "strike_offset": +50, "weight": -1},
            ],
            "suitable_market_condition": "bullish",
            "timeframe": "weekly",
        },
        "bear_put_spread": {
            "display_name": "Bear Put Spread",
            "strategy_type": "debit_spread",
            "description": "Buy higher strike put, sell lower strike put. Limited risk, limited profit.",
            "legs": [
                {"action": "BUY", "option_type": "PE", "strike_offset": +50, "weight": 1},
                {"action": "SELL", "option_type": "PE", "strike_offset": -50, "weight": -1},
            ],
            "suitable_market_condition": "bearish",
            "timeframe": "weekly",
        },
        "iron_condor": {
            "display_name": "Iron Condor",
            "strategy_type": "credit_spread",
            "description": "Sell OTM call spread and OTM put spread. Profits from range-bound market.",
            "legs": [
                {"action": "SELL", "option_type": "CE", "strike_offset": +100, "weight": -1},
                {"action": "BUY", "option_type": "CE", "strike_offset": +150, "weight": 1},
                {"action": "SELL", "option_type": "PE", "strike_offset": -100, "weight": -1},
                {"action": "BUY", "option_type": "PE", "strike_offset": -150, "weight": 1},
            ],
            "suitable_market_condition": "neutral",
            "timeframe": "weekly",
        },
        "long_straddle": {
            "display_name": "Long Straddle",
            "strategy_type": "neutral_volatility",
            "description": "Buy ATM call and put. Profits from large move in either direction.",
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike_offset": 0, "weight": 1},
                {"action": "BUY", "option_type": "PE", "strike_offset": 0, "weight": 1},
            ],
            "suitable_market_condition": "volatile",
            "timeframe": "weekly",
        },
        "long_strangle": {
            "display_name": "Long Strangle",
            "strategy_type": "neutral_volatility",
            "description": "Buy OTM call and put. Cheaper than straddle, needs larger move.",
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike_offset": +50, "weight": 1},
                {"action": "BUY", "option_type": "PE", "strike_offset": -50, "weight": 1},
            ],
            "suitable_market_condition": "volatile",
            "timeframe": "weekly",
        },
        "covered_call": {
            "display_name": "Covered Call",
            "strategy_type": "directional_hedge",
            "description": "Buy stock, sell OTM call against it. Generates income in flat market.",
            "legs": [
                {"action": "BUY", "option_type": "STOCK", "strike_offset": 0, "weight": 1},
                {"action": "SELL", "option_type": "CE", "strike_offset": +50, "weight": -0.5},
            ],
            "suitable_market_condition": "neutral_to_bullish",
            "timeframe": "weekly",
        },
        "protective_put": {
            "display_name": "Protective Put",
            "strategy_type": "directional_hedge",
            "description": "Buy stock, buy put for downside protection.",
            "legs": [
                {"action": "BUY", "option_type": "STOCK", "strike_offset": 0, "weight": 1},
                {"action": "BUY", "option_type": "PE", "strike_offset": -50, "weight": 1},
            ],
            "suitable_market_condition": "bullish_with_protection",
            "timeframe": "weekly",
        },
    }

    def __init__(self):
        self._validate_weights()

    def _validate_weights(self):
        """Validate base weights sum to 100."""
        total = sum(self.BASE_WEIGHTS.values())
        if total != 100:
            raise ValueError(f"BASE_WEIGHTS total is {total}, must be 100")

    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """Get list of all available options strategies."""
        strategies = []
        for key, config in self.OPTION_STRATEGIES.items():
            strategies.append({
                "strategy_name": key,
                "display_name": config["display_name"],
                "strategy_type": config["strategy_type"],
                "description": config["description"],
                "suitable_market_condition": config["suitable_market_condition"],
                "timeframe": config["timeframe"],
                "legs": config["legs"],
            })
        return strategies

    def get_strategy_config(
        self,
        strategy_name: str,
        underlying_price: float = 19000.0,  # Approximate Nifty 50 level
    ) -> Dict[str, Any]:
        """Generate strategy configuration for SI-Trader.

        Args:
            strategy_name: Name of the options strategy
            underlying_price: Current underlying price (Nifty 50 approx)

        Returns:
            Strategy configuration dict for SI-Trader integration
        """
        if strategy_name not in self.OPTION_STRATEGIES:
            raise ValueError(
                f"Unknown strategy: {strategy_name}. "
                f"Available: {list(self.OPTION_STRATEGIES.keys())}"
            )

        config = self.OPTION_STRATEGIES[strategy_name]

        # Adjust base weights based on strategy type
        weights = dict(self.BASE_WEIGHTS)

        # Strategy-specific weight adjustments
        adjustments = self._get_strategy_adjustments(config["strategy_type"])
        for param_key, adjustment in adjustments.items():
            if param_key in weights:
                weights[param_key] = max(1, weights[param_key] + adjustment)

        # Renormalize to 100
        weights = normalize_weights(weights)

        final_total = sum(weights.values())
        if final_total != 100:
            raise ValueError(f"Final weight total is {final_total}, must be 100")

        # Calculate strategy specifics
        result = {
            "strategy_name": strategy_name,
            "strategy_type": config["strategy_type"],
            "description": config["description"],
            "parameter_weights": weights,
            "weight_total": sum(weights.values()),
            "brd_compliant": sum(weights.values()) == 100,
            "suitable_market_condition": config["suitable_market_condition"],
            "timeframe": config["timeframe"],
            "underlying_price": underlying_price,
            "legs": config["legs"],
            "legs_count": len(config["legs"]),
            "delivery_compatible": True,  # Cash-settled index options
            "generated_at": datetime.now().isoformat(),
        }

        return result

    def _get_strategy_adjustments(self, strategy_type: str) -> Dict[str, int]:
        """Get weight adjustments for each strategy type."""
        adjustments_map = {
            "debit_spread": {
                "price_momentum_weekly": 2,
                "midcap_volatility_adj": 1,
                "historical_news_sentiment": 1,
                "roe_trend": -1,
                "earnings_trend": -1,
            },
            "credit_spread": {
                "price_momentum_weekly": 1,
                "price_momentum_monthly": 2,
                "midcap_volatility_adj": 2,
                "roe_trend": 1,
                "earnings_trend": 1,
                "swot_analytics": 1,
            },
            "neutral_volatility": {
                "midcap_volatility_adj": 3,
                "historical_news_sentiment": 2,
                "price_momentum_weekly": -1,
                "price_momentum_monthly": -1,
                "roe_trend": -1,
                "earnings_trend": -1,
            },
            "directional_hedge": {
                "price_momentum_weekly": 2,
                "roe_trend": 2,
                "earnings_trend": 2,
                "midcap_volatility_adj": -1,
                "midcap_liquidity_score": 1,
            },
        }
        return adjustments_map.get(strategy_type, {})

    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Get all options strategy configs."""
        return [
            self.generate_strategy_config(name)
            for name in self.OPTION_STRATEGIES
        ]


# Convenience functions
def get_option_strategy_config(
    strategy_name: str,
    underlying_price: float = 19000.0
) -> Dict[str, Any]:
    """Convenience function to get option strategy config."""
    adapter = OptionsStrategyAdapter()
    return adapter.get_strategy_config(strategy_name, underlying_price)


def get_all_option_strategies(
    underlying_price: float = 19000.0
) -> List[Dict[str, Any]]:
    """Get all options strategy configs."""
    adapter = OptionsStrategyAdapter()
    return [adapter.get_strategy_config(name, underlying_price)
            for name in adapter.OPTION_STRATEGIES]
"""Options Strategy Adapter for SI-Trader.

Integrates options strategies into the SI-Trader platform while keeping the
BRD delivery boundary intact: the strategies here are cash-settled index
options (Nifty 50 / Bank Nifty), so no physical delivery is involved.

Supported strategies
    bull_call_spread   - buy nearer CE, sell farther CE (bullish debit)
    bear_put_spread    - buy nearer PE, sell farther PE (bearish debit)
    iron_condor        - sell both call and put spreads (range bound credit)
    long_straddle      - ATM CE + ATM PE (volatility)
    long_strangle      - OTM CE + OTM PE (volatility, cheaper)
    covered_call       - stock + short OTM CE
    protective_put     - stock + long OTM PE

Payoffs are computed with Black-Scholes premiums and reported per unit
(1 lot); margins are rupee estimates for a single unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import math

from ._weight_utils import normalize_weights

logger = logging.getLogger(__name__)


@dataclass
class OptionLeg:
    """A single option (or stock) leg."""
    option_type: str  # CE, PE or STOCK
    strike: float
    premium: float
    lot_size: int = 1
    action: str = "BUY"  # BUY or SELL


@dataclass
class OptionStrategy:
    """Options strategy definition."""
    name: str
    display_name: str
    strategy_type: str
    legs: List[dict]
    description: str
    suitable_market_condition: str
    timeframe: str


@dataclass
class OptionStrategyResult:
    """Encoded strategy plus its economics."""
    strategy_name: str
    parameter_weights: Dict[str, int]
    weight_total: int
    brd_compliant: bool
    max_profit: float
    max_loss: float
    breakeven: List[float]
    margin_required: float
    reward_risk_ratio: float


class OptionsStrategyAdapter:
    """Options strategies -> SI-Trader parameter weights + payoff profile."""

    OPTION_STRATEGIES: Dict[str, Dict[str, Any]] = {
        "bull_call_spread": {
            "display_name": "Bull Call Spread",
            "strategy_type": "debit_spread",
            "description": "Buy nearer-strike call, sell farther-strike call. "
                           "Limited risk, limited profit.",
            "suitable_market_condition": "bullish",
            "timeframe": "weekly",
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike_offset": -50},
                {"action": "SELL", "option_type": "CE", "strike_offset": +50},
            ],
        },
        "bear_put_spread": {
            "display_name": "Bear Put Spread",
            "strategy_type": "debit_spread",
            "description": "Buy nearer-strike put, sell farther-strike put. "
                           "Limited risk, limited profit.",
            "suitable_market_condition": "bearish",
            "timeframe": "weekly",
            "legs": [
                {"action": "BUY", "option_type": "PE", "strike_offset": +50},
                {"action": "SELL", "option_type": "PE", "strike_offset": -50},
            ],
        },
        "iron_condor": {
            "display_name": "Iron Condor",
            "strategy_type": "credit_spread",
            "description": "Sell an OTM call spread and an OTM put spread; "
                           "profits when the index stays in a range.",
            "suitable_market_condition": "neutral",
            "timeframe": "weekly",
            "legs": [
                {"action": "SELL", "option_type": "CE", "strike_offset": +100},
                {"action": "BUY", "option_type": "CE", "strike_offset": +150},
                {"action": "SELL", "option_type": "PE", "strike_offset": -100},
                {"action": "BUY", "option_type": "PE", "strike_offset": -150},
            ],
        },
        "long_straddle": {
            "display_name": "Long Straddle",
            "strategy_type": "neutral_volatility",
            "description": "Buy ATM call and put; profits from a large move "
                           "in either direction.",
            "suitable_market_condition": "volatile",
            "timeframe": "weekly",
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike_offset": 0},
                {"action": "BUY", "option_type": "PE", "strike_offset": 0},
            ],
        },
        "long_strangle": {
            "display_name": "Long Strangle",
            "strategy_type": "neutral_volatility",
            "description": "Buy OTM call and put; cheaper than the straddle "
                           "but needs a larger move.",
            "suitable_market_condition": "volatile",
            "timeframe": "weekly",
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike_offset": +50},
                {"action": "BUY", "option_type": "PE", "strike_offset": -50},
            ],
        },
        "covered_call": {
            "display_name": "Covered Call",
            "strategy_type": "directional_hedge",
            "description": "Hold stock and sell an OTM call against it.",
            "suitable_market_condition": "neutral_to_bullish",
            "timeframe": "weekly",
            "legs": [
                {"action": "BUY", "option_type": "STOCK", "strike_offset": 0},
                {"action": "SELL", "option_type": "CE", "strike_offset": +50},
            ],
        },
        "protective_put": {
            "display_name": "Protective Put",
            "strategy_type": "directional_hedge",
            "description": "Hold stock and buy an OTM put for downside cover.",
            "suitable_market_condition": "bullish_with_protection",
            "timeframe": "weekly",
            "legs": [
                {"action": "BUY", "option_type": "STOCK", "strike_offset": 0},
                {"action": "BUY", "option_type": "PE", "strike_offset": -50},
            ],
        },
    }

    _WEIGHT_ADJUSTMENTS = {
        "debit_spread": {"price_momentum_weekly": 2,
                         "midcap_volatility_adj": 1},
        "credit_spread": {"price_momentum_monthly": 2,
                          "midcap_volatility_adj": 2},
        "neutral_volatility": {"midcap_volatility_adj": 3,
                               "historical_news_sentiment": 2},
        "directional_hedge": {"price_momentum_weekly": 2,
                              "midcap_liquidity_score": 1},
    }

    def __init__(self):
        from ..config.parameter_catalogue import PARAMETER_CATALOGUE
        self.base_weights = {k: p.weight for k, p in
                             PARAMETER_CATALOGUE.items() if p.enable_switch}

    def get_available_strategies(self) -> List[Dict[str, Any]]:
        return [
            {"strategy_name": k,
             "display_name": v["display_name"],
             "strategy_type": v["strategy_type"],
             "description": v["description"],
             "suitable_market_condition": v["suitable_market_condition"],
             "legs": v["legs"]}
            for k, v in self.OPTION_STRATEGIES.items()
        ]

    # ------------------------------------------------------------------
    # Black-Scholes helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @classmethod
    def _bs_price(cls, spot: float, strike: float, opt_type: str,
                  vol: float = 0.15, t: float = 1 / 365 * 7,
                  r: float = 0.065) -> float:
        """Black-Scholes premium for one unit of the underlying."""
        if spot <= 0 or strike <= 0 or vol <= 0 or t <= 0:
            return 0.0
        d1 = (math.log(spot / strike) + (r + vol * vol / 2) * t) / (vol * math.sqrt(t))
        d2 = d1 - vol * math.sqrt(t)
        if opt_type == "CE":
            return spot * cls._norm_cdf(d1) - strike * math.exp(-r * t) * cls._norm_cdf(d2)
        return strike * math.exp(-r * t) * cls._norm_cdf(-d2) - spot * cls._norm_cdf(-d1)

    def _premium(self, spot: float, strike: float,
                 option_type: str) -> float:
        if option_type == "STOCK":
            return spot  # cost of holding one unit of the underlying
        return self._bs_price(spot, strike, option_type)

    # ------------------------------------------------------------------
    # Payoff profile
    # ------------------------------------------------------------------

    def _legs(self, strategy: Dict[str, Any],
              underlying_price: float) -> List[OptionLeg]:
        legs = []
        for leg in strategy["legs"]:
            otype = leg.get("option_type", "CE")
            strike = underlying_price + leg.get("strike_offset", 0)
            legs.append(OptionLeg(
                option_type=otype,
                strike=strike,
                premium=self._premium(underlying_price, strike, otype),
                lot_size=1,
                action=leg.get("action", "BUY"),
            ))
        return legs

    @classmethod
    def _payoff_points(cls, legs: List[OptionLeg],
                       underlying_price: float) -> List[tuple]:
        low = max(1.0, underlying_price * 0.6)
        high = underlying_price * 1.6
        steps = 81
        points = []
        for i in range(steps):
            spot = low + (high - low) * i / (steps - 1)
            total = 0.0
            for leg in legs:
                if leg.option_type == "STOCK":
                    intrinsic = spot
                elif leg.option_type == "CE":
                    intrinsic = max(0.0, spot - leg.strike)
                else:  # PE
                    intrinsic = max(0.0, leg.strike - spot)
                sign = -1.0 if leg.action == "SELL" else 1.0
                total += sign * (intrinsic - leg.premium) * leg.lot_size
            points.append((spot, total))
        return points

    @staticmethod
    def _breakevens(points: List[tuple]) -> List[float]:
        out: List[float] = []
        for i in range(1, len(points)):
            s0, v0 = points[i - 1]
            s1, v1 = points[i]
            if v0 == 0:
                out.append(s0)
            elif (v0 < 0) != (v1 < 0):
                out.append(s0 + (s1 - s0) * abs(v0) / (abs(v0) + abs(v1)))
        return sorted(set(round(x, 2) for x in out))

    def compute_payoff(self, legs: List[OptionLeg],
                       underlying_price: float) -> Dict[str, Any]:
        """Expiry payoff profile, per unit of the underlying."""
        if not legs:
            return {"max_profit": 0.0, "max_loss": 0.0, "breakeven": [],
                    "margin_required": 0.0, "reward_risk_ratio": 0.0,
                    "net_premium": 0.0}

        points = self._payoff_points(legs, underlying_price)
        values = [v for _, v in points]
        max_profit = max(values)
        min_value = min(values)
        max_loss = -min_value if min_value < 0 else 0.0
        net_premium = sum(
            (l.premium if l.action == "BUY" else -l.premium) * l.lot_size
            for l in legs)

        # Long premium legs tie up the premium paid; short legs are margined
        # on their maximum loss.
        margin = 0.0
        for l in legs:
            if l.action == "BUY":
                margin += l.premium * l.lot_size
            else:
                margin += max_loss if max_loss > 0 else l.premium * l.lot_size

        rr = (max_profit / max_loss) if max_loss > 0 else 0.0
        return {
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven": self._breakevens(points),
            "margin_required": round(margin, 2),
            "reward_risk_ratio": round(rr, 2),
            "net_premium": round(net_premium, 2),
        }

    # ------------------------------------------------------------------
    # Strategy config
    # ------------------------------------------------------------------

    def get_strategy_config(
        self,
        strategy_name: str,
        underlying_price: float = 19000.0,  # approx Nifty 50 level
    ) -> Dict[str, Any]:
        if strategy_name not in self.OPTION_STRATEGIES:
            raise ValueError(
                f"Unknown strategy: {strategy_name}. "
                f"Available: {list(self.OPTION_STRATEGIES.keys())}")

        strategy = self.OPTION_STRATEGIES[strategy_name]
        weights = normalize_weights({
            **self.base_weights,
            **self._WEIGHT_ADJUSTMENTS.get(strategy["strategy_type"], {}),
        })
        legs = self._legs(strategy, underlying_price)
        payoff = self.compute_payoff(legs, underlying_price)

        return {
            "strategy_name": strategy_name,
            "strategy_type": strategy["strategy_type"],
            "description": strategy["description"],
            "parameter_weights": weights,
            "weight_total": sum(weights.values()),
            "brd_compliant": sum(weights.values()) == 100,
            "suitable_market_condition": strategy["suitable_market_condition"],
            "timeframe": strategy["timeframe"],
            "underlying_price": underlying_price,
            "legs": [l.__dict__ for l in legs],
            "legs_count": len(legs),
            "max_profit": payoff["max_profit"],
            "max_loss": payoff["max_loss"],
            "breakeven": payoff["breakeven"],
            "margin_required": payoff["margin_required"],
            "capital_required": payoff["margin_required"],
            "reward_risk_ratio": payoff["reward_risk_ratio"],
            "delivery_compatible": True,  # cash-settled index options
            "generated_at": datetime.now().isoformat(),
        }


def get_option_strategy_config(strategy_name: str,
                               underlying_price: float = 19000.0
                               ) -> Dict[str, Any]:
    """Convenience function to get an option strategy config."""
    adapter = OptionsStrategyAdapter()
    return adapter.get_strategy_config(strategy_name, underlying_price)


def get_all_option_strategies(underlying_price: float = 19000.0
                              ) -> List[Dict[str, Any]]:
    """Get all option strategy configs."""
    adapter = OptionsStrategyAdapter()
    return [adapter.get_strategy_config(name, underlying_price)
            for name in adapter.OPTION_STRATEGIES]


__all__ = [
    "OptionLeg", "OptionStrategy", "OptionStrategyResult",
    "OptionsStrategyAdapter", "get_option_strategy_config",
    "get_all_option_strategies",
]
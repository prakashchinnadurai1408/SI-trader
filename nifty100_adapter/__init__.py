"""Nifty 100 Weekly Delivery Platform - Main package.

Configurable broker-agnostic platform for Indian algorithmic trading
strategies on Nifty 100 universe.

Key modules:
- broker: Adapter pattern for any broker (HDFC, Zerodha, Angel, Upstox, Fyers)
- config: Indian cost/tax model, parameter catalogue
- data: Market data, fundamentals, shareholding
- strategy: Scoring engine, backtester
- risk: Risk limits, kill switch, position sizing
- backtest: Weekly pipeline, historical testing
- ui: React frontend (to be built)
"""

from .config.indian_cost_model import IndianCostModel, get_cost_model
from .config.parameter_catalogue import (
    PARAMETER_CATALOGUE,
    get_enabled_parameters,
    get_total_weight,
    validate_weight_total,
)

__all__ = [
    "IndianCostModel",
    "get_cost_model",
    "PARAMETER_CATALOGUE",
    "get_enabled_parameters",
    "get_total_weight",
    "validate_weight_total",
]
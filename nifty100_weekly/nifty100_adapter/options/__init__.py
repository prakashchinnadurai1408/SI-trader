"""Options pricing, Greeks, and option chains for SI-Trader.

Provides Black-Scholes European option pricing, all Greeks (delta, gamma,
theta, vega, rho), implied volatility via bisection, full option-chain
construction, and payoff calculations. Dependency-free (stdlib math only).
"""

from .greeks import (
    OptionGreeks, OptionChainLink,
    black_scholes, implied_volatility,
    build_option_chain, payoff,
)

__all__ = [
    "OptionGreeks", "OptionChainLink",
    "black_scholes", "implied_volatility",
    "build_option_chain", "payoff",
]

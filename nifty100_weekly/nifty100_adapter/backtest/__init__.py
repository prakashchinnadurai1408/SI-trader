"""Backtesting engines for SI-Trader.

SI-Trader native weekly/monthly pipeline
    enhanced_backtester    - Phase 1 weekly selection pipeline (7-step)
    weekly_backtester      - weekly backtest runner
    monthly_backtester     - monthly backtest runner
    phase3_backtester      - Phase 3 simulator suite
    monthly_inputs         - monthly input assembly
    historical_intake      - historical data intake for backtests
    gate_g1                - G1 acceptance gate checks
    paper_pilot            - paper trading pilot runner

Research simulators
    monte_carlo_simulator   - 10K+ Monte Carlo edge simulations
    bootstrap_simulator     - non-parametric bootstrap resampling
    walk_forward_simulator  - rolling train/test with edge decay
    stress_test_simulator   - crash / high-vol / liquidity-freeze scenarios
    price_experiments       - price path experiments

External engine adapters
    vectorbt_adapter        - vectorised parameter sweeps (polakowo/vectorbt)
    backtrader_adapter      - event-driven backtesting (mementum/backtrader)
    compare_strategies     - side-by-side strategy comparison
"""

from .enhanced_backtester import Phase1Backtester
from .sitrader_strategy_backtester import (
    StrategyBacktester, StrategyBacktestResult, backtest_strategy,
)
from .vectorbt_adapter import VectorBTAdapter
from .backtrader_adapter import BacktraderAdapter

__all__ = [
    "Phase1Backtester",
    "StrategyBacktester",
    "StrategyBacktestResult",
    "backtest_strategy",
    "VectorBTAdapter",
    "BacktraderAdapter",
]
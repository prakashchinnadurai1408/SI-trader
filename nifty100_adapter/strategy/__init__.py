"""SI-Trader Strategy Layer - Universal Strategy Integration.

Exports all strategy integration modules:

- PKScreenerAdapter: Chart pattern detection -> parameter weight configuration
- AlgoIndiaAdapter: Indian trading strategies (breakout, momentum, etc.)
- UniversalStrategyHub: Combines all layers into unified strategy solution

Usage:
    from nifty100_weekly.nifty100_adapter.strategy import (
        PKScreenerAdapter, AlgoIndiaAdapter, UniversalStrategyHub,
        HubConfig, StrategyCandidate,
    )
"""

from .pkscreener_adapter import PKScreenerAdapter, PkScreenerConfig, PkScreenerSignal
from .algo_india_adapter import AlgoIndiaAdapter, AlgoIndiaConfig, AlgoIndiaStrategy
from .universal_hub import UniversalStrategyHub, HubConfig, StrategyCandidate

__all__ = [
    "PKScreenerAdapter",
    "PkScreenerConfig",
    "PkScreenerSignal",
    "AlgoIndiaAdapter",
    "AlgoIndiaConfig",
    "AlgoIndiaStrategy",
    "UniversalStrategyHub",
    "HubConfig",
    "StrategyCandidate",
]
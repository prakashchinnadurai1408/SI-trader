"""SI-Trader Strategy Layer - Universal Strategy Integration.

Exports all strategy integration modules:

- PKScreenerAdapter: Chart pattern detection -> parameter weight configuration
- AlgoIndiaAdapter: Indian trading strategies (breakout, momentum, etc.)
- UniversalStrategyHub: Combines all layers into unified strategy solution
- MACrossoverAdapter: Moving Average crossover strategies
- AIStrategyGenerator: AI/LLM-generated strategies
- OptionsStrategyAdapter: Options strategies (cash-settled indices)

Usage:
    from nifty100_weekly.nifty100_adapter.strategy import (
        PKScreenerAdapter, AlgoIndiaAdapter, UniversalStrategyHub,
        MACrossoverAdapter, AIStrategyGenerator, OptionsStrategyAdapter,
        HubConfig, StrategyCandidate,
    )
"""

from .pkscreener_adapter import PKScreenerAdapter, PkScreenerConfig, PkScreenerSignal
from .algo_india_adapter import AlgoIndiaAdapter, AlgoIndiaConfig, AlgoIndiaStrategy
from .universal_hub import UniversalStrategyHub, HubConfig, StrategyCandidate
from .ma_crossover_adapter import (
    MACrossoverAdapter, MACrossoverStrategy, MACrossoverResult,
    get_ma_strategy_config, get_all_ma_strategies,
)
from .ai_strategy_generator import (
    AIStrategyGenerator, StrategyIdea, StrategyGenerationResult,
)
from .llm_client import LLMClient, PROVIDERS, SUPPORTED_PROVIDERS
from .options_strategy_adapter import (
    OptionsStrategyAdapter, OptionLeg, OptionStrategy, OptionStrategyResult,
    get_option_strategy_config, get_all_option_strategies,
)

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
    "MACrossoverAdapter",
    "MACrossoverStrategy",
    "MACrossoverResult",
    "get_ma_strategy_config",
    "get_all_ma_strategies",
    "AIStrategyGenerator",
    "StrategyIdea",
    "StrategyGenerationResult",
    "LLMClient",
    "PROVIDERS",
    "SUPPORTED_PROVIDERS",
    "OptionsStrategyAdapter",
    "OptionLeg",
    "OptionStrategy",
    "OptionStrategyResult",
    "get_option_strategy_config",
    "get_all_option_strategies",
]
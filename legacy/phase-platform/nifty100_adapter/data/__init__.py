"""Data layer for SI-Trader.

Market data adapters and the data-quality pipeline:

Price & volume
    nse_price_adapter     - NSE price history, momentum/volatility/liquidity scoring
    jugaad_data_adapter   - jugaad-data NSE/BSE/RBI source with broker fallback
    historical_data_collector - multi-source historical OHLCV intake
    nifty100_universe     - Nifty 100 + midcap constituent universe
    nse_market            - live NSE market data helpers
    catalogue_evidence    - parameter evidence records

Fundamentals / shareholding / sentiment / regulatory
    fundamentals_adapter  - Piotroski F-Score, Altman Z-Score, PE, ROE, cash flow
    shareholding_adapter  - promoter holding/pledging, FII/DII/MF trend
    news_sentiment_adapter- NLP keyword sentiment scoring
    regulatory_adapter    - SEBI/RBI/NSE/BSE announcements, legal cases

Orchestration & validation
    data_source_catalogue - 48-parameter -> data source mapping
    pipeline_orchestrator - refresh scheduling across all adapters
    data_validator        - quality gates and quality scores

Every adapter below is optional-dependency safe: if its third-party package is
missing the adapter still imports and reports itself unavailable, so importing
`nifty100_adapter.data` never fails.
"""

from typing import Any, List


def _optional(name: str, attrs: List[str]) -> Any:
    """Import `attrs` from submodule `name`, returning None when unavailable."""
    try:
        module = __import__(f".{name}", fromlist=attrs)
        return tuple(getattr(module, a) for a in attrs)
    except Exception as exc:  # ImportError or missing optional dependency
        import logging
        logging.getLogger(__name__).debug(
            "data.%s unavailable (%s); related adapters disabled", name, exc)
        return tuple(None for _ in attrs)


(NSEPriceAdapter, PriceData, MomentumScore) = _optional(
    "nse_price_adapter", ["NSEPriceAdapter", "PriceData", "MomentumScore"])
(JugaadDataAdapter, MarketDataManager) = _optional(
    "jugaad_data_adapter", ["JugaadDataAdapter", "MarketDataManager"])
(FundamentalsAdapter, FinancialData, FundamentalScore) = _optional(
    "fundamentals_adapter",
    ["FundamentalsAdapter", "FinancialData", "FundamentalScore"])
(ShareholdingAdapter, ShareholdingData, ShareholdingScore) = _optional(
    "shareholding_adapter",
    ["ShareholdingAdapter", "ShareholdingData", "ShareholdingScore"])
(NewsSentimentAdapter, NewsSentimentResult) = _optional(
    "news_sentiment_adapter", ["NewsSentimentAdapter", "NewsSentimentResult"])
(RegulatoryAdapter, RegulatoryRiskScore) = _optional(
    "regulatory_adapter", ["RegulatoryAdapter", "RegulatoryRiskScore"])
(DataPipelineOrchestrator, DataRefreshResult, PipelineHealth) = _optional(
    "pipeline_orchestrator",
    ["DataPipelineOrchestrator", "DataRefreshResult", "PipelineHealth"])
(DataValidator, ValidationResult, ValidationReport) = _optional(
    "data_validator",
    ["DataValidator", "ValidationResult", "ValidationReport"])

# Pure-python modules with no third-party dependencies
from .parameter_store import (  # noqa: E402
    ParameterValueStore, ParameterValue,
)
from .data_source_catalogue import (  # noqa: E402
    DATA_SOURCES,
    PARAMETER_TO_DATA_SOURCE,
    DataSourceConfig,
    DataSourceType,
    RefreshSchedule,
    get_parameter_data_source,
)

__all__ = [
    "NSEPriceAdapter", "PriceData", "MomentumScore",
    "JugaadDataAdapter", "MarketDataManager",
    "FundamentalsAdapter", "FinancialData", "FundamentalScore",
    "ShareholdingAdapter", "ShareholdingData", "ShareholdingScore",
    "NewsSentimentAdapter", "NewsSentimentResult",
    "RegulatoryAdapter", "RegulatoryRiskScore",
    "DATA_SOURCES", "PARAMETER_TO_DATA_SOURCE", "DataSourceConfig",
    "ParameterValueStore", "ParameterValue",
    "DataSourceType", "RefreshSchedule", "get_parameter_data_source",
    "DataPipelineOrchestrator", "DataRefreshResult", "PipelineHealth",
    "DataValidator", "ValidationResult", "ValidationReport",
]
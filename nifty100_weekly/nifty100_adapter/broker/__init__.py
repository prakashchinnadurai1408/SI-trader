"""Broker module for SI-Trader.

Exposes the shared core types (``_init_``) plus broker gateway adapters:
OpenAlgo (multi-broker, AGPL v3.0), Kite Connect (Zerodha official) and
Fenix (15+ brokers). Adapters import lazily-safe so a missing optional
dependency never breaks the core types.
"""

from ._init_ import (
    OrderSide, OrderType, ProductType, OrderStatus, BrokerPlatform,
    BrokerConfig, OrderRequest, OrderResponse, Position,
    PortfolioSnapshot, BrokerAdapter,
)

try:
    from .openalgo_adapter import OpenAlgoAdapter
except Exception:  # pragma: no cover - optional dependency
    OpenAlgoAdapter = None

try:
    from .kite_connect_adapter import KiteConnectAdapter
except Exception:  # pragma: no cover - optional dependency
    KiteConnectAdapter = None

try:
    from .fenix_adapter import FenixAdapter
except Exception:  # pragma: no cover - optional dependency
    FenixAdapter = None

__all__ = [
    "OrderSide", "OrderType", "ProductType", "OrderStatus", "BrokerPlatform",
    "BrokerConfig", "OrderRequest", "OrderResponse", "Position",
    "PortfolioSnapshot", "BrokerAdapter",
    "OpenAlgoAdapter", "KiteConnectAdapter", "FenixAdapter",
]
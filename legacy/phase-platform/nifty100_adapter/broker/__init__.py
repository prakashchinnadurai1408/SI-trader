"""Broker module for SI-Trader.

Provides broker connectivity adapters:

- openalgo_adapter: OpenAlgo multi-broker gateway (AGPL v3.0)
- kite_connect_adapter: Zerodha Kite Connect official SDK
- fenix_adapter: Fenix lightweight multi-broker (15+ brokers)

All adapters implement the BrokerAdapter base class with standardised
OrderRequest/OrderResponse types for interoperability.
"""

from ._init_ import (
    BrokerConfig,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderType,
    ProductType,
    OrderStatus,
    BrokerPlatform,
    BrokerAdapter,
    Position,
    PortfolioSnapshot,
)
from .openalgo_adapter import OpenAlgoAdapter
from .kite_connect_adapter import KiteConnectAdapter
from .fenix_adapter import FenixAdapter

__all__ = [
    "BrokerConfig",
    "OrderRequest",
    "OrderResponse",
    "OrderSide",
    "OrderType",
    "ProductType",
    "OrderStatus",
    "BrokerPlatform",
    "BrokerAdapter",
    "Position",
    "PortfolioSnapshot",
    "OpenAlgoAdapter",
    "KiteConnectAdapter",
    "FenixAdapter",
]
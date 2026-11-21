"""Broker core types and adapter base class for SI-Trader.

Single source of truth for order/position/config abstractions shared by all
broker adapters (OpenAlgo, Kite Connect, Fenix, Zerodha, HDFC, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SLM"


class ProductType(Enum):
    CNC = "CNC"   # Cash and Carry - delivery (SI-Trader default)
    NRML = "NRML"  # Futures / options carry-forward
    MIS = "MIS"    # Intraday


class OrderStatus(Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    COMPLETE = "COMPLETE"


class BrokerPlatform(Enum):
    """Supported broker gateways."""
    ZERODHA_KITE = "zerodha_kite"
    OPEN_ALGO = "open_algo"        # Multi-broker gateway (AGPL v3.0)
    FENIX = "fenix"                # Lightweight multi-broker (15+)
    HDFC_SECURITIES = "hdfc_securities"
    ANGEL_ONE = "angel_one"
    UPSTOX = "upstox"
    FYERS = "fyers"


@dataclass
class BrokerConfig:
    """Broker API credentials and settings."""
    platform: BrokerPlatform = BrokerPlatform.ZERODHA_KITE
    client_id: str = ""
    api_key: str = ""
    secret_key: str = ""
    access_token: str = ""
    redirect_uri: str = ""
    base_url: str = ""
    enable_auto_order: bool = False
    static_ip_required: bool = True
    api_timeout: int = 30
    rate_limit_per_minute: int = 60


@dataclass
class OrderRequest:
    """Standardised order specification."""
    symbol: str
    action: OrderSide = OrderSide.BUY
    quantity: int = 1
    price: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    product: ProductType = ProductType.CNC
    validity: str = "DAY"
    tag: Optional[str] = None
    strategy_id: Optional[str] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None


@dataclass
class OrderResponse:
    """Broker execution result."""
    order_id: str
    algo_id: str
    status: OrderStatus = OrderStatus.OPEN
    filled_quantity: int = 0
    average_price: float = 0.0
    brokerage: float = 0.0
    exchange: str = "NSE"
    timestamp: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_filled(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.COMPLETE)

    @property
    def total_value(self) -> float:
        return self.filled_quantity * self.average_price


@dataclass
class Position:
    """Current holding in a stock."""
    symbol: str
    quantity: int
    average_price: float
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    product: ProductType = ProductType.CNC

    @property
    def total_value(self) -> float:
        return self.quantity * self.current_price

    def update_pnl(self, current_price: float) -> None:
        self.current_price = current_price
        self.pnl = (current_price - self.average_price) * self.quantity
        self.pnl_percent = (
            (current_price - self.average_price) / self.average_price * 100
            if self.average_price else 0.0
        )


@dataclass
class PortfolioSnapshot:
    """Portfolio state at a point in time."""
    total_capital: float = 25000.0
    available_cash: float = 25000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    daily_trades: int = 0
    weekly_trades: int = 0

    @property
    def position_count(self) -> int:
        return len(self.positions)

    def update_totals(self) -> None:
        self.total_pnl = sum(p.pnl for p in self.positions.values())
        if self.total_capital:
            self.total_pnl_percent = self.total_pnl / self.total_capital * 100
        self.available_cash = self.total_capital - sum(
            p.quantity * p.average_price for p in self.positions.values()
        )


class BrokerAdapter:
    """Base class every broker adapter implements."""

    def __init__(self, config: BrokerConfig):
        self.config = config
        self._connected = False
        self.account_id: Optional[str] = None

    def connect(self) -> bool:
        raise NotImplementedError

    def place_order(self, order: OrderRequest) -> Optional[OrderResponse]:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    def get_positions(self) -> List[Position]:
        raise NotImplementedError

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_historical_data(self, symbol: str, interval: str = "day",
                            from_date: str = "", to_date: str = "") -> List[Dict[str, Any]]:
        raise NotImplementedError

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False
        self.account_id = None

    def __repr__(self) -> str:
        platform = self.config.platform.value if hasattr(self.config, "platform") else "?"
        return f"{self.__class__.__name__}(platform={platform}, connected={self._connected})"


__all__ = [
    "OrderSide", "OrderType", "ProductType", "OrderStatus", "BrokerPlatform",
    "BrokerConfig", "OrderRequest", "OrderResponse", "Position",
    "PortfolioSnapshot", "BrokerAdapter",
]
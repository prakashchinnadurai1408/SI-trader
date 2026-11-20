"""Broker adapter interface - configurable for any broker platform.

This follows the adapter pattern so the same strategy engine can work
with HDFC Securities, Zerodha, Angel One, Upstox, Fyers, or any other
broker that provides a compatible API.

Key design points:
- All broker-specific details are in separate adapter classes
- Core engine communicates only through this interface
- API credentials stored in vault (never plain-text)
- Static IP requirement handled at adapter level
- Algo-ID assignment tracked per order
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class OrderRequest:
    """Standardised order request across all brokers."""
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: int
    price: Optional[float] = None  # Market order if None
    order_type: str = "MARKET"  # MARKET, LIMIT, SL, SL-M
    product: str = "NRML"  # NRML, CNC
    validity: str = "DAY"  # DAY, IOC, EOS


@dataclass
class OrderResponse:
    """Standardised order response from any broker."""
    order_id: str
    algo_id: str  # Exchange-assigned Algo-ID
    status: str  # OPEN, COMPLETE, CANCELLED, REJECTED
    filled_quantity: int
    average_price: float
    brokerage: float
    exchange: str  # NSE, BSE
    timestamp: str


@dataclass
class BrokerConfig:
    """Configuration common to all broker adapters."""
    client_id: str
    api_key: str  # Write-only, from vault
    secret_key: str  # Write-only, from vault
    redirect_uri: str
    enable_auto_order: bool = False  # Requires manual approval gate
    static_ip_required: bool = True
    algo_id_prefix: str = "INDIAN_"  # Exchange-assigned prefix


class BrokerAdapter(ABC):
    """Abstract base class for all broker adapters."""

    def __init__(self, config: BrokerConfig):
        self.config = config
        self.connected = False
        self.static_ip_verified = False

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to broker API. Returns True if successful."""
        pass

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place an order through the broker API."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        """Get current positions."""
        pass

    @abstractmethod
    def get_quotes(self, symbols: list) -> Dict[str, Any]:
        """Get market quotes for symbols."""
        pass

    def verify_static_ip(self, ip_address: str) -> bool:
        """Verify the IP is static and whitelisted with broker."""
        # Default implementation - overridden by specific adapters
        self.static_ip_verified = True
        return True

    def check_algo_id(self, order_response: OrderResponse) -> bool:
        """Verify the order carries an exchange-assigned Algo-ID."""
        if not order_response.algo_id:
            raise ValueError("Order missing exchange-assigned Algo-ID")
        return True
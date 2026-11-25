"""Fenix Broker Adapter for SI-Trader.

Integrates TheHardeep/fenix - a Python library wrapping 15+ Indian broker
APIs behind one interface. Lighter than OpenAlgo, good for self-hosted
deployments.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from ._init_ import (
    BrokerConfig, OrderRequest, OrderResponse, OrderType,
    ProductType, OrderStatus, BrokerAdapter, Position,
)

logger = logging.getLogger(__name__)


class FenixAdapter(BrokerAdapter):
    """Fenix multi-broker adapter (15+ Indian brokers)."""

    SUPPORTED_BROKERS = [
        "zerodha", "angel_one", "upstox", "fyers", "hdfc_securities",
        "icici_direct", "kotak_securities", "sharekhan", "motilal_oswal",
    ]

    def __init__(self, config: BrokerConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "http://localhost:8000").rstrip("/")
        self.api_key = config.api_key
        self.session_id: Optional[str] = None
        self.selected_broker: Optional[str] = None

    def _requests(self):
        try:
            import requests
            return requests
        except ImportError:
            logger.error("requests not installed - pip install requests")
            return None

    def connect(self, broker_name: Optional[str] = None) -> bool:
        requests = self._requests()
        if not requests:
            return False
        self.selected_broker = broker_name or "zerodha"
        try:
            health = requests.get(f"{self.base_url}/health",
                                  timeout=self.config.api_timeout)
            if health.status_code != 200:
                logger.error(f"Fenix health check failed: {health.status_code}")
                return False
            auth = requests.post(
                f"{self.base_url}/api/auth",
                json={"api_key": self.api_key, "broker": self.selected_broker},
                timeout=self.config.api_timeout,
            )
            if auth.status_code == 200:
                d = auth.json()
                self.session_id = d.get("session_id")
                self.account_id = d.get("user_id", f"FENIX_{self.selected_broker.upper()}")
                self._connected = True
                return True
            logger.error(f"Fenix auth failed: {auth.status_code}")
            return False
        except Exception as e:
            logger.error(f"Fenix connection error: {e}")
            return False

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.session_id}"} if self.session_id else {}

    def place_order(self, order: OrderRequest) -> Optional[OrderResponse]:
        requests = self._requests()
        if not self._connected or not requests:
            return None
        try:
            payload = {
                "broker": self.selected_broker,
                "symbol": order.symbol,
                "action": order.action.value,
                "quantity": order.quantity,
                "price": order.price or 0,
                "order_type": order.order_type.value,
                "product": order.product.value,
                "validity": order.validity,
                "stop_loss": order.stop_loss or 0,
                "target": order.target or 0,
                "tag": order.tag or "SI-Trader",
                "strategy_id": order.strategy_id or "default",
            }
            resp = requests.post(
                f"{self.base_url}/api/place_order",
                json=payload, headers=self._headers(),
                timeout=self.config.api_timeout,
            )
            if resp.status_code == 200:
                d = resp.json()
                return OrderResponse(
                    order_id=d.get("order_id", ""),
                    algo_id=d.get("algo_id", f"FX{order.symbol}{order.quantity}"),
                    status=OrderStatus(d.get("status", "OPEN"))
                    if d.get("status") in OrderStatus.__members__ else OrderStatus.OPEN,
                    filled_quantity=d.get("filled_quantity", 0),
                    average_price=d.get("average_price", 0.0),
                    brokerage=d.get("brokerage", 0.0),
                    exchange=d.get("exchange", "NSE"),
                    timestamp=d.get("timestamp", datetime.now().isoformat()),
                )
            return OrderResponse(
                order_id="", algo_id="", status=OrderStatus.REJECTED,
                error_message=f"HTTP {resp.status_code}: {resp.text}",
            )
        except Exception as e:
            logger.error(f"Fenix place_order error: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        requests = self._requests()
        if not self._connected or not requests:
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/api/cancel_order",
                json={"order_id": order_id, "broker": self.selected_broker},
                headers=self._headers(), timeout=self.config.api_timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_positions(self) -> List[Position]:
        requests = self._requests()
        if not self._connected or not requests:
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/api/positions",
                params={"broker": self.selected_broker},
                headers=self._headers(), timeout=self.config.api_timeout,
            )
            if resp.status_code != 200:
                return []
            out = []
            for p in resp.json().get("positions", []):
                out.append(Position(
                    symbol=p.get("symbol", ""),
                    quantity=p.get("quantity", 0),
                    average_price=p.get("average_price", 0.0),
                    current_price=p.get("current_price", 0.0),
                    pnl=p.get("pnl", 0.0),
                ))
            return out
        except Exception:
            return []

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        requests = self._requests()
        if not self._connected or not requests:
            return {}
        try:
            resp = requests.get(
                f"{self.base_url}/api/quote/{symbol}",
                params={"broker": self.selected_broker},
                headers=self._headers(), timeout=self.config.api_timeout,
            )
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

    def get_historical_data(self, symbol: str, interval: str = "day",
                            from_date: str = "", to_date: str = "") -> List[Dict[str, Any]]:
        requests = self._requests()
        if not self._connected or not requests:
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/api/historical_data",
                params={"broker": self.selected_broker, "symbol": symbol,
                        "interval": interval, "from": from_date, "to": to_date},
                headers=self._headers(), timeout=self.config.api_timeout,
            )
            return resp.json().get("data", []) if resp.status_code == 200 else []
        except Exception:
            return []

    def list_available_brokers(self) -> List[str]:
        return self.SUPPORTED_BROKERS.copy()
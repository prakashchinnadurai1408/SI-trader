"""Kite Connect Broker Adapter for SI-Trader.

Zerodha official client library (pykiteconnect) for the Kite Connect APIs.

Requires: api_key + api_secret from Zerodha developer console, and a valid
access_token obtained through the login flow (TOTP).
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


class KiteConnectAdapter(BrokerAdapter):
    """Zerodha Kite Connect adapter."""

    def __init__(self, config: BrokerConfig):
        super().__init__(config)
        self.api_secret = config.secret_key
        self.access_token = config.access_token
        self._kite = None

    def connect(self) -> bool:
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            logger.error("pykiteconnect not installed - pip install kiteconnect")
            return False
        try:
            self._kite = KiteConnect(api_key=self.config.api_key)
            self._kite.set_access_token(self.access_token)
            profile = self._kite.profile()
            self.account_id = profile.get("user_id", "ZERODHA_USER")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Kite Connect connection error: {e}")
            return False

    def _map_order_type(self, order_type: OrderType):
        if self._kite is None:
            return None
        return {
            OrderType.MARKET: self._kite.ORDER_TYPE_MARKET,
            OrderType.LIMIT: self._kite.ORDER_TYPE_LIMIT,
            OrderType.SL: self._kite.ORDER_TYPE_SL,
            OrderType.SLM: self._kite.ORDER_TYPE_SLM,
        }.get(order_type, self._kite.ORDER_TYPE_MARKET)

    def place_order(self, order: OrderRequest) -> Optional[OrderResponse]:
        if not self._connected or self._kite is None:
            return None
        try:
            txn = self._kite.TRANSACTION_TYPE_BUY if order.action.value == "BUY" \
                else self._kite.TRANSACTION_TYPE_SELL
            product = self._kite.PRODUCT_CNC if order.product == ProductType.CNC \
                else self._kite.PRODUCT_NRML
            validity = self._kite.VALIDITY_DAY if order.validity == "DAY" \
                else self._kite.VALIDITY_IOC

            params: Dict[str, Any] = {
                "tradingsymbol": order.symbol,
                "exchange": self._kite.EXCHANGE_NSE,
                "transaction_type": txn,
                "quantity": order.quantity,
                "order_type": self._map_order_type(order.order_type),
                "product": product,
                "validity": validity,
                "tag": order.tag or "SI-Trader",
            }
            if order.price is not None:
                params["price"] = order.price
            if order.stop_loss is not None:
                params["trigger_price"] = order.stop_loss

            order_id = self._kite.place_order(
                variety=self._kite.VARIETY_REGULAR, **params
            )
            return OrderResponse(
                order_id=str(order_id),
                algo_id=f"KITE{order.symbol}{order.quantity}"
                        f"{int(datetime.now().timestamp())}",
                status=OrderStatus.OPEN,
                average_price=order.price or 0.0,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.error(f"Kite place_order error: {e}")
            return OrderResponse(
                order_id="", algo_id="", status=OrderStatus.REJECTED,
                error_message=str(e),
            )

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected or self._kite is None:
            return False
        try:
            self._kite.cancel_order(variety=self._kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception:
            return False

    def get_positions(self) -> List[Position]:
        if not self._connected or self._kite is None:
            return []
        try:
            data = self._kite.positions()
            out = []
            for p in data.get("day", []):
                out.append(Position(
                    symbol=p.get("tradingsymbol", ""),
                    quantity=p.get("quantity", 0),
                    average_price=p.get("average_price", 0.0),
                    current_price=p.get("last_price", 0.0),
                    pnl=p.get("pnl", 0.0),
                    product=ProductType.CNC if p.get("product") == "CNC" else ProductType.NRML,
                ))
            return out
        except Exception:
            return []

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        if not self._connected or self._kite is None:
            return {}
        try:
            q = self._kite.quote([f"NSE:{symbol}"])
            return q.get(f"NSE:{symbol}", {})
        except Exception:
            return {}

    def get_historical_data(self, symbol: str, interval: str = "day",
                            from_date: str = "", to_date: str = "") -> List[Dict[str, Any]]:
        if not self._connected or self._kite is None:
            return []
        try:
            return self._kite.historical_data(
                instrument_token=symbol,
                from_date=from_date, to_date=to_date, interval=interval,
            )
        except Exception as e:
            logger.error(f"Kite historical_data error: {e}")
            return []

    def get_margins(self) -> Dict[str, Any]:
        if not self._connected or self._kite is None:
            return {}
        try:
            return self._kite.margins()
        except Exception:
            return {}
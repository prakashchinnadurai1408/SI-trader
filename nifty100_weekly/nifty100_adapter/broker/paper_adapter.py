"""Paper (mock) broker adapter for SI-Trader.

Provides a fully functional in-memory broker simulation so the complete
order flow (connect -> place order -> positions -> margins -> order book ->
trade fills) can be exercised end-to-end without live broker credentials.

Intended for paper trading, backtest-driven execution testing, and
demonstrations. All state is held in memory and resets on adapter restart.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import uuid

from ._init_ import (
    BrokerConfig, OrderRequest, OrderResponse, Order, Trade, Position,
    Margin, OrderSide, OrderType, ProductType, OrderStatus,
    BrokerAdapter, PortfolioSnapshot,
)
from ..webhooks import fire_webhooks

logger = logging.getLogger(__name__)


class PaperBrokerAdapter(BrokerAdapter):
    """In-memory paper broker adapter.

    Simulates market-order fills at the last quoted price. Maintains an
    order book, position ledger, margin snapshot, and trade history.
    Fires webhooks on order placement and trade execution when a
    webhook_store is configured.
    """

    def __init__(self, config: BrokerConfig, webhook_store=None):
        super().__init__(config)
        self.starting_cash = 25000.0
        self.available_cash = self.starting_cash
        self.used_margin = 0.0
        self._orders: Dict[str, Order] = {}
        self._trades: List[Trade] = []
        self._positions: Dict[str, Position] = {}
        self._quotes: Dict[str, Dict[str, Any]] = {}
        self._order_counter = 0
        self.webhook_store = webhook_store

    def connect(self) -> bool:
        self._connected = True
        self.account_id = "PAPER_USER"
        self.available_cash = self.starting_cash
        self.used_margin = 0.0
        self._orders.clear()
        self._trades.clear()
        self._positions.clear()
        self._order_counter = 0
        logger.info("Paper broker connected (account=%s)", self.account_id)
        return True

    def disconnect(self) -> None:
        self._connected = False
        self.account_id = None

    def set_quote(self, symbol: str, price: float) -> None:
        """Update the simulated last-traded price for a symbol."""
        self._quotes[symbol] = {
            "symbol": symbol,
            "last_price": price,
            "ohlc": {"close": price},
            "timestamp": datetime.now().isoformat(),
        }

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"PAPER{self._order_counter:06d}"

    def place_order(self, order: OrderRequest) -> Optional[OrderResponse]:
        if not self._connected:
            return OrderResponse(
                order_id="", algo_id="", status=OrderStatus.REJECTED,
                error_message="Paper broker not connected",
            )

        order_id = self._next_order_id()
        algo_id = f"PAPER{order.symbol}{order.quantity}{int(datetime.now().timestamp())}"

        quote = self._quotes.get(order.symbol, {})
        fill_price = order.price if order.price is not None else quote.get("last_price", 0.0)
        if fill_price <= 0:
            fill_price = 100.0  # fallback so the demo works without quotes

        total_value = order.quantity * fill_price
        commission = total_value * 0.0005  # 0.05% paper brokerage

        if order.action == OrderSide.BUY:
            if total_value + commission > self.available_cash:
                return OrderResponse(
                    order_id=order_id, algo_id=algo_id,
                    status=OrderStatus.REJECTED,
                    error_message="Insufficient cash",
                )
            self.available_cash -= (total_value + commission)
            self.used_margin += total_value

            pos = self._positions.get(order.symbol)
            if pos is None:
                pos = Position(
                    symbol=order.symbol, quantity=0, average_price=0.0,
                    current_price=fill_price, product=order.product,
                )
                self._positions[order.symbol] = pos
            new_qty = pos.quantity + order.quantity
            pos.average_price = (
                (pos.average_price * pos.quantity + fill_price * order.quantity)
                / new_qty if new_qty else 0.0
            )
            pos.quantity = new_qty
            pos.current_price = fill_price
            pos.update_pnl(fill_price)
        else:
            pos = self._positions.get(order.symbol)
            if pos is None or pos.quantity < order.quantity:
                return OrderResponse(
                    order_id=order_id, algo_id=algo_id,
                    status=OrderStatus.REJECTED,
                    error_message="Insufficient holdings",
                )
            self.available_cash += (total_value - commission)
            self.used_margin -= total_value
            pos.quantity -= order.quantity
            if pos.quantity == 0:
                del self._positions[order.symbol]
            else:
                pos.current_price = fill_price
                pos.update_pnl(fill_price)

        trade_id = f"TRADE{self._order_counter:06d}"
        trade = Trade(
            trade_id=trade_id, order_id=order_id, symbol=order.symbol,
            action=order.action, quantity=order.quantity, price=fill_price,
            timestamp=datetime.now().isoformat(), brokerage=commission,
        )
        self._trades.append(trade)

        order_rec = Order(
            order_id=order_id, algo_id=algo_id, symbol=order.symbol,
            action=order.action, quantity=order.quantity, price=fill_price,
            order_type=order.order_type, product=order.product,
            status=OrderStatus.FILLED, filled_quantity=order.quantity,
            average_price=fill_price, brokerage=commission,
            timestamp=datetime.now().isoformat(),
            stop_loss=order.stop_loss, target=order.target,
        )
        self._orders[order_id] = order_rec

        if self.webhook_store is not None:
            order_payload = {
                "order_id": order_id,
                "algo_id": algo_id,
                "symbol": order.symbol,
                "action": order.action.value,
                "quantity": order.quantity,
                "price": fill_price,
                "status": "FILLED",
                "timestamp": datetime.now().isoformat(),
            }
            trade_payload = {
                "trade_id": trade_id,
                "order_id": order_id,
                "symbol": order.symbol,
                "action": order.action.value,
                "quantity": order.quantity,
                "price": fill_price,
                "timestamp": datetime.now().isoformat(),
                "brokerage": commission,
            }
            fire_webhooks(self.webhook_store, "order.placed", order_payload)
            fire_webhooks(self.webhook_store, "trade.executed", trade_payload)

        return OrderResponse(
            order_id=order_id, algo_id=algo_id, status=OrderStatus.FILLED,
            filled_quantity=order.quantity, average_price=fill_price,
            brokerage=commission, exchange="NSE",
            timestamp=datetime.now().isoformat(),
        )

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            order_rec = self._orders[order_id]
            if not order_rec.is_filled:
                order_rec.status = OrderStatus.CANCELLED
                return True
        return False

    def get_positions(self) -> List[Position]:
        for symbol, pos in self._positions.items():
            quote = self._quotes.get(symbol, {})
            cur = quote.get("last_price", pos.average_price)
            pos.update_pnl(cur)
        return list(self._positions.values())

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return dict(self._quotes.get(symbol, {}))

    def get_historical_data(self, symbol: str, interval: str = "day",
                            from_date: str = "", to_date: str = "") -> List[Dict[str, Any]]:
        return []

    def get_margins(self) -> Optional[Margin]:
        return Margin(
            available_cash=self.available_cash,
            used_margin=self.used_margin,
            total_margin=self.starting_cash,
            exchange="NSE",
            segment="equity",
            timestamp=datetime.now().isoformat(),
        )

    def get_orders(self) -> List[Order]:
        return list(self._orders.values())

    def get_trades(self) -> List[Trade]:
        return list(self._trades)

    def snapshot(self) -> PortfolioSnapshot:
        snap = PortfolioSnapshot(
            total_capital=self.starting_cash,
            available_cash=self.available_cash,
            positions=dict(self._positions),
        )
        snap.update_totals()
        return snap


__all__ = ["PaperBrokerAdapter"]

"""Indian equity capital-gains and tax reporting (dependency-free).

Computes short-term (STCG) and long-term (LTCG) capital gains using FIFO
lot matching, and produces a Financial-Year (April-March) capital-gains
statement with tax liability.

Indian equity tax rules modelled:
- STCG (holding <= 12 months): 15%  (Section 111A)
- LTCG (holding > 12 months): 10% above Rs 1 lakh exemption (Section 112A)
  - No indexation benefit
  - Grandfathering not applied (pre-31-Jan-2018 cost treated as actual buy
    price for simplicity; production should use grandfathered cost)

All monetary values in INR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

# Indian equity tax rates
STCG_RATE = 0.15   # 15% short-term capital gains (equity, Section 111A)
LTCG_RATE = 0.10   # 10% long-term capital gains above 1 lakh (Section 112A)
LTCG_EXEMPTION = 100000.0  # Rs 1 lakh LTCG exemption per FY
LTCG_THRESHOLD_DAYS = 365  # > 12 months = long term


@dataclass
class TaxLot:
    """A buy lot awaiting (partial or full) sale matching."""
    buy_date: date
    symbol: str
    quantity: int
    buy_price: float
    brokerage: float = 0.0
    isin: Optional[str] = None

    @property
    def remaining(self) -> int:
        return self.quantity

    @property
    def total_cost(self) -> float:
        return self.quantity * self.buy_price + self.brokerage


@dataclass
class Trade:
    """A completed trade (buy or sell)."""
    trade_date: date
    symbol: str
    side: str            # "BUY" or "SELL"
    quantity: int
    price: float
    brokerage: float = 0.0
    isin: Optional[str] = None


@dataclass
class CapitalGain:
    """A single gain/loss lot result from a sale."""
    symbol: str
    sell_date: date
    buy_date: date
    quantity: int
    buy_price: float
    sell_price: float
    buy_brokerage: float
    sell_brokerage: float
    holding_days: int
    term: str              # "STCG" or "LTCG"
    gross_gain: float
    net_gain: float        # after brokerage on both legs
    tax: float             # tax payable on this lot

    def to_dict(self) -> Dict[str, object]:
        return {
            "symbol": self.symbol,
            "sell_date": self.sell_date.isoformat(),
            "buy_date": self.buy_date.isoformat(),
            "quantity": self.quantity,
            "buy_price": round(self.buy_price, 2),
            "sell_price": round(self.sell_price, 2),
            "buy_brokerage": round(self.buy_brokerage, 2),
            "sell_brokerage": round(self.sell_brokerage, 2),
            "holding_days": self.holding_days,
            "term": self.term,
            "gross_gain": round(self.gross_gain, 2),
            "net_gain": round(self.net_gain, 2),
            "tax": round(self.tax, 2),
        }


@dataclass
class FYStatement:
    """Financial-year capital-gains statement."""
    financial_year: str   # e.g. "FY2025-26"
    fy_start: date
    fy_end: date
    gains: List[CapitalGain] = field(default_factory=list)
    stcg_total: float = 0.0
    stcg_tax: float = 0.0
    ltcg_total: float = 0.0
    ltcg_tax: float = 0.0
    total_gain: float = 0.0
    total_tax: float = 0.0
    ltcg_exemption_used: float = 0.0

    @property
    def net_gain_after_tax(self) -> float:
        return self.total_gain - self.total_tax

    def to_dict(self) -> Dict[str, object]:
        return {
            "financial_year": self.financial_year,
            "fy_start": self.fy_start.isoformat(),
            "fy_end": self.fy_end.isoformat(),
            "stcg_total": round(self.stcg_total, 2),
            "stcg_tax": round(self.stcg_tax, 2),
            "ltcg_total": round(self.ltcg_total, 2),
            "ltcg_tax": round(self.ltcg_tax, 2),
            "ltcg_exemption_used": round(self.ltcg_exemption_used, 2),
            "total_gain": round(self.total_gain, 2),
            "total_tax": round(self.total_tax, 2),
            "net_gain_after_tax": round(self.net_gain_after_tax, 2),
            "num_gain_lots": len(self.gains),
            "gains": [g.to_dict() for g in self.gains],
        }


def _fy_for(d: date) -> str:
    """Financial year label for a date (April-March FY)."""
    year = d.year if d.month >= 4 else d.year - 1
    return f"FY{year}-{year + 1}"


def _fy_bounds(fy_label: str) -> tuple[date, date]:
    """Start and end dates for an FY label like 'FY2025-26'."""
    start_year = int(fy_label[2:6])
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def _classify(holding_days: int) -> str:
    return "LTCG" if holding_days > LTCG_THRESHOLD_DAYS else "STCG"


class CapitalGainsEngine:
    """FIFO lot-matching capital-gains engine.

    Processes trades in chronological order, maintaining buy lots per symbol.
    On a SELL, matches against the oldest buy lots first (FIFO), emitting a
    CapitalGain per matched lot with term classification and tax.
    """

    def __init__(self):
        self._buy_lots: Dict[str, List[TaxLot]] = {}
        self.gains: List[CapitalGain] = []

    def _lots_for(self, symbol: str) -> List[TaxLot]:
        return self._buy_lots.setdefault(symbol, [])

    def add_trade(self, trade: Trade) -> Optional[List[CapitalGain]]:
        """Add a trade. On SELL, emit CapitalGain lots (FIFO match)."""
        symbol = trade.symbol.upper()
        if trade.side.upper() == "BUY":
            self._lots_for(symbol).append(TaxLot(
                buy_date=trade.trade_date,
                symbol=symbol,
                quantity=trade.quantity,
                buy_price=trade.price,
                brokerage=trade.brokerage,
                isin=trade.isin,
            ))
            return None

        # SELL: FIFO match
        lots = self._lots_for(symbol)
        remaining = trade.quantity
        emitted: List[CapitalGain] = []
        i = 0
        while remaining > 0 and i < len(lots):
            lot = lots[i]
            if lot.remaining <= 0:
                i += 1
                continue
            match_qty = min(remaining, lot.remaining)
            sell_price = trade.price
            buy_price = lot.buy_price
            holding_days = (trade.trade_date - lot.buy_date).days
            term = _classify(holding_days)

            gross_gain = (sell_price - buy_price) * match_qty
            # Brokerage allocated pro-rata to matched quantity
            lot_brokerage = (lot.brokerage / lot.quantity) * match_qty if lot.quantity else 0.0
            sell_brokerage = (trade.brokerage / trade.quantity) * match_qty if trade.quantity else 0.0
            net_gain = gross_gain - lot_brokerage - sell_brokerage

            # Tax
            if term == "STCG":
                tax = max(net_gain, 0.0) * STCG_RATE
            else:
                tax = 0.0  # LTCG tax computed at FY level after exemption
            emitted.append(CapitalGain(
                symbol=symbol,
                sell_date=trade.trade_date,
                buy_date=lot.buy_date,
                quantity=match_qty,
                buy_price=buy_price,
                sell_price=sell_price,
                buy_brokerage=lot_brokerage,
                sell_brokerage=sell_brokerage,
                holding_days=holding_days,
                term=term,
                gross_gain=gross_gain,
                net_gain=net_gain,
                tax=tax,
            ))
            self.gains.append(emitted[-1])

            lot.quantity -= match_qty  # reduce lot remaining
            remaining -= match_qty
            if lot.remaining <= 0:
                i += 1

        return emitted

    def fy_statement(self, fy_label: str) -> FYStatement:
        """Build capital-gains statement for a financial year."""
        fy_start, fy_end = _fy_bounds(fy_label)
        stmt = FYStatement(
            financial_year=fy_label, fy_start=fy_start, fy_end=fy_end,
        )

        # Gains whose sell date falls in this FY
        fy_gains = [
            g for g in self.gains
            if fy_start <= g.sell_date <= fy_end
        ]
        stmt.gains = sorted(fy_gains, key=lambda g: g.sell_date)

        stcg_gains = [g for g in stmt.gains if g.term == "STCG"]
        ltcg_gains = [g for g in stmt.gains if g.term == "LTCG"]

        stmt.stcg_total = sum(g.net_gain for g in stcg_gains)
        stmt.stcg_tax = sum(g.tax for g in stcg_gains)

        # LTCG: aggregate net gain, apply 1 lakh exemption, tax at 10% on excess
        ltcg_net = sum(g.net_gain for g in ltcg_gains)
        stmt.ltcg_total = ltcg_net
        taxable_ltcg = max(ltcg_net - LTCG_EXEMPTION, 0.0)
        stmt.ltcg_exemption_used = min(ltcg_net, LTCG_EXEMPTION) if ltcg_net > 0 else 0.0
        stmt.ltcg_tax = taxable_ltcg * LTCG_RATE

        stmt.total_gain = stmt.stcg_total + stmt.ltcg_total
        stmt.total_tax = stmt.stcg_tax + stmt.ltcg_tax
        return stmt


def capital_gains_for_trades(
    trades: List[Trade],
    fy_label: str,
) -> FYStatement:
    """Convenience: process a list of trades and return the FY statement."""
    engine = CapitalGainsEngine()
    for t in trades:
        engine.add_trade(t)
    return engine.fy_statement(fy_label)


__all__ = [
    "STCG_RATE", "LTCG_RATE", "LTCG_EXEMPTION",
    "TaxLot", "Trade", "CapitalGain", "FYStatement",
    "CapitalGainsEngine", "capital_gains_for_trades",
]

"""Real-time data feed for SI-Trader.

Provides:
- PriceRegistry: thread-safe symbol -> last-traded price registry with
  timestamps. Broker adapters / feed adapters write into it; the dashboard
  reads from it.
- Intraday scanner: momentum breakout detection vs previous close across a
  watchlist.

Dependency-free (stdlib only). Designed so a websocket feed can be plugged
in later by writing into the same registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import threading


@dataclass
class Quote:
    """A single price quote."""
    symbol: str
    price: float
    previous_close: Optional[float] = None
    volume: Optional[int] = None
    timestamp: Optional[str] = None

    @property
    def change(self) -> Optional[float]:
        if self.previous_close is None:
            return None
        return self.price - self.previous_close

    @property
    def change_pct(self) -> Optional[float]:
        if self.previous_close is None or self.previous_close == 0:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "previous_close": self.previous_close,
            "change": self.change,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "timestamp": self.timestamp,
        }


class PriceRegistry:
    """Thread-safe in-memory price registry.

    Call `set_quote` whenever a feed/adapter produces a new tick.
    Call `get_quote` / `get_all_quotes` to read the latest snapshot.
    """

    def __init__(self):
        self._quotes: Dict[str, Quote] = {}
        self._lock = threading.Lock()

    def set_quote(
        self,
        symbol: str,
        price: float,
        previous_close: Optional[float] = None,
        volume: Optional[int] = None,
    ) -> Quote:
        q = Quote(
            symbol=symbol.upper(),
            price=price,
            previous_close=previous_close,
            volume=volume,
            timestamp=datetime.now().isoformat(),
        )
        with self._lock:
            self._quotes[q.symbol] = q
        return q

    def get_quote(self, symbol: str) -> Optional[Quote]:
        with self._lock:
            return self._quotes.get(symbol.upper())

    def get_all_quotes(self) -> List[Quote]:
        with self._lock:
            return list(self._quotes.values())

    def symbols(self) -> List[str]:
        with self._lock:
            return sorted(self._quotes.keys())

    def clear(self) -> None:
        with self._lock:
            self._quotes.clear()


def intraday_scan(
    registry: PriceRegistry,
    watchlist: List[str],
    breakout_pct: float = 1.0,
) -> Dict[str, object]:
    """Scan watchlist for intraday momentum breakouts.

    A stock "breaks out" when its current price is >= breakout_pct above
    its previous close. Returns breakouts ranked by change_pct descending.

    Args:
        registry: PriceRegistry with live quotes.
        watchlist: Symbols to scan.
        breakout_pct: Minimum % change to qualify as a breakout.
    """
    results = []
    for symbol in watchlist:
        q = registry.get_quote(symbol)
        if q is None or q.change_pct is None:
            continue
        if q.change_pct >= breakout_pct:
            results.append({
                "symbol": q.symbol,
                "price": q.price,
                "previous_close": q.previous_close,
                "change": q.change,
                "change_pct": q.change_pct,
                "volume": q.volume,
                "timestamp": q.timestamp,
            })
    results.sort(key=lambda r: r["change_pct"], reverse=True)
    return {
        "watchlist": watchlist,
        "breakout_pct": breakout_pct,
        "scanned": len(watchlist),
        "breakouts": results,
        "num_breakouts": len(results),
        "timestamp": datetime.now().isoformat(),
    }


__all__ = ["Quote", "PriceRegistry", "intraday_scan"]

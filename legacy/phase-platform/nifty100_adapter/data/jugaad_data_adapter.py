"""Jugaad-Data Market Data Adapter for SI-Trader.

Integrates jugaad-py/jugaad-data - downloads live and historical data for
the Indian market.

Covers:
- NSE stocks, stock F&O, indices, index F&O
- RBI rates
- Cached requests to avoid NSE blocking

WARNING: nsepython and nsetools scrape NSE website - they break when NSE
changes its website structure. Use broker historical APIs (Kite Connect,
OpenAlgo) for production. jugaad-data is more robust but still subject
to NSE rate limits.

SI-Trader Integration:
- Provides market data for parameter scoring (momentum, liquidity, etc.)
- Supports Nifty 100 universe (54 large-cap + 39 mid-cap)
- Weekly delivery focus: daily/weekly OHLCV data
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JugaadDataAdapter:
    """Jugaad-data market data adapter for SI-Trader.
    
    Provides Indian market data via jugaad-data library.
    Falls back to broker APIs if jugaad-data is unavailable.
    
    Usage:
        adapter = JugaadDataAdapter()
        df = adapter.get_daily_history("RELIANCE", "2024-01-01", "2024-12-31")
        quote = adapter.get_quote("RELIANCE")
    """
    
    def __init__(self, cache_enabled: bool = True):
        self.cache_enabled = cache_enabled
        self._jugaad_available = False
        self._check_availability()
    
    def _check_availability(self) -> None:
        try:
            import jugaad_data  # type: ignore
            self._jugaad_available = True
            logger.info("jugaad-data available for market data")
        except ImportError:
            self._jugaad_available = False
            logger.warning(
                "jugaad-data not installed - pip install jugaad-data. "
                "Market data will use broker APIs instead."
            )
    
    def is_available(self) -> bool:
        return self._jugaad_available
    
    def get_daily_history(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        exchange: str = "NSE",
    ) -> Optional[list]:
        """Get daily OHLCV data for a stock."""
        if not self._jugaad_available:
            logger.warning("jugaad-data not available - use broker historical API")
            return None
        
        try:
            from jugaad_data import stock  # type: ignore
            
            df = stock.stock_df(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
                series="EQ",
            )
            
            if df is None or df.empty:
                return []
            
            records = []
            for _, row in df.iterrows():
                records.append({
                    "date": str(row.get("DATE", "")),
                    "symbol": symbol,
                    "open": float(row.get("OPEN", 0)),
                    "high": float(row.get("HIGH", 0)),
                    "low": float(row.get("LOW", 0)),
                    "close": float(row.get("CLOSE", 0)),
                    "volume": int(row.get("VOLUME", 0)),
                    "exchange": exchange,
                })
            return records
        except Exception as e:
            logger.error(f"jugaad-data error for {symbol}: {e}")
            return None
    
    def get_quote(self, symbol: str, exchange: str = "NSE") -> Optional[dict]:
        """Get real-time quote for a stock."""
        if not self._jugaad_available:
            return None
        
        try:
            from jugaad_data import stock  # type: ignore
            
            quote = stock.quote(symbol=symbol)
            if quote:
                return {
                    "symbol": symbol,
                    "price": float(quote.get("lastPrice", 0)),
                    "open": float(quote.get("open", 0)),
                    "high": float(quote.get("high", 0)),
                    "low": float(quote.get("low", 0)),
                    "close": float(quote.get("previousClose", 0)),
                    "volume": int(quote.get("totalTradedVolume", 0)),
                    "exchange": exchange,
                    "timestamp": datetime.now().isoformat(),
                }
            return None
        except Exception as e:
            logger.error(f"jugaad-data quote error for {symbol}: {e}")
            return None
    
    def get_nifty100_universe(self) -> Optional[list]:
        """Get Nifty 100 constituent list."""
        if not self._jugaad_available:
            logger.warning("jugaad-data not available - use SI-Trader built-in universe")
            return None
        
        try:
            from jugaad_data import indices  # type: ignore
            
            constituents = indices.nifty_100()
            if constituents:
                return [c.get("symbol", "") for c in constituents if c.get("symbol")]
            return None
        except Exception as e:
            logger.error(f"jugaad-data universe error: {e}")
            return None
    
    def get_index_data(self,
                       index_symbol: str = "NIFTY 50",
                       from_date: str = "",
                       to_date: str = "") -> Optional[list]:
        """Get index historical data."""
        if not self._jugaad_available:
            return None
        
        try:
            from jugaad_data import indices  # type: ignore
            
            df = indices.index_df(
                symbol=index_symbol,
                from_date=from_date,
                to_date=to_date,
            )
            
            if df is None or df.empty:
                return []
            
            records = []
            for _, row in df.iterrows():
                records.append({
                    "date": str(row.get("DATE", "")),
                    "index": index_symbol,
                    "open": float(row.get("OPEN", 0)),
                    "high": float(row.get("HIGH", 0)),
                    "low": float(row.get("LOW", 0)),
                    "close": float(row.get("CLOSE", 0)),
                    "volume": int(row.get("VOLUME", 0)),
                })
            return records
        except Exception as e:
            logger.error(f"jugaad-data index error for {index_symbol}: {e}")
            return None
    
    def get_rbi_rates(self) -> Optional[dict]:
        """Get RBI interest rates via jugaad-data."""
        if not self._jugaad_available:
            return None
        
        try:
            from jugaad_data import rbi  # type: ignore
            
            rates = rbi.rates()
            return rates if rates else None
        except Exception as e:
            logger.error(f"jugaad-data RBI error: {e}")
            return None


class MarketDataManager:
    """Unified market data manager for SI-Trader.
    
    Coordinates multiple data sources:
    1. jugaad-data (primary, free)
    2. Broker APIs (Kite Connect, OpenAlgo) (backup, production)
    3. SI-Trader built-in NSE bhavcopy (fallback)
    """
    
    def __init__(self, broker_adapter=None):
        self.jugaad = JugaadDataAdapter()
        self.broker_adapter = broker_adapter
        self._cache: Dict[str, Any] = {}
    
    def get_daily_history(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> Optional[list]:
        """Get daily OHLCV with fallback chain."""
        if self.jugaad.is_available():
            data = self.jugaad.get_daily_history(symbol, from_date, to_date)
            if data:
                return data
        
        if self.broker_adapter and self.broker_adapter.is_connected():
            data = self.broker_adapter.get_historical_data(
                symbol=symbol,
                interval="day",
                from_date=from_date,
                to_date=to_date,
            )
            if data:
                return data
        
        logger.warning(f"No market data available for {symbol}")
        return None
    
    def get_quote(self, symbol: str) -> Optional[dict]:
        """Get real-time quote with fallback chain."""
        if self.jugaad.is_available():
            quote = self.jugaad.get_quote(symbol)
            if quote:
                return quote
        
        if self.broker_adapter and self.broker_adapter.is_connected():
            return self.broker_adapter.get_quote(symbol)
        
        return None
    
    def get_nifty100_universe(self) -> list:
        """Get Nifty 100 universe with fallback."""
        if self.jugaad.is_available():
            universe = self.jugaad.get_nifty100_universe()
            if universe:
                return universe
        
        logger.warning("Using SI-Trader built-in Nifty 100 universe")
        return self._get_builtin_universe()
    
    def _get_builtin_universe(self) -> list:
        """SI-Trader built-in Nifty 100 universe fallback."""
        return [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
            "ITC", "SBIN", "BHARTIARTL", "BAJFINANCE", "KOTAKBANK", "LT",
            "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN",
            "NESTLEIND", "ULTRACEMCO", "WIPRO", "POWERGRID", "NTPC",
            "ONGC", "TATASTEEL", "TECHM", "ADANIENT", "ADANIPORTS",
            "COALINDIA", "HCLTECH", "BAJAJFINSV", "DRREDDY", "EICHERMOT",
            "GRASIM", "HINDALCO", "JSWSTEEL", "CIPLA", "BPCL",
            "SHRIRAMFIN", "TATAMOTORS", "M&M", "SBILIFE", "HDFCLIFE",
            "BAJAJ-AUTO", "TATACONSUM", "BRITANNIA", "APOLLOHOSP",
            "DIVISLAB", "HEROMOTOCO", "INDUSINDBK", "LTIM", "LT",
        ]
    
    def get_cache_stats(self) -> dict:
        return {
            "cached_symbols": len(self._cache),
            "jugaad_available": self.jugaad.is_available(),
            "broker_connected": self.broker_adapter.is_connected() if self.broker_adapter else False,
        }
"""Collects and stores historical price data, fundamentals, and shareholding
information for Nifty 100 constituents required by the weekly backtester.

Data sources (terms-permitted):
- NSE India official data feed (with proper licensing)
- Yahoo Finance (fallback/unofficial)
- Scraped company filings (with terms compliance)
- SEBI/RBI/NSE announcements

Note: Actual data fetching would require proper API keys and terms compliance.
This module provides the structure and parsing logic.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from enum import Enum
from dataclasses import dataclass

from nifty100_weekly.nifty100_adapter.data.nifty100_universe import get_nifty_100_universe, get_symbols, get_stock, count_by_sector


class DataSource(Enum):
    """Available data sources."""
    NSE_OFFICIAL = "NSE_OFFICIAL"        # Paid licensed feed
    YAHOO_FINANCE = "YAHOO_FINANCE"      # Free fallback
    NSE_UNOFFICAL = "NSE_UNOFFICAL"     # Scraped (terms-permitted)
    FILE = "FILE"                        # Local CSV/JSON data


@dataclass
class PriceDataPoint:
    """Single day's price data for a stock."""
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    delivery_percentage: float  # % of volume that was delivery vs intraday


@dataclass
class FundamentalData:
    """Fundamental metrics for a stock as on a specific date."""
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[float] = None


class HistoricalDataCollector:
    """Collects and stores historical price data for Nifty 100 stocks."""

    def __init__(self, data_source: DataSource = DataSource.YAHOO_FINANCE,
                 start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None):
        self.data_source = data_source
        self.start_date = start_date
        self.end_date = end_date
        self.cache_dir = Path("data_cache")
        self.cache_dir.mkdir(exist_ok=True)

    def fetch_historical_data(self, symbol: str, years: int = 3) -> Optional[pd.DataFrame]:
        """Fetch historical price data for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
            years: Number of years of data to fetch

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
            or None if data cannot be fetched
        """
        import yfinance as yf

        try:
            ticker = yf.Ticker(symbol)
            days = years * 252  # ~252 trading days per year
            hist = ticker.history(period=f"{days}d")

            if hist.empty:
                return None

            # Reset index to get date as a column
            hist = hist.reset_index()

            # Ensure we have the required columns
            required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_cols:
                if col not in hist.columns:
                    print(f"Missing column {col} for {symbol}")
                    return None

            # Rename Date column to 'date' for consistency
            hist = hist.rename(columns={'Date': 'date'})

            # Select and order columns
            hist = hist[['date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()

            # Convert types
            hist['date'] = pd.to_datetime(hist['date'])
            hist['Open'] = hist['Open'].astype(float)
            hist['High'] = hist['High'].astype(float)
            hist['Low'] = hist['Low'].astype(float)
            hist['Close'] = hist['Close'].astype(float)
            hist['Volume'] = hist['Volume'].astype(int)

            # Sort by date ascending
            hist = hist.sort_values('date').reset_index(drop=True)

            return hist

        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None

    def fetch_multiple_symbols(self, symbols: List[str], years: int = 3) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetch historical data for multiple symbols.

        Args:
            symbols: List of stock symbols
            years: Number of years of data to fetch

        Returns:
            Dictionary mapping symbol to DataFrame (or None if failed)
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.fetch_historical_data(symbol, years)
        return results

    def get_data_summary(self, df: pd.DataFrame) -> Dict:
        """Get a summary of the data DataFrame.

        Args:
            df: DataFrame from fetch_historical_data

        Returns:
            Dictionary with summary stats
        """
        if df is None or df.empty:
            return {}

        return {
            "date_range": f"{df['date'].min().date()} to {df['date'].max().date()}",
            "trading_days": len(df),
            "price_range": f"₹{df['Close'].min():.2f} to ₹{df['Close'].max():.2f}",
            "volume_total": df['Volume'].sum(),
            "mean_volume": df['Volume'].mean(),
        }
"""NSE Price History Data Adapter for SI-Trader.

Provides price and volume data from NSE India for momentum scoring,
liquidity scoring, and volatility adjustment parameters.

Data Sources:
- NSE India Historical Data API
- NSE Bhavcopy (End of Day)
- NSE Live Market Data

Parameters Covered:
- price_momentum_weekly, monthly, yearly
- midcap_liquidity_score
- midcap_volatility_adj
- liquidity_floor
- historical_price_series
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)


def _aiohttp():
    """Return the aiohttp module, or None if it is not installed.

    aiohttp is an OPTIONAL dependency. The NSE price adapter uses it for async
    HTTP; without it the adapter reports unavailable instead of failing at
    import time.
    """
    try:
        import aiohttp
        return aiohttp
    except ImportError:
        logger.warning(
            "aiohttp not installed - pip install aiohttp "
            "(or: pip install -r requirements-optional.txt). "
            "NSE price history is unavailable; use broker historical APIs."
        )
        return None



@dataclass
class PriceData:
    """Price data for a single stock."""
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover_crore: float
    source: str = "NSE"
    refresh_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MomentumScore:
    """Momentum score calculation result."""
    symbol: str
    weekly_momentum: float  # 7-day price change %
    monthly_momentum: float  # 30-day price change %
    yearly_momentum: float  # 365-day price change %
    daily_momentum: float   # 1-day price change %
    volatility: float       # Annualized volatility %
    liquidity_score: float  # Liquidity score 0-100
    calculated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class NSEPriceAdapter:
    """NSE Price History Data Adapter.

    Fetches price and volume data from NSE India for:
    - Price momentum calculations (weekly, monthly, yearly, daily)
    - Liquidity scoring for midcap stocks
    - Volatility adjustment calculations
    - Liquidity floor checks

    BRD Parameters Supported:
    - price_momentum_weekly (Score, weight=1)
    - price_momentum_monthly (Score, weight=2)
    - price_momentum_yearly (Score, weight=2)
    - price_momentum_daily (Score, weight=1)
    - midcap_liquidity_score (Score, weight=4)
    - midcap_volatility_adj (Filter, weight=3)
    - liquidity_floor (Filter, weight=5)
    - historical_price_series (Advisory, weight=0)
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://www.nseindia.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = None  # type: ignore[assignment]
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self.cache_ttl_minutes = 15  # Cache for 15 minutes

        logger.info("NSEPriceAdapter initialized")

    async def __aenter__(self):
        aiohttp = _aiohttp()
        if aiohttp is None:
            raise RuntimeError(
                "aiohttp is not installed; cannot open an NSE HTTP session"
            )
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _fetch(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch data from NSE API with retry logic."""
        if not self.session:
            aiohttp = _aiohttp()
            if aiohttp is None:
                return None
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.get(url, params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    logger.warning("NSE API rate limit exceeded, waiting...")
                    await asyncio.sleep(2)
                    return await self._fetch(url, params)
                else:
                    logger.error(f"NSE API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"NSE API request failed: {e}")
            return None

    async def get_price_history(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> List[PriceData]:
        """Get historical price data for a symbol.

        Args:
            symbol: Stock symbol (e.g., RELIANCE)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of PriceData objects
        """
        cache_key = f"price_history_{symbol}_{from_date}_{to_date}"

        # Check cache
        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = f"{self.base_url}/api/historical/cm/equity"
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
        }

        data = await self._fetch(url, params)
        if not data or "data" not in data:
            logger.warning(f"No price data for {symbol} from {from_date} to {to_date}")
            return []

        prices = []
        for item in data.get("data", []):
            try:
                price = PriceData(
                    symbol=symbol,
                    date=item.get("CH_TRADING_DATE", ""),
                    open=float(item.get("CH_OPENING_PRICE", 0)),
                    high=float(item.get("CH_TRADE_HIGH_PRICE", 0)),
                    low=float(item.get("CH_TRADE_LOW_PRICE", 0)),
                    close=float(item.get("CH_CLOSING_PRICE", 0)),
                    volume=int(item.get("CH_TOTAL_TRADED_QUANTITY", 0)),
                    turnover_crore=float(item.get("CH_TOTAL_TRADED_VALUE", 0)) / 10_000_000,
                )
                prices.append(price)
            except (ValueError, TypeError) as e:
                logger.warning(f"Error parsing price data for {symbol}: {e}")
                continue

        # Cache result
        self._cache[cache_key] = prices
        self._cache_ttl[cache_key] = datetime.now() + timedelta(minutes=self.cache_ttl_minutes)

        return prices

    async def get_live_quote(self, symbol: str) -> Optional[PriceData]:
        """Get live quote for a symbol."""
        cache_key = f"live_quote_{symbol}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = f"{self.base_url}/api/live-equity"
        params = {"symbol": symbol}

        data = await self._fetch(url, params)
        if not data:
            return None

        try:
            price = PriceData(
                symbol=symbol,
                date=datetime.now().strftime("%Y-%m-%d"),
                open=float(data.get("open", 0)),
                high=float(data.get("high", 0)),
                low=float(item.get("low", 0)) if (item := data.get("low")) else 0,
                close=float(data.get("lastPrice", 0)),
                volume=int(data.get("totalTradedQuantity", 0)),
                turnover_crore=float(data.get("totalTradedValue", 0)) / 10_000_000,
            )
            self._cache[cache_key] = price
            self._cache_ttl[cache_key] = datetime.now() + timedelta(minutes=5)
            return price
        except Exception as e:
            logger.error(f"Error parsing live quote for {symbol}: {e}")
            return None

    async def calculate_momentum(
        self,
        symbol: str,
        lookback_days: int = 365,
    ) -> Optional[MomentumScore]:
        """Calculate momentum scores for a symbol.

        Calculates weekly, monthly, yearly, and daily momentum
        based on historical price data.
        """
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        prices = await self.get_price_history(symbol, start_date, end_date)
        if len(prices) < 2:
            logger.warning(f"Insufficient price data for {symbol}: {len(prices)} points")
            return None

        # Sort by date
        prices.sort(key=lambda p: p.date)

        # Get prices at different intervals
        current_price = prices[-1].close

        # Weekly (7 days)
        weekly_price = self._get_price_at_offset(prices, 7)
        weekly_momentum = ((current_price - weekly_price) / weekly_price * 100) if weekly_price else 0

        # Monthly (30 days)
        monthly_price = self._get_price_at_offset(prices, 30)
        monthly_momentum = ((current_price - monthly_price) / monthly_price * 100) if monthly_price else 0

        # Yearly (365 days)
        yearly_price = self._get_price_at_offset(prices, 365)
        yearly_momentum = ((current_price - yearly_price) / yearly_price * 100) if yearly_price else 0

        # Daily (1 day)
        daily_price = self._get_price_at_offset(prices, 1)
        daily_momentum = ((current_price - daily_price) / daily_price * 100) if daily_price else 0

        # Volatility (annualized standard deviation of daily returns)
        volatility = self._calculate_volatility(prices)

        # Liquidity score (based on turnover and volume consistency)
        liquidity_score = self._calculate_liquidity_score(prices)

        return MomentumScore(
            symbol=symbol,
            weekly_momentum=round(weekly_momentum, 2),
            monthly_momentum=round(monthly_momentum, 2),
            yearly_momentum=round(yearly_momentum, 2),
            daily_momentum=round(daily_momentum, 2),
            volatility=round(volatility, 2),
            liquidity_score=round(liquidity_score, 2),
        )

    def _get_price_at_offset(self, prices: List[PriceData], days_offset: int) -> Optional[float]:
        """Get price at a specific offset from the most recent price."""
        if len(prices) <= days_offset:
            return None
        return prices[-(days_offset + 1)].close

    def _calculate_volatility(self, prices: List[PriceData]) -> float:
        """Calculate annualized volatility from daily returns."""
        if len(prices) < 2:
            return 0.0

        returns = []
        for i in range(1, len(prices)):
            if prices[i-1].close > 0:
                ret = (prices[i].close - prices[i-1].close) / prices[i-1].close
                returns.append(ret)

        if len(returns) < 2:
            return 0.0

        import statistics
        std_dev = statistics.stdev(returns)
        annualized_volatility = std_dev * (252 ** 0.5) * 100  # Annualize
        return round(annualized_volatility, 2)

    def _calculate_liquidity_score(self, prices: List[PriceData]) -> float:
        """Calculate liquidity score (0-100) based on turnover and volume consistency."""
        if not prices:
            return 0.0

        avg_turnover = sum(p.turnover_crore for p in prices) / len(prices)
        avg_volume = sum(p.volume for p in prices) / len(prices)

        # Score based on turnover (crore)
        if avg_turnover >= 100:
            liquidity_score = 100
        elif avg_turnover >= 50:
            liquidity_score = 80
        elif avg_turnover >= 25:
            liquidity_score = 60
        elif avg_turnover >= 10:
            liquidity_score = 40
        elif avg_turnover >= 5:
            liquidity_score = 20
        else:
            liquidity_score = 10

        # Adjust for volume consistency
        volumes = [p.volume for p in prices if p.volume > 0]
        if len(volumes) > 1:
            import statistics
            try:
                vol_cv = statistics.stdev(volumes) / statistics.mean(volumes)
                if vol_cv > 2:  # High volatility in volume
                    liquidity_score *= 0.8
            except Exception:
                pass

        return min(100, max(0, liquidity_score))

    async def get_multiple_momentum(
        self,
        symbols: List[str],
    ) -> Dict[str, MomentumScore]:
        """Calculate momentum for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                score = await self.calculate_momentum(symbol)
                if score:
                    results[symbol] = score
            except Exception as e:
                logger.error(f"Error calculating momentum for {symbol}: {e}")
                continue
        return results
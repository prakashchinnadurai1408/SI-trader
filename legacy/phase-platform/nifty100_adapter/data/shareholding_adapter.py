"""NSE Shareholding Data Adapter for SI-Trader.

Provides shareholding pattern data from NSE India for:
- Promoter Holding %
- Promoter Pledging %
- FII/DII/MF Trend

Data Sources:
- NSE Shareholding Pattern API
- NSE Institutional Flows API

Parameters Covered:
- promoter_holding_pct (Filter, weight=4, quarterly)
- promoter_pledging_pct (Veto, weight=3, quarterly)
- fii_dii_mf_trend (Score, weight=3, weekly)
- ownership_breakdown (Advisory, weight=0, quarterly - disabled)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ShareholdingData:
    """Shareholding data for a company."""
    symbol: str
    reporting_period: str
    report_date: str

    # Promoter holding
    promoter_holding_pct: float = 0.0
    promoter_pledged_pct: float = 0.0
    promoter_pledged_of_holding: float = 0.0  # % of promoter holding pledged

    # Institutional holdings
    fii_holding_pct: float = 0.0
    dii_holding_pct: float = 0.0
    mf_holding_pct: float = 0.0

    # Public holding
    public_holding_pct: float = 0.0
    other_holding_pct: float = 0.0

    # Institutional flows (weekly)
    fii_net_flow_crore: float = 0.0
    dii_net_flow_crore: float = 0.0
    mf_net_flow_crore: float = 0.0

    source: str = "NSE"
    refresh_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ShareholdingScore:
    """Shareholding score calculation result."""
    symbol: str
    promoter_holding_pct: float
    promoter_pledging_pct: float
    fii_dii_mf_trend: float  # Net institutional flow score
    promoter_pledge_risk: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    institutional_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    calculated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class ShareholdingAdapter:
    """NSE Shareholding Data Adapter.

    Fetches shareholding data from NSE India for:
    - Promoter Holding %
    - Promoter Pledging %
    - FII/DII/MF Trend

    BRD Parameters Supported:
    - promoter_holding_pct (Filter, weight=4, quarterly)
    - promoter_pledging_pct (Veto, weight=3, quarterly)
    - fii_dii_mf_trend (Score, weight=3, weekly)
    - ownership_breakdown (Advisory, weight=0, quarterly - disabled)
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://www.nseindia.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self.cache_ttl_hours = 24

        logger.info("ShareholdingAdapter initialized")

    async def __aenter__(self):
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

    async def get_shareholding_data(self, symbol: str) -> Optional[ShareholdingData]:
        """Get shareholding data for a symbol.

        Args:
            symbol: Stock symbol (e.g., RELIANCE)

        Returns:
            ShareholdingData object or None
        """
        cache_key = f"shareholding_{symbol}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = f"{self.base_url}/api/corporate-shareholding"
        params = {"symbol": symbol}

        data = await self._fetch(url, params)
        if not data:
            logger.warning(f"No shareholding data for {symbol}")
            return None

        try:
            share_data = data.get("data", {})
            if isinstance(share_data, list) and len(share_data) > 0:
                latest = share_data[0]
            elif isinstance(share_data, dict):
                latest = share_data
            else:
                return None

            sh = ShareholdingData(
                symbol=symbol,
                reporting_period=latest.get("period", ""),
                report_date=latest.get("date", ""),
                promoter_holding_pct=float(latest.get("promoterHolding", 0)),
                promoter_pledged_pct=float(latest.get("promoterPledged", 0)),
                fii_holding_pct=float(latest.get("fiiHolding", 0)),
                dii_holding_pct=float(latest.get("diiHolding", 0)),
                mf_holding_pct=float(latest.get("mfHolding", 0)),
                public_holding_pct=float(latest.get("publicHolding", 0)),
            )

            # Calculate pledged % of promoter holding
            if sh.promoter_holding_pct > 0:
                sh.promoter_pledged_of_holding = (sh.promoter_pledged_pct / sh.promoter_holding_pct) * 100

            # Cache result
            self._cache[cache_key] = sh
            self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=self.cache_ttl_hours)

            return sh

        except Exception as e:
            logger.error(f"Error parsing shareholding data for {symbol}: {e}")
            return None

    async def get_institutional_flows(self, symbol: str) -> Optional[Dict[str, float]]:
        """Get FII/DII/MF flow data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with fii_net, dii_net, mf_net in crore
        """
        cache_key = f"flows_{symbol}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = f"{self.base_url}/api/fii-dii-data"
        params = {"symbol": symbol}

        data = await self._fetch(url, params)
        if not data:
            return None

        try:
            flows = data.get("data", {})
            if isinstance(flows, list) and len(flows) > 0:
                latest = flows[0]
            elif isinstance(flows, dict):
                latest = flows
            else:
                return None

            result = {
                "fii_net_crore": float(latest.get("fiiNet", 0)),
                "dii_net_crore": float(latest.get("diiNet", 0)),
                "mf_net_crore": float(latest.get("mfNet", 0)),
            }

            self._cache[cache_key] = result
            self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=6)  # Flows update more frequently

            return result

        except Exception as e:
            logger.error(f"Error parsing institutional flows for {symbol}: {e}")
            return None

    def calculate_shareholding_score(self, sh: ShareholdingData,
                                     flows: Optional[Dict[str, float]] = None) -> ShareholdingScore:
        """Calculate shareholding scores.

        Evaluates:
        - Promoter holding adequacy
        - Promoter pledging risk
        - Institutional flow trend
        """
        # Promoter pledging risk assessment
        if sh.promoter_pledged_pct == 0:
            pledge_risk = "LOW"
        elif sh.promoter_pledged_pct <= 10:
            pledge_risk = "MEDIUM"
        elif sh.promoter_pledged_pct <= 25:
            pledge_risk = "HIGH"
        else:
            pledge_risk = "CRITICAL"

        # Institutional trend
        fii_net = flows.get("fii_net_crore", 0) if flows else 0
        dii_net = flows.get("dii_net_crore", 0) if flows else 0
        mf_net = flows.get("mf_net_crore", 0) if flows else 0

        net_flow = fii_net + dii_net + mf_net

        if net_flow > 100:
            inst_trend = "BULLISH"
        elif net_flow > 0:
            inst_trend = "NEUTRAL_POSITIVE"
        elif net_flow > -100:
            inst_trend = "NEUTRAL_NEGATIVE"
        else:
            inst_trend = "BEARISH"

        # FII/DII/MF trend score (0-100)
        trend_score = 50  # Neutral baseline
        if net_flow > 200:
            trend_score = 80
        elif net_flow > 100:
            trend_score = 70
        elif net_flow > 0:
            trend_score = 60
        elif net_flow > -100:
            trend_score = 50
        elif net_flow > -200:
            trend_score = 40
        else:
            trend_score = 30

        return ShareholdingScore(
            symbol=sh.symbol,
            promoter_holding_pct=sh.promoter_holding_pct,
            promoter_pledging_pct=sh.promoter_pledged_pct,
            fii_dii_mf_trend=trend_score,
            promoter_pledge_risk=pledge_risk,
            institutional_trend=inst_trend,
        )

    async def get_shareholding_score(self, symbol: str) -> Optional[ShareholdingScore]:
        """Get complete shareholding score for a symbol."""
        sh = await self.get_shareholding_data(symbol)
        if not sh:
            return None

        flows = await self.get_institutional_flows(symbol)
        return self.calculate_shareholding_score(sh, flows)

    async def get_multiple_scores(self, symbols: List[str]) -> Dict[str, ShareholdingScore]:
        """Get shareholding scores for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                score = await self.get_shareholding_score(symbol)
                if score:
                    results[symbol] = score
            except Exception as e:
                logger.error(f"Error calculating shareholding score for {symbol}: {e}")
                continue
        return results
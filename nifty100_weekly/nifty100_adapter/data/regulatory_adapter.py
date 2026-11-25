"""Regulatory Announcements Data Adapter for SI-Trader.

Provides SEBI/RBI/NSE/BSE announcements and circulars for regulatory risk scoring.

Data Sources:
- SEBI (Securities and Exchange Board of India)
- RBI (Reserve Bank of India)
- NSE (National Stock Exchange)
- BSE (Bombay Stock Exchange)

Parameters Covered:
- regulatory_actions (Veto, weight=6, on-event)
- government_news (Market dial, weight=0, on-event - disabled)
- political_incidents (Flag, weight=0, on-event - disabled)
- regulator_announcements (Flag, weight=0, on-event - disabled)
- company_collaborations (Flag, weight=0, on-event - disabled)
- legal_cases_company_promoters (Veto, weight=0, on-event - disabled)
- auditor_resignations (Veto, weight=0, on-event - disabled)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import asyncio
try:
    import aiohttp
except ImportError:  # optional dependency
    aiohttp = None

logger = logging.getLogger(__name__)

def _require_aiohttp():
    """Raise a clear error when the optional aiohttp dependency is missing."""
    if aiohttp is None:
        raise RuntimeError(
            "aiohttp is not installed; install optional dependencies with "
            "`pip install -r requirements-optional.txt`"
        )



@dataclass
class RegulatoryAnnouncement:
    """Single regulatory announcement."""
    title: str
    description: str
    authority: str  # SEBI, RBI, NSE, BSE
    announcement_type: str  # circular, notification, press_release, order
    published_date: str
    effective_date: Optional[str]
    url: str
    affected_sectors: List[str] = field(default_factory=list)
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    relevance_score: float = 0.0  # 0 to 1


@dataclass
class RegulatoryRiskScore:
    """Regulatory risk assessment result."""
    symbol: str
    company_name: str
    regulatory_risk_score: float  # 0-100 (higher = more risk)
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    active_actions: int
    recent_announcements: List[RegulatoryAnnouncement]
    legal_cases_count: int
    auditor_resignations_count: int
    calculated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.regulatory_risk_score >= 70:
            self.risk_level = "CRITICAL"
        elif self.regulatory_risk_score >= 50:
            self.risk_level = "HIGH"
        elif self.regulatory_risk_score >= 30:
            self.risk_level = "MEDIUM"
        else:
            self.risk_level = "LOW"


class RegulatoryAdapter:
    """Regulatory Announcements Data Adapter.

    Fetches regulatory announcements from SEBI, RBI, NSE, BSE for:
    - Legal cases against directors/promoters
    - Auditor resignations
    - Corporate actions affecting stocks
    - Regulatory actions that may impact stocks

    Parameters Covered:
    - regulatory_actions (Veto, weight=6, on-event)
    - legal_cases_directors (Veto, weight=6, on-event)
    - credit_rating_changes (Veto, weight=5, on-event)
    - legal_cases_company_promoters (Veto, weight=0, on-event - disabled)
    - auditor_resignations (Veto, weight=0, on-event - disabled)
    - company_collaborations (Flag, weight=0, on-event - disabled)
    - government_news (Market dial, weight=0, on-event - disabled)
    - political_incidents (Flag, weight=0, on-event - disabled)
    - regulator_announcements (Flag, weight=0, on-event - disabled)
    """

    def __init__(self, sebi_api_key: Optional[str] = None,
                 rbi_api_key: Optional[str] = None,
                 nse_api_key: Optional[str] = None,
                 bse_api_key: Optional[str] = None):
        self.api_keys = {
            "SEBI": sebi_api_key,
            "RBI": rbi_api_key,
            "NSE": nse_api_key,
            "BSE": bse_api_key,
        }
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self.cache_ttl_hours = 6

        logger.info("RegulatoryAdapter initialized")

    async def __aenter__(self):
        _require_aiohttp()
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _fetch(self, url: str, params: Optional[Dict] = None,
                     headers: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch data from regulatory API with retry logic."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = headers or {}

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    logger.warning(f"Regulatory API rate limit exceeded, waiting...")
                    await asyncio.sleep(2)
                    return await self._fetch(url, params, headers)
                else:
                    logger.error(f"Regulatory API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Regulatory API request failed: {e}")
            return None

    async def get_sebi_announcements(self, symbol: Optional[str] = None,
                                     days: int = 30) -> List[RegulatoryAnnouncement]:
        """Get SEBI announcements that may affect a symbol or market.

        Args:
            symbol: Stock symbol (optional, for company-specific announcements)
            days: Number of days to look back

        Returns:
            List of RegulatoryAnnouncement objects
        """
        cache_key = f"sebi_{symbol or 'all'}_{days}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = "https://www.sebi.gov.in/api/announcements"
        params = {
            "from_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to_date": datetime.now().strftime("%Y-%m-%d"),
        }

        if self.api_keys.get("SEBI"):
            headers = {"Authorization": f"Bearer {self.api_keys['SEBI']}"}
        else:
            headers = {}

        data = await self._fetch(url, params, headers)
        if not data or "announcements" not in data:
            logger.warning("No SEBI announcements found")
            return []

        announcements = []
        for item in data.get("announcements", []):
            try:
                ann = RegulatoryAnnouncement(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    authority="SEBI",
                    announcement_type=item.get("type", "circular"),
                    published_date=item.get("publishedDate", ""),
                    effective_date=item.get("effectiveDate"),
                    url=item.get("url", ""),
                    affected_sectors=item.get("affectedSectors", []),
                    severity=item.get("severity", "MEDIUM"),
                    relevance_score=self._calculate_relevance(item, symbol),
                )
                announcements.append(ann)
            except Exception as e:
                logger.warning(f"Error parsing SEBI announcement: {e}")
                continue

        # Sort by relevance and date
        announcements.sort(key=lambda a: (a.relevance_score, a.published_date), reverse=True)

        # Cache result
        self._cache[cache_key] = announcements
        self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=self.cache_ttl_hours)

        return announcements

    async def get_rbi_announcements(self, days: int = 30) -> List[RegulatoryAnnouncement]:
        """Get RBI announcements (monetary policy, regulatory changes)."""
        cache_key = f"rbi_{days}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = "https://www.rbi.org.in/api/announcements"
        params = {
            "from_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to_date": datetime.now().strftime("%Y-%m-%d"),
        }

        if self.api_keys.get("RBI"):
            headers = {"Authorization": f"Bearer {self.api_keys['RBI']}"}
        else:
            headers = {}

        data = await self._fetch(url, params, headers)
        if not data or "announcements" not in data:
            logger.warning("No RBI announcements found")
            return []

        announcements = []
        for item in data.get("announcements", []):
            try:
                ann = RegulatoryAnnouncement(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    authority="RBI",
                    announcement_type=item.get("type", "circular"),
                    published_date=item.get("publishedDate", ""),
                    effective_date=item.get("effectiveDate"),
                    url=item.get("url", ""),
                    affected_sectors=item.get("affectedSectors", ["banking", "finance"]),
                    severity=item.get("severity", "MEDIUM"),
                    relevance_score=0.5,  # RBI announcements affect all financial stocks
                )
                announcements.append(ann)
            except Exception as e:
                logger.warning(f"Error parsing RBI announcement: {e}")
                continue

        self._cache[cache_key] = announcements
        self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=self.cache_ttl_hours)

        return announcements

    async def get_nse_announcements(self, symbol: str,
                                    days: int = 30) -> List[RegulatoryAnnouncement]:
        """Get NSE announcements for a specific symbol."""
        cache_key = f"nse_{symbol}_{days}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = f"{self.base_url}/api/announcements"
        params = {
            "symbol": symbol,
            "from_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to_date": datetime.now().strftime("%Y-%m-%d"),
        }

        data = await self._fetch(url, params)
        if not data or "announcements" not in data:
            logger.warning(f"No NSE announcements for {symbol}")
            return []

        announcements = []
        for item in data.get("announcements", []):
            try:
                ann = RegulatoryAnnouncement(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    authority="NSE",
                    announcement_type=item.get("type", "circular"),
                    published_date=item.get("publishedDate", ""),
                    effective_date=item.get("effectiveDate"),
                    url=item.get("url", ""),
                    affected_sectors=item.get("affectedSectors", []),
                    severity=item.get("severity", "MEDIUM"),
                    relevance_score=0.8,  # NSE announcements are symbol-specific
                )
                announcements.append(ann)
            except Exception as e:
                logger.warning(f"Error parsing NSE announcement: {e}")
                continue

        self._cache[cache_key] = announcements
        self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=self.cache_ttl_hours)

        return announcements

    def _calculate_relevance(self, announcement: Dict, symbol: Optional[str]) -> float:
        """Calculate relevance score for an announcement."""
        score = 0.5  # Base relevance

        title = announcement.get("title", "").lower()
        description = announcement.get("description", "").lower()
        text = f"{title} {description}"

        if symbol and symbol.lower() in text:
            score += 0.4

        if any(kw in text for kw in ["penalty", "fine", "investigation", "action", "violation"]):
            score += 0.2

        if any(kw in text for kw in ["approval", "clearance", "permission"]):
            score += 0.1

        return min(1.0, score)

    def calculate_regulatory_risk(self, symbol: str,
                                  announcements: List[RegulatoryAnnouncement],
                                  legal_cases_count: int = 0,
                                  auditor_resignations: int = 0) -> RegulatoryRiskScore:
        """Calculate regulatory risk score for a symbol.

        Args:
            symbol: Stock symbol
            announcements: List of regulatory announcements
            legal_cases_count: Number of serious legal cases
            auditor_resignations: Number of auditor resignations

        Returns:
            RegulatoryRiskScore object
        """
        # Base risk from announcements
        announcement_risk = 0
        for ann in announcements:
            if ann.severity == "CRITICAL":
                announcement_risk += 25
            elif ann.severity == "HIGH":
                announcement_risk += 15
            elif ann.severity == "MEDIUM":
                announcement_risk += 10
            elif ann.severity == "LOW":
                announcement_risk += 5

            # Adjust for relevance
            announcement_risk = announcement_risk * ann.relevance_score

        # Legal cases risk
        legal_risk = min(legal_cases_count * 15, 40)

        # Auditor resignation risk
        auditor_risk = min(auditor_resignations * 20, 30)

        # Total risk score (0-100)
        total_risk = min(100, announcement_risk + legal_risk + auditor_risk)

        return RegulatoryRiskScore(
            symbol=symbol,
            company_name=symbol,
            regulatory_risk_score=round(total_risk, 1),
            risk_level="",  # Will be set in __post_init__
            active_actions=len(announcements),
            recent_announcements=announcements[:10],
            legal_cases_count=legal_cases_count,
            auditor_resignations_count=auditor_resignations,
        )

    async def get_regulatory_risk(self, symbol: str,
                                  days: int = 30,
                                  legal_cases_count: int = 0,
                                  auditor_resignations: int = 0) -> RegulatoryRiskScore:
        """Get regulatory risk score for a symbol."""
        # Get announcements from all sources
        sebi_announcements = await self.get_sebi_announcements(symbol, days)
        rbi_announcements = await self.get_rbi_announcements(days)
        nse_announcements = await self.get_nse_announcements(symbol, days)

        all_announcements = sebi_announcements + rbi_announcements + nse_announcements

        # Calculate risk
        risk_score = self.calculate_regulatory_risk(
            symbol, all_announcements, legal_cases_count, auditor_resignations
        )

        return risk_score

    async def get_multiple_risks(self, symbols: List[str]) -> Dict[str, RegulatoryRiskScore]:
        """Get regulatory risk scores for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                risk = await self.get_regulatory_risk(symbol)
                if risk:
                    results[symbol] = risk
            except Exception as e:
                logger.error(f"Error calculating regulatory risk for {symbol}: {e}")
                continue
        return results
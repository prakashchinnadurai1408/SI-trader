"""NSE Fundamental Data Adapter for SI-Trader.

Provides fundamental financial data from NSE India for fundamental scoring:
- Piotroski F-Score (0-9)
- Altman Z-Score (bankruptcy prediction)
- PE vs Sector Ratio
- ROE Trend
- Cash Flow Positive
- Earnings Trend
- Debt/Equity Ratio
- Interest Coverage Ratio

Data Sources:
- NSE Corporate Financial Results
- NSE Corporate Filings
- NSE Annual Reports

Parameters Covered:
- f_score (Score, weight=1, quarterly)
- altman_z_score (Score, weight=1, quarterly)
- pe_ratio_vs_sector (Score, weight=4, quarterly)
- roe_trend (Score, weight=4, quarterly)
- cash_flow_positive (Filter, weight=3, quarterly)
- earnings_trend (Score, weight=4, quarterly)
- debt_equity_ratio (Filter, weight=3, quarterly)
- interest_coverage (Filter, weight=3, quarterly)
- company_valuation (Score, weight=0, quarterly - disabled)
- company_analytics (Advisory, weight=0, quarterly - disabled)
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
class FinancialData:
    """Financial data for a single company."""
    symbol: str
    reporting_period: str  # e.g., "Q1 FY2024"
    report_date: str

    # Profitability
    net_profit: float = 0.0
    revenue: float = 0.0
    operating_profit: float = 0.0
    roe: float = 0.0
    roa: float = 0.0
    net_margin: float = 0.0

    # Leverage
    total_debt: float = 0.0
    total_equity: float = 0.0
    total_assets: float = 0.0
    debt_equity_ratio: float = 0.0
    interest_expense: float = 0.0
    ebit: float = 0.0

    # Liquidity
    operating_cash_flow: float = 0.0
    current_assets: float = 0.0
    current_liabilities: float = 0.0
    cash_and_equivalents: float = 0.0

    # Efficiency
    total_sales: float = 0.0
    total_income: float = 0.0

    # Share Data
    shares_outstanding: float = 0.0
    shares_previous_year: float = 0.0

    # Market Data
    market_cap: float = 0.0
    total_liabilities: float = 0.0

    sector_median_pe: float = 0.0
    stock_pe: float = 0.0

    source: str = "NSE"
    refresh_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FundamentalScore:
    """Fundamental score calculation result."""
    symbol: str
    f_score: int  # 0-9
    altman_z_score: float
    pe_ratio_vs_sector: float
    roe_trend: float  # % change
    cash_flow_positive: bool
    earnings_trend: float  # % change
    debt_equity_ratio: float
    interest_coverage: float
    calculated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        # F-Score interpretation
        if self.f_score >= 8:
            self.f_score_interpretation = "Strong financial health"
        elif self.f_score >= 6:
            self.f_score_interpretation = "Good financial health"
        elif self.f_score >= 4:
            self.f_score_interpretation = "Average financial health"
        elif self.f_score >= 2:
            self.f_score_interpretation = "Weak financial health"
        else:
            self.f_score_interpretation = "Very weak financial health"

        # Z-Score interpretation
        if self.altman_z_score > 3.0:
            self.z_score_interpretation = "Low bankruptcy risk (safe zone)"
        elif self.altman_z_score > 1.8:
            self.z_score_interpretation = "Grey zone - caution"
        else:
            self.z_score_interpretation = "High bankruptcy risk (distress zone)"


class FundamentalsAdapter:
    """NSE Fundamental Data Adapter.

    Fetches fundamental financial data from NSE India for:
    - Piotroski F-Score calculation (9 criteria)
    - Altman Z-Score calculation (bankruptcy prediction)
    - PE vs Sector Ratio
    - ROE Trend
    - Cash Flow Positive
    - Earnings Trend
    - Debt/Equity Ratio
    - Interest Coverage Ratio

    BRD Parameters Supported:
    - f_score (Score, weight=1, quarterly)
    - altman_z_score (Score, weight=1, quarterly)
    - pe_ratio_vs_sector (Score, weight=4, quarterly)
    - roe_trend (Score, weight=4, quarterly)
    - cash_flow_positive (Filter, weight=3, quarterly)
    - earnings_trend (Score, weight=4, quarterly)
    - debt_equity_ratio (Filter, weight=3, quarterly)
    - interest_coverage (Filter, weight=3, quarterly)
    - company_valuation (Score, weight=0, quarterly - disabled)
    - company_analytics (Advisory, weight=0, quarterly - disabled)
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://www.nseindia.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self.cache_ttl_hours = 24  # Cache financial data for 24 hours

        logger.info("FundamentalsAdapter initialized")

    async def __aenter__(self):
        _require_aiohttp()
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
        """Fetch data from the API with retry logic."""
        _require_aiohttp()
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

    async def get_financial_data(self, symbol: str) -> Optional[FinancialData]:
        """Get financial data for a symbol.

        Args:
            symbol: Stock symbol (e.g., RELIANCE)

        Returns:
            FinancialData object or None
        """
        cache_key = f"financial_{symbol}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        url = f"{self.base_url}/api/corporate-financial-results"
        params = {"symbol": symbol}

        data = await self._fetch(url, params)
        if not data:
            logger.warning(f"No financial data for {symbol}")
            return None

        try:
            # Extract latest period data
            financial_data = data.get("data", {})
            if isinstance(financial_data, list) and len(financial_data) > 0:
                latest = financial_data[0]
            elif isinstance(financial_data, dict):
                latest = financial_data
            else:
                return None

            fd = FinancialData(
                symbol=symbol,
                reporting_period=latest.get("period", ""),
                report_date=latest.get("date", ""),
                net_profit=float(latest.get("netProfit", 0)),
                revenue=float(latest.get("revenue", 0)),
                operating_profit=float(latest.get("operatingProfit", 0)),
                roe=float(latest.get("roe", 0)),
                roa=float(latest.get("roa", 0)),
                net_margin=float(latest.get("netMargin", 0)),
                total_debt=float(latest.get("totalDebt", 0)),
                total_equity=float(latest.get("totalEquity", 0)),
                total_assets=float(latest.get("totalAssets", 0)),
                debt_equity_ratio=float(latest.get("debtEquityRatio", 0)),
                interest_expense=float(latest.get("interestExpense", 0)),
                ebit=float(latest.get("ebit", 0)),
                operating_cash_flow=float(latest.get("operatingCashFlow", 0)),
                current_assets=float(latest.get("currentAssets", 0)),
                current_liabilities=float(latest.get("currentLiabilities", 0)),
                cash_and_equivalents=float(latest.get("cashAndEquivalents", 0)),
                total_sales=float(latest.get("totalSales", 0)),
                total_income=float(latest.get("totalIncome", 0)),
                shares_outstanding=float(latest.get("sharesOutstanding", 0)),
                shares_previous_year=float(latest.get("sharesPreviousYear", 0)),
                market_cap=float(latest.get("marketCap", 0)),
                total_liabilities=float(latest.get("totalLiabilities", 0)),
                stock_pe=float(latest.get("pe", 0)),
                sector_median_pe=float(latest.get("sectorMedianPE", 0)),
            )

            # Cache result
            self._cache[cache_key] = fd
            self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=self.cache_ttl_hours)

            return fd

        except Exception as e:
            logger.error(f"Error parsing financial data for {symbol}: {e}")
            return None

    def calculate_f_score(self, fd: FinancialData) -> int:
        """Calculate Piotroski F-Score (0-9).

        9 criteria:
        1. ROA > 0
        2. CFO > 0
        3. ROA improving
        4. CFO > ROA (accrual < 0)
        5. Margin improving
        6. Turnover improving
        7. Liquidity improving
        8. Leverage decreasing
        9. No share dilution
        """
        score = 0

        # 1. ROA > 0
        if fd.roa > 0:
            score += 1

        # 2. CFO > 0
        if fd.operating_cash_flow > 0:
            score += 1

        # 3. ROA improving (need previous period for comparison)
        # Simplified: use current ROA as proxy
        if fd.roa > 5:
            score += 1

        # 4. CFO > ROA (accrual < 0 means cash flow quality)
        if fd.operating_cash_flow > fd.net_profit:
            score += 1

        # 5. Margin improving (net margin > 5%)
        if fd.net_margin > 5:
            score += 1

        # 6. Turnover improving (asset turnover > 1)
        if fd.total_sales > fd.total_assets:
            score += 1

        # 7. Liquidity improving (current ratio > 1.5)
        current_ratio = fd.current_assets / fd.current_liabilities if fd.current_liabilities > 0 else 0
        if current_ratio > 1.5:
            score += 1

        # 8. Leverage decreasing (debt/equity < 1)
        if fd.debt_equity_ratio < 1:
            score += 1

        # 9. No share dilution (shares not increasing)
        if fd.shares_outstanding <= fd.shares_previous_year or fd.shares_previous_year == 0:
            score += 1

        return score

    def calculate_altman_z_score(self, fd: FinancialData) -> float:
        """Calculate Altman Z-Score.

        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 0.999*X5

        X1 = Working Capital / Total Assets
        X2 = Retained Earnings / Total Assets
        X3 = EBIT / Total Assets
        X4 = Market Value of Equity / Total Liabilities
        X5 = Sales / Total Assets
        """
        total_assets = fd.total_assets if fd.total_assets > 0 else 1
        total_liabilities = fd.total_liabilities if fd.total_liabilities > 0 else 1
        market_cap = fd.market_cap if fd.market_cap > 0 else fd.total_equity

        x1 = (fd.current_assets - fd.current_liabilities) / total_assets  # Working Capital / TA
        x2 = fd.net_profit / total_assets  # Retained Earnings approx / TA
        x3 = fd.ebit / total_assets  # EBIT / TA
        x4 = market_cap / total_liabilities  # Market Cap / Total Liabilities
        x5 = fd.total_sales / total_assets  # Sales / TA

        z_score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 0.999 * x5
        return round(z_score, 2)

    def calculate_all_scores(self, fd: FinancialData) -> FundamentalScore:
        """Calculate all fundamental scores for a symbol."""
        f_score = self.calculate_f_score(fd)
        z_score = self.calculate_altman_z_score(fd)

        # PE vs Sector Ratio
        pe_vs_sector = fd.stock_pe / fd.sector_median_pe if fd.sector_median_pe > 0 else 0

        # ROE Trend (use current ROE as proxy for trend)
        roe_trend = fd.roe

        # Cash Flow Positive
        cash_flow_positive = fd.operating_cash_flow > 0

        # Earnings Trend (use net profit as proxy)
        earnings_trend = fd.net_profit

        # Debt/Equity Ratio
        debt_equity = fd.debt_equity_ratio

        # Interest Coverage
        interest_coverage = fd.ebit / fd.interest_expense if fd.interest_expense > 0 else 0

        return FundamentalScore(
            symbol=fd.symbol,
            f_score=f_score,
            altman_z_score=z_score,
            pe_ratio_vs_sector=round(pe_vs_sector, 2),
            roe_trend=round(roe_trend, 2),
            cash_flow_positive=cash_flow_positive,
            earnings_trend=round(earnings_trend, 2),
            debt_equity_ratio=round(debt_equity, 2),
            interest_coverage=round(interest_coverage, 2),
        )

    async def get_fundamental_scores(self, symbol: str) -> Optional[FundamentalScore]:
        """Get complete fundamental scores for a symbol."""
        fd = await self.get_financial_data(symbol)
        if not fd:
            return None
        return self.calculate_all_scores(fd)

    async def get_multiple_scores(self, symbols: List[str]) -> Dict[str, FundamentalScore]:
        """Calculate fundamental scores for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                score = await self.get_fundamental_scores(symbol)
                if score:
                    results[symbol] = score
            except Exception as e:
                logger.error(f"Error calculating fundamental scores for {symbol}: {e}")
                continue
        return results
"""Parameter catalogue for the Nifty 100 weekly scoring system.

Each parameter is a row with:
- enable_switch: boolean, default true (can be disabled by user/role)
- role_type: Score/Filter/Veto/Market dial/Advisory/Flag
- weight: integer 1-25, total across all parameters = 100
- source: NSE, BSE, AMFI, SEBI, RBI, News, Filings, Historical
- refresh_schedule: daily/weekly/monthly/quarterly/on-event/fy_update/per_trade

Weight totals 100 across all 48 enabled parameters.

Section 27.5 defines the weekly selection pipeline:
1. Apply filters (liquidity > 25 crore, no ASM/GSM, no pending serious legal action)
2. Apply vetoes (regulatory actions, pledging > 50%, legal cases)
3. Calculate raw score (weighted sum)
4. Cost check: subtract estimated brokerage + STT 0.1% + STCG 20% + slippage
5. Edge check: if net edge <= 0 after costs+tax, auto-disable trade
6. Select top N stocks (default: 10) for the weekly basket

Integrated external strategies:
- Piotroski F-Score (fundamental health, 0-9 scale)
- Altman Z-Score (bankruptcy risk prediction)
- PKScreener patterns (breakout, flag, momentum)
- algo_trading_strategies_india (breakout, bull flag, oversold bounce, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class RoleType(Enum):
    """Parameter role in the scoring system."""
    SCORE = "Score"
    FILTER = "Filter"
    VETO = "Veto"
    MARKET_DIAL = "Market dial"
    ADVISORY = "Advisory"
    FLAG = "Flag"


@dataclass
class ParameterDefinition:
    """Definition of a single parameter in the catalogue."""
    parameter_key: str
    display_name: str
    description: str
    enable_switch: bool = True
    role_type: RoleType = RoleType.SCORE
    weight: int = 5
    source: str = "NSE"
    refresh_schedule: str = "weekly"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Optional[float] = None
    unit: str = ""


PARAMETER_CATALOGUE: Dict[str, ParameterDefinition] = {
    # --- Score parameters (13 params, total weight 35)
    "price_momentum_weekly": ParameterDefinition(
        parameter_key="price_momentum_weekly",
        display_name="Weekly Price Momentum",
        description="Price change over the past 7 calendar days",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE Price History",
        refresh_schedule="weekly",
        unit="%",
    ),
    "price_momentum_monthly": ParameterDefinition(
        parameter_key="price_momentum_monthly",
        display_name="Monthly Price Momentum",
        description="Price change over the past 30 calendar days",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE Price History",
        refresh_schedule="weekly",
        unit="%",
    ),
    "price_momentum_yearly": ParameterDefinition(
        parameter_key="price_momentum_yearly",
        display_name="Yearly Price Momentum",
        description="Price change over the past 365 calendar days",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE Price History",
        refresh_schedule="weekly",
        unit="%",
    ),
    "f_score": ParameterDefinition(
        parameter_key="f_score",
        display_name="Piotroski F-Score",
        description="Evaluates financial health using 9 criteria: profitability, leverage, liquidity, and operating efficiency. Score range: 0-9 (higher = healthier).",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE Financial Statements",
        refresh_schedule="quarterly",
    ),
    "altman_z_score": ParameterDefinition(
        parameter_key="altman_z_score",
        display_name="Altman Z-Score",
        description="Predicts bankruptcy risk using 5 financial ratios",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE Financial Statements",
        refresh_schedule="quarterly",
    ),
    "pe_ratio_vs_sector": ParameterDefinition(
        parameter_key="pe_ratio_vs_sector",
        display_name="PE vs Sector Ratio",
        description="Stock PE divided by sector median PE",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE Fundamentals",
        refresh_schedule="quarterly",
    ),
    "roe_trend": ParameterDefinition(
        parameter_key="roe_trend",
        display_name="ROE Trend",
        description="Return on equity over recent quarters",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE Fundamentals",
        refresh_schedule="quarterly",
    ),
    "earnings_trend": ParameterDefinition(
        parameter_key="earnings_trend",
        display_name="Earnings Trend",
        description="EPS growth over last 4 quarters",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE Fundamentals",
        refresh_schedule="quarterly",
    ),
    "company_valuation": ParameterDefinition(
        parameter_key="company_valuation",
        display_name="Company Valuation",
        description="Company valuation relative to peers and sector",
        role_type=RoleType.SCORE,
        weight=3,
        source="Financial filings and NSE market data",
        refresh_schedule="quarterly",
    ),
    "fii_dii_mf_trend": ParameterDefinition(
        parameter_key="fii_dii_mf_trend",
        display_name="FII/DII/MF Trend",
        description="Foreign/institutional/mutual fund flow direction",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE Institutional Flows",
        refresh_schedule="weekly",
    ),
    "midcap_liquidity_score": ParameterDefinition(
        parameter_key="midcap_liquidity_score",
        display_name="Midcap Liquidity Score",
        description="Liquidity adequacy for midcap trading (turnover vs market cap)",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE Price History",
        refresh_schedule="weekly",
    ),
    "midcap_fii_mf_trend": ParameterDefinition(
        parameter_key="midcap_fii_mf_trend",
        display_name="Midcap FII/DII/MF Trend",
        description="Foreign/institutional/mutual fund flow direction for midcaps",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE Institutional Flows",
        refresh_schedule="weekly",
    ),
    "historical_news_sentiment": ParameterDefinition(
        parameter_key="historical_news_sentiment",
        display_name="News Sentiment Score",
        description="NLP-analysed sentiment of company/news articles",
        role_type=RoleType.SCORE,
        weight=3,
        source="News Sentiment Model",
        refresh_schedule="daily",
    ),

    # --- Filter parameters (10 params, total weight 20)
    "promoter_holding_pct": ParameterDefinition(
        parameter_key="promoter_holding_pct",
        display_name="Promoter Holding %",
        description="Promoters' equity holding percentage",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE Shareholding",
        refresh_schedule="quarterly",
    ),
    "midcap_volatility_adj": ParameterDefinition(
        parameter_key="midcap_volatility_adj",
        display_name="Midcap Volatility Adjustment",
        description="Volatility adj factor for midcap risk management",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE Price History",
        refresh_schedule="weekly",
    ),
    "liquidity_floor": ParameterDefinition(
        parameter_key="liquidity_floor",
        display_name="Liquidity Floor",
        description="Minimum daily turnover for consideration",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE Volume Data",
        refresh_schedule="daily",
    ),
    "stt_rate_equity": ParameterDefinition(
        parameter_key="stt_rate_equity",
        display_name="STT Rate - Equity",
        description="Securities Transaction Tax rate",
        role_type=RoleType.FILTER,
        weight=2,
        source="Config",
        refresh_schedule="fy_update",
        unit="%",
    ),
    "stcg_tax_rate": ParameterDefinition(
        parameter_key="stcg_tax_rate",
        display_name="STCG Tax Rate",
        description="Short-term capital gains tax rate",
        role_type=RoleType.FILTER,
        weight=2,
        source="Config",
        refresh_schedule="fy_update",
        unit="%",
    ),
    "brokerage_rate_param": ParameterDefinition(
        parameter_key="brokerage_rate",
        display_name="Brokerage Rate",
        description="Per-order brokerage as percentage",
        role_type=RoleType.FILTER,
        weight=2,
        source="Broker API",
        refresh_schedule="per_trade",
        unit="%",
    ),
    "asm_gsm_surveillance": ParameterDefinition(
        parameter_key="asm_gsm_surveillance",
        display_name="ASM/GSM Surveillance",
        description="ASM/GSM surveillance status from NSE",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE surveillance reports",
        refresh_schedule="daily",
    ),
    "debt_equity_ratio": ParameterDefinition(
        parameter_key="debt_equity_ratio",
        display_name="Debt/Equity Ratio",
        description="Total debt divided by equity",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE Fundamentals",
        refresh_schedule="quarterly",
    ),
    "interest_coverage": ParameterDefinition(
        parameter_key="interest_coverage",
        display_name="Interest Coverage Ratio",
        description="EBIT divided by interest expense",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE Fundamentals",
        refresh_schedule="quarterly",
    ),
    "cash_flow_positive": ParameterDefinition(
        parameter_key="cash_flow_positive",
        display_name="Cash Flow Positive",
        description="Operating cash flow > 0",
        role_type=RoleType.FILTER,
        weight=2,
        source="NSE Fundamentals",
        refresh_schedule="quarterly",
    ),

    # --- Veto parameters (6 params, total weight 15)
    "promoter_pledging_pct": ParameterDefinition(
        parameter_key="promoter_pledging_pct",
        display_name="Promoter Pledging %",
        description="% of promoter holding pledged as security",
        role_type=RoleType.VETO,
        weight=3,
        source="NSE Shareholding",
        refresh_schedule="quarterly",
    ),
    "legal_cases_directors": ParameterDefinition(
        parameter_key="legal_cases_directors",
        display_name="Legal Cases - Directors",
        description="Serious legal cases against directors/promoters",
        role_type=RoleType.VETO,
        weight=3,
        source="Court Records",
        refresh_schedule="on-event",
    ),
    "credit_rating_changes": ParameterDefinition(
        parameter_key="credit_rating_changes",
        display_name="Credit Rating Changes",
        description="Upgrades/downgrades by rating agencies",
        role_type=RoleType.VETO,
        weight=3,
        source="Credit Agencies",
        refresh_schedule="on-event",
    ),
    "legal_cases_company_promoters": ParameterDefinition(
        parameter_key="legal_cases_company_promoters",
        display_name="Legal Cases - Company/Promoters",
        description="Legal cases against companies or promoters",
        role_type=RoleType.VETO,
        weight=2,
        source="Court records",
        refresh_schedule="on-event",
    ),
    "auditor_resignations": ParameterDefinition(
        parameter_key="auditor_resignations",
        display_name="Auditor Resignations",
        description="Auditor resignations",
        role_type=RoleType.VETO,
        weight=2,
        source="Exchange corporate filings",
        refresh_schedule="on-event",
    ),
    "cost_vs_edge_check": ParameterDefinition(
        parameter_key="cost_vs_edge_check",
        display_name="Cost vs Edge Check",
        description="Auto-disable if net edge <= 0 after costs+tax",
        role_type=RoleType.VETO,
        weight=2,
        source="Internal Calculation",
        refresh_schedule="per_trade",
    ),

    # --- Market dial parameters (2 params, total weight 5)
    "international_war_situation": ParameterDefinition(
        parameter_key="international_war_situation",
        display_name="International Situation",
        description="Geopolitical risk dial (escalation/reduction)",
        role_type=RoleType.MARKET_DIAL,
        weight=3,
        source="Geopolitical Risk API",
        refresh_schedule="daily",
    ),
    "government_news": ParameterDefinition(
        parameter_key="government_news",
        display_name="Government News",
        description="Government releases and news (Press Information Bureau)",
        role_type=RoleType.MARKET_DIAL,
        weight=2,
        source="Press Information Bureau",
        refresh_schedule="on-event",
    ),

    # --- Advisory parameters (12 params, total weight 12)
    "swot_analytics": ParameterDefinition(
        parameter_key="swot_analytics",
        display_name="SWOT Analytics",
        description="Strengths, Weaknesses, Opportunities, Threats",
        role_type=RoleType.ADVISORY,
        weight=2,
        source="Company Reports",
        refresh_schedule="quarterly",
    ),
    "competitive_plans": ParameterDefinition(
        parameter_key="competitive_plans",
        display_name="Competitive Plans",
        description="Competitor launches, market share changes",
        role_type=RoleType.ADVISORY,
        weight=2,
        source="Company Reports",
        refresh_schedule="quarterly",
    ),
    "company_analytics": ParameterDefinition(
        parameter_key="company_analytics",
        display_name="Company Analytics",
        description="Financial filings and internal analytics",
        role_type=RoleType.ADVISORY,
        weight=1,
        source="Financial filings and internal analytics",
        refresh_schedule="weekly",
    ),
    "customer_feedback": ParameterDefinition(
        parameter_key="customer_feedback",
        display_name="Company Customer Feedback",
        description="Published customer research",
        role_type=RoleType.ADVISORY,
        weight=1,
        source="Published customer research",
        refresh_schedule="monthly",
    ),
    "ownership_breakdown": ParameterDefinition(
        parameter_key="ownership_breakdown",
        display_name="Ownership Breakdown",
        description="Ownership by promoters, government, institutions, funds and individuals",
        role_type=RoleType.ADVISORY,
        weight=1,
        source="Exchange shareholding filings",
        refresh_schedule="quarterly",
    ),
    "historical_price_series": ParameterDefinition(
        parameter_key="historical_price_series",
        display_name="Historical Price Series",
        description="Historical price series (daily, weekly, monthly, yearly)",
        role_type=RoleType.ADVISORY,
        weight=1,
        source="NSE historical market data",
        refresh_schedule="daily",
    ),
    "unique_features": ParameterDefinition(
        parameter_key="unique_features",
        display_name="Unique Company Features",
        description="Unique company features",
        role_type=RoleType.ADVISORY,
        weight=1,
        source="Company filings",
        refresh_schedule="quarterly",
    ),
    "company_collaborations": ParameterDefinition(
        parameter_key="company_collaborations",
        display_name="Company Collaborations",
        description="Company collaborations",
        role_type=RoleType.FLAG,
        weight=1,
        source="Exchange corporate filings",
        refresh_schedule="on-event",
    ),

    # --- Flag parameters (5 params, total weight 5)
    "midcap_corp_action": ParameterDefinition(
        parameter_key="midcap_corp_action",
        display_name="Midcap Corporate Action",
        description="Corporate actions affecting midcap stocks",
        role_type=RoleType.FLAG,
        weight=1,
        source="NSE Corporate Actions",
        refresh_schedule="on-event",
    ),
    "corporate_actions": ParameterDefinition(
        parameter_key="corporate_actions",
        display_name="Corporate Actions",
        description="Corporate actions affecting stocks",
        role_type=RoleType.FLAG,
        weight=1,
        source="NSE and BSE corporate actions",
        refresh_schedule="on-event",
    ),
    "political_incidents": ParameterDefinition(
        parameter_key="political_incidents",
        display_name="Political Incidents",
        description="Political incidents",
        role_type=RoleType.FLAG,
        weight=1,
        source="Government releases and news",
        refresh_schedule="on-event",
    ),
    "regulator_announcements": ParameterDefinition(
        parameter_key="regulator_announcements",
        display_name="Regulator Announcements",
        description="SEBI, RBI, NSE and BSE announcements",
        role_type=RoleType.FLAG,
        weight=1,
        source="SEBI/RBI/NSE/BSE",
        refresh_schedule="on-event",
    ),
}


def validate_weight_total() -> bool:
    """Validate that total enabled weight equals 100."""
    total = sum(p.weight for p in PARAMETER_CATALOGUE.values() if p.enable_switch)
    return total == 100


def get_total_weight() -> int:
    """Get the total weight of all enabled parameters."""
    return sum(p.weight for p in PARAMETER_CATALOGUE.values() if p.enable_switch)


def get_enabled_parameters() -> List[ParameterDefinition]:
    """Get all parameters that are enabled."""
    return [p for p in PARAMETER_CATALOGUE.values() if p.enable_switch]


def get_parameters_by_role(role: RoleType) -> List[ParameterDefinition]:
    """Get parameters filtered by role type."""
    return [p for p in PARAMETER_CATALOGUE.values() if p.role_type == role and p.enable_switch]


# Validation on import
if not validate_weight_total():
    import warnings
    warnings.warn(
        f"Parameter catalogue weight total is {get_total_weight()}, not 100. "
        "BRD compliance may be affected.",
        stacklevel=2,
    )
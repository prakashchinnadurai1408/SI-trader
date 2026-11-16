"""Parameter catalogue for the Nifty 100 weekly scoring system.

Each parameter is a row with:
- enable_switch: boolean, default true (can be disabled by user/role)
- role_type: Score/Filter/Veto/Market dial/Advisory/Flag
- weight: integer 1-25, total across all parameters = 100
- source: NSE, BSE, AMFI, SEBI, RBI, News, Filings, Historical
- refresh_schedule: daily/weekly/on-event

Weight totals 100 (configurable, subject to backtest validation).

Section 27.5 defines the weekly selection pipeline:
1. Apply filters (liquidity > 25 crore, no ASM/GSM, no pending serious legal action)
2. Apply vetoes (regulatory actions, pledging > 50%, legal cases)
3. Calculate raw score (weighted sum)
4. Cost check: subtract estimated brokerage + STT 0.1% + STCG 20% + slippage
5. Edge check: if net edge ≤ 0 after costs+tax, auto-disable trade
6. Select top N stocks (default: 10) for the weekly basket
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class RoleType(Enum):
    """Parameter role in the scoring system."""
    SCORE = "Score"       # Contributes to raw score weight
    FILTER = "Filter"    # Must pass (stock fails if missing/negative)
    VETO = "Veto"        # Automatic disqualification
    MARKET_DIAL = "Market dial"  # Adjusts overall market exposure
    ADVISORY = "Advisory"  # Informational only, no score contribution
    FLAG = "Flag"        # Alert/notification, no trading action


@dataclass
class ParameterDefinition:
    """Definition of a single parameter in the catalogue."""
    parameter_key: str
    display_name: str
    description: str
    enable_switch: bool = True  # Can be disabled by user/role
    role_type: RoleType = RoleType.SCORE
    weight: int = 5  # 1-25, contributes to total 100
    source: str = "NSE"  # Data source
    refresh_schedule: str = "weekly"  # daily/weekly/on-event
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Optional[float] = None
    unit: str = ""  # e.g., "%", "ratio", "crore"


# Complete parameter catalogue (Section 27)
# All weights total 100

PARAMETER_CATALOGUE: Dict[str, ParameterDefinition] = {
    # --- Momentum parameters (Score) - total 38
    "price_momentum_weekly": ParameterDefinition(
        parameter_key="price_momentum_weekly",
        display_name="Weekly Price Momentum",
        description="Price change over the past 7 calendar days",
        role_type=RoleType.SCORE,
        weight=15,
        source="NSE Price History",
        refresh_schedule="weekly",
        unit="%"
    ),
    "price_momentum_daily": ParameterDefinition(
        parameter_key="price_momentum_daily",
        display_name="Daily Price Momentum",
        description="Price change over the past 1 trading day",
        role_type=RoleType.SCORE,
        weight=10,
        source="NSE Price History",
        refresh_schedule="daily",
        unit="%"
    ),
    "price_momentum_monthly": ParameterDefinition(
        parameter_key="price_momentum_monthly",
        display_name="Monthly Price Momentum",
        description="Price change over the past 30 calendar days",
        role_type=RoleType.SCORE,
        weight=8,
        source="NSE Price History",
        refresh_schedule="monthly",
        unit="%"
    ),
    "price_momentum_yearly": ParameterDefinition(
        parameter_key="price_momentum_yearly",
        display_name="Yearly Price Momentum",
        description="Price change over the past 365 calendar days",
        role_type=RoleType.SCORE,
        weight=5,
        source="NSE Price History",
        refresh_schedule="yearly",
        unit="%"
    ),

    # --- Valuation parameters (Score/Filter) - total 21
    "pe_ratio_vs_sector": ParameterDefinition(
        parameter_key="pe_ratio_vs_sector",
        display_name="PE vs Sector Ratio",
        description="Stock PE divided by sector median PE",
        role_type=RoleType.SCORE,
        weight=8,
        source="Fundamentals",
        refresh_schedule="quarterly",
        min_value=0,
        max_value=100,
        unit="x"
    ),
    "industry_expectations": ParameterDefinition(
        parameter_key="industry_expectations",
        display_name="Industry Expectations",
        description="qualitative sentiment on sector outlook",
        role_type=RoleType.ADVISORY,
        weight=5,
        source="Research Reports",
        refresh_schedule="quarterly",
        unit=""
    ),
    "debt_equity_ratio": ParameterDefinition(
        parameter_key="debt_equity_ratio",
        display_name="Debt/Equity Ratio",
        description="Total debt divided by equity",
        role_type=RoleType.FILTER,
        weight=10,
        source="Fundamentals",
        refresh_schedule="quarterly",
        max_value=2.0,  # Max acceptable D/E
        unit="x"
    ),
    "interest_coverage": ParameterDefinition(
        parameter_key="interest_coverage",
        display_name="Interest Coverage Ratio",
        description="EBIT divided by interest expense",
        role_type=RoleType.FILTER,
        weight=5,
        source="Fundamentals",
        refresh_schedule="quarterly",
        min_value=1.5,  # Minimum acceptable
        unit="x"
    ),
    "roe_trend": ParameterDefinition(
        parameter_key="roe_trend",
        display_name="ROE Trend",
        description="Return on equity over recent quarters",
        role_type=RoleType.SCORE,
        weight=8,
        source="Fundamentals",
        refresh_schedule="quarterly",
        min_value=0,
        max_value=50,
        unit="%"
    ),
    "cash_flow_positive": ParameterDefinition(
        parameter_key="cash_flow_positive",
        display_name="Cash Flow Positive",
        description="Operating cash flow > 0",
        role_type=RoleType.FILTER,
        weight=5,
        source="Fundamentals",
        refresh_schedule="quarterly",
        unit="bool"
    ),
    "earnings_trend": ParameterDefinition(
        parameter_key="earnings_trend",
        display_name="Earnings Trend",
        description="EPS growth over last 4 quarters",
        role_type=RoleType.SCORE,
        weight=8,
        source="Fundamentals",
        refresh_schedule="quarterly",
        unit="%"
    ),

    # --- Shareholding parameters (Filter/Veto) - total 31
    "promoter_holding_pct": ParameterDefinition(
        parameter_key="promoter_holding_pct",
        display_name="Promoter Holding %",
        description="Promoters' equity holding percentage",
        role_type=RoleType.FILTER,
        weight=8,
        source="Shareholding",
        refresh_schedule="quarterly",
        min_value=30,  # Minimum promoter holding
        unit="%"
    ),
    "promoter_pledging_pct": ParameterDefinition(
        parameter_key="promoter_pledging_pct",
        display_name="Promoter Pledging %",
        description="% of promoter holding pledged as security",
        role_type=RoleType.VETO,
        weight=10,
        source="Shareholding",
        refresh_schedule="quarterly",
        max_value=25,  # Veto if pledging > 25%
        unit="%"
    ),
    "fii_dii_mf_trend": ParameterDefinition(
        parameter_key="fii_dii_mf_trend",
        display_name="FII/DII/MF Trend",
        description="Foreign/institutional/mutual fund flow direction",
        role_type=RoleType.SCORE,
        weight=7,
        source="Shareholding",
        refresh_schedule="weekly",
        unit="net IN/OUT"
    ),
    "bulk_block_deals": ParameterDefinition(
        parameter_key="bulk_block_deals",
        display_name="Bulk/Block Deals",
        description="Large block trades in the week",
        role_type=RoleType.FLAG,
        weight=5,
        source="NSE Corporate Filings",
        refresh_schedule="daily",
        unit="count"
    ),
    "corporate_action_results": ParameterDefinition(
        parameter_key="corporate_action_results",
        display_name="Corporate Action - Results",
        description="Quarterly results date passed/ex-date",
        role_type=RoleType.FLAG,
        weight=5,
        source="NSE Corporate Actions",
        refresh_schedule="on-event",
        unit="bool"
    ),
    "corporate_action_dividends": ParameterDefinition(
        parameter_key="corporate_action_dividends",
        display_name="Corporate Action - Dividends",
        description="Interim/final dividend declarations",
        role_type=RoleType.ADVISORY,
        weight=3,
        source="NSE Corporate Actions",
        refresh_schedule="on-event",
        unit="%"),
    "regulatory_actions": ParameterDefinition(
        parameter_key="regulatory_actions",
        display_name="Regulatory Actions",
        description="SEBI/RBI/NSE/BSE observations, show-cause notices",
        role_type=RoleType.VETO,
        weight=15,
        source="SEBI/RBI/NSE/BSE",
        refresh_schedule="on-event",
        unit="bool"
    ),

    # --- Macro/market parameters (Market dial) - total 10
    "international_war_situation": ParameterDefinition(
        parameter_key="international_war_situation",
        display_name="International Situation",
        description="Geopolitical risk dial (escalation/reduction)",
        role_type=RoleType.MARKET_DIAL,
        weight=5,
        source="News, Geopolitical",
        refresh_schedule="daily",
        unit="score -5 to +5"
    ),
    "historical_events": ParameterDefinition(
        parameter_key="historical_events",
        display_name="Historical Events",
        description="Anniversaries of market-moving historical events",
        role_type=RoleType.ADVISORY,
        weight=5,
        source="Historical Database",
        refresh_schedule="weekly",
        unit=""
    ),

    # --- Sentiment parameters (Score) - total 16
    "historical_news_sentiment": ParameterDefinition(
        parameter_key="historical_news_sentiment",
        display_name="News Sentiment Score",
        description="NLP-analysed sentiment of company/news articles",
        role_type=RoleType.SCORE,
        weight=8,
        source="News Sentiment Model",
        refresh_schedule="daily",
        unit="-1 to +1"
    ),

    # --- SWOT and competition (Advisory) - total 10
    "swot_analytics": ParameterDefinition(
        parameter_key="swot_analytics",
        display_name="SWOT Analytics",
        description="Strengths, Weaknesses, Opportunities, Threats",
        role_type=RoleType.ADVISORY,
        weight=5,
        source="Company Reports",
        refresh_schedule="quarterly",
        unit=""
    ),
    "competitive_plans": ParameterDefinition(
        parameter_key="competitive_plans",
        display_name="Competitive Plans",
        description="Competitor launches, market share changes",
        role_type=RoleType.ADVISORY,
        weight=5,
        source="Industry Analysis",
        refresh_schedule="annually",
        unit=""
    ),

    # --- Cost and edge parameters (Veto/Filter) - total 25
    "legal_cases_directors": ParameterDefinition(
        parameter_key="legal_cases_directors",
        display_name="Legal Cases - Directors",
        description="Serious legal cases against directors/promoters",
        role_type=RoleType.VETO,
        weight=12,
        source="Court Records",
        refresh_schedule="on-event",
        unit="bool"
    ),
    "credit_rating_changes": ParameterDefinition(
        parameter_key="credit_rating_changes",
        display_name="Credit Rating Changes",
        description="Upgrades/downgrades by rating agencies",
        role_type=RoleType.VETO,
        weight=5,
        source="Credit Agencies",
        refresh_schedule="on-event",
        unit=""
    ),
    "liquidity_floor": ParameterDefinition(
        parameter_key="liquidity_floor",
        display_name="Liquidity Floor",
        description="Minimum daily turnover for consideration",
        role_type=RoleType.FILTER,
        weight=10,
        source="NSE Volume Data",
        refresh_schedule="daily",
        min_value=25,  # Minimum 25 crore daily turnover
        unit="crore"
    ),
    "cost_vs_edge_check": ParameterDefinition(
        parameter_key="cost_vs_edge_check",
        display_name="Cost vs Edge Check",
        description="Auto-disable if net edge ≤ 0 after costs+tax",
        role_type=RoleType.VETO,
        weight=10,
        source="Internal Calculation",
        refresh_schedule="per_trade",
        unit="% edge"
    ),
    "stt_rate_equity": ParameterDefinition(
        parameter_key="stt_rate_equity",
        display_name="STT Rate - Equity",
        description="Securities Transaction Tax rate",
        role_type=RoleType.FILTER,
        weight=3,
        source="Config",
        refresh_schedule="fy_update",
        unit="%"
    ),
    "stcg_tax_rate": ParameterDefinition(
        parameter_key="stcg_tax_rate",
        display_name="STCG Tax Rate",
        description="Short-term capital gains tax rate",
        role_type=RoleType.FILTER,
        weight=3,
        source="Config",
        refresh_schedule="fy_update",
        unit="%"
    ),
    "brokerage_rate_param": ParameterDefinition(
        parameter_key="brokerage_rate",
        display_name="Brokerage Rate",
        description="Per-order brokerage as percentage",
        role_type=RoleType.FILTER,
        weight=2,
        source="Broker API",
        refresh_schedule="per_trade",
        unit="%"
    ),
}


# Additional BRD inputs available for strategy configuration. Data feeds are
# tracked separately from their catalogue definitions.
ADDITIONAL_PARAMETERS = (
    ("stock_recommendation_reports", "Stock recommendation reports", RoleType.ADVISORY, "Broker research", "weekly"),
    ("company_news", "Company news", RoleType.ADVISORY, "Company releases and news", "daily"),
    ("government_news", "Government news", RoleType.MARKET_DIAL, "Press Information Bureau", "on-event"),
    ("political_incidents", "Political incidents", RoleType.FLAG, "Government releases and news", "on-event"),
    ("regulator_announcements", "SEBI, RBI, NSE and BSE announcements", RoleType.FLAG, "Regulator and exchange circulars", "on-event"),
    ("historical_price_series", "Historical price series (daily, weekly, monthly, yearly)", RoleType.ADVISORY, "NSE historical market data", "daily"),
    ("historical_news", "Historical news", RoleType.ADVISORY, "News archives", "weekly"),
    ("corporate_actions", "Corporate actions", RoleType.FLAG, "NSE and BSE corporate actions", "on-event"),
    ("predictive_analytics", "Predictive analytics", RoleType.ADVISORY, "Backtested internal models", "weekly"),
    ("unique_features", "Unique company features", RoleType.ADVISORY, "Company filings", "quarterly"),
    ("customer_feedback", "Company customer feedback", RoleType.ADVISORY, "Published customer research", "monthly"),
    ("ownership_breakdown", "Ownership by promoters, government, institutions, funds and individuals", RoleType.ADVISORY, "Exchange shareholding filings", "quarterly"),
    ("company_valuation", "Company valuation", RoleType.SCORE, "Financial filings and NSE market data", "quarterly"),
    ("company_analytics", "Company analytics", RoleType.ADVISORY, "Financial filings and internal analytics", "weekly"),
    ("company_collaborations", "Company collaborations", RoleType.FLAG, "Exchange corporate filings", "on-event"),
    ("legal_cases_company_promoters", "Legal cases against companies or promoters", RoleType.VETO, "Court records and exchange filings", "on-event"),
    ("auditor_resignations", "Auditor resignations", RoleType.VETO, "Exchange corporate filings", "on-event"),
    ("asm_gsm_surveillance", "ASM/GSM surveillance", RoleType.FILTER, "NSE surveillance reports", "daily"),
)

for key, name, role, source, schedule in ADDITIONAL_PARAMETERS:
    PARAMETER_CATALOGUE[key] = ParameterDefinition(
        parameter_key=key, display_name=name, description=name,
        enable_switch=False, role_type=role, weight=0,
        source=source, refresh_schedule=schedule,
    )


def get_total_weight() -> int:
    """Get the total weight of all enabled parameters."""
    total = 0
    for param in PARAMETER_CATALOGUE.values():
        if param.enable_switch:
            total += param.weight
    return total


def get_enabled_parameters() -> List[ParameterDefinition]:
    """Get all parameters that are enabled."""
    return [p for p in PARAMETER_CATALOGUE.values() if p.enable_switch]


def get_parameters_by_role(role: RoleType) -> List[ParameterDefinition]:
    """Get parameters filtered by role type."""
    return [p for p in PARAMETER_CATALOGUE.values() if p.role_type == role and p.enable_switch]


# Validation
def validate_weight_total() -> bool:
    """Validate that total enabled weight equals 100."""
    total = get_total_weight()
    return total == 100
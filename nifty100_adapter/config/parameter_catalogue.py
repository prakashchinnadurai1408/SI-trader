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
from typing import Dict, List, Optional, Tuple
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


# =============================================================================
# MAIN PARAMETER CATALOGUE
# All weights total exactly 100 across 30 enabled parameters (BRD requirement)
#
# Role breakdown:
#   Score:    12 params, weight 33
#   Filter:   9 params, weight 31
#   Veto:     4 params, weight 19
#   Market dial: 1 param, weight 3
#   Advisory: 3 params, weight 11
#   Flag:     1 param, weight 3
#   Total:    30 params, weight 100
# =============================================================================

PARAMETER_CATALOGUE: Dict[str, ParameterDefinition] = {
    # --- Momentum parameters (Score) - total 6
    "price_momentum_weekly": ParameterDefinition(
        parameter_key="price_momentum_weekly",
        display_name="Weekly Price Momentum",
        description="Price change over the past 7 calendar days",
        role_type=RoleType.SCORE,
        weight=1,
        source="NSE",
        refresh_schedule="weekly",
        unit="%",
    ),
    "price_momentum_monthly": ParameterDefinition(
        parameter_key="price_momentum_monthly",
        display_name="Monthly Price Momentum",
        description="Price change over the past 30 calendar days",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE",
        refresh_schedule="weekly",
        unit="%",
    ),
    "price_momentum_yearly": ParameterDefinition(
        parameter_key="price_momentum_yearly",
        display_name="Yearly Price Momentum",
        description="Price change over the past 365 calendar days",
        role_type=RoleType.SCORE,
        weight=2,
        source="NSE",
        refresh_schedule="weekly",
        unit="%",
    ),

    # --- Fundamental Scores (Score) - total 2 (Piotroski F-Score, Altman Z-Score)
    # Integrated from external fundamental analysis research
    "f_score": ParameterDefinition(
        parameter_key="f_score",
        display_name="Piotroski F-Score",
        description="Evaluates financial health using 9 criteria: profitability, leverage, liquidity, and operating efficiency. Score range: 0-9 (higher = healthier).",
        role_type=RoleType.SCORE,
        weight=1,
        source="NSE",
        refresh_schedule="quarterly",
    ),
    "altman_z_score": ParameterDefinition(
        parameter_key="altman_z_score",
        display_name="Altman Z-Score",
        description="Predicts bankruptcy risk using 5 financial ratios: working capital/Total assets, retained earnings/Total assets, EBIT/Total assets, market equity/Total assets, sales/Total assets. Score > 3 = low bankruptcy risk.",
        role_type=RoleType.SCORE,
        weight=1,
        source="NSE",
        refresh_schedule="quarterly",
    ),

    # --- Valuation parameters (Score/Filter) - total 26
    "pe_ratio_vs_sector": ParameterDefinition(
        parameter_key="pe_ratio_vs_sector",
        display_name="PE vs Sector Ratio",
        description="Stock PE divided by sector median PE",
        role_type=RoleType.SCORE,
        weight=4,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "industry_expectations": ParameterDefinition(
        parameter_key="industry_expectations",
        display_name="Industry Expectations",
        description="Qualitative sentiment on sector outlook",
        role_type=RoleType.ADVISORY,
        weight=3,
        source="Research Reports",
        refresh_schedule="weekly",
    ),
    "debt_equity_ratio": ParameterDefinition(
        parameter_key="debt_equity_ratio",
        display_name="Debt/Equity Ratio",
        description="Total debt divided by equity",
        role_type=RoleType.FILTER,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "interest_coverage": ParameterDefinition(
        parameter_key="interest_coverage",
        display_name="Interest Coverage Ratio",
        description="EBIT divided by interest expense",
        role_type=RoleType.FILTER,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "roe_trend": ParameterDefinition(
        parameter_key="roe_trend",
        display_name="ROE Trend",
        description="Return on equity over recent quarters",
        role_type=RoleType.SCORE,
        weight=4,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "cash_flow_positive": ParameterDefinition(
        parameter_key="cash_flow_positive",
        display_name="Cash Flow Positive",
        description="Operating cash flow > 0",
        role_type=RoleType.FILTER,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "earnings_trend": ParameterDefinition(
        parameter_key="earnings_trend",
        display_name="Earnings Trend",
        description="EPS growth over last 4 quarters",
        role_type=RoleType.SCORE,
        weight=4,
        source="NSE",
        refresh_schedule="weekly",
    ),

    # --- Shareholding parameters (Filter/Veto) - total 19
    "promoter_holding_pct": ParameterDefinition(
        parameter_key="promoter_holding_pct",
        display_name="Promoter Holding %",
        description="Promoters' equity holding percentage",
        role_type=RoleType.FILTER,
        weight=4,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "promoter_pledging_pct": ParameterDefinition(
        parameter_key="promoter_pledging_pct",
        display_name="Promoter Pledging %",
        description="% of promoter holding pledged as security",
        role_type=RoleType.VETO,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "fii_dii_mf_trend": ParameterDefinition(
        parameter_key="fii_dii_mf_trend",
        display_name="FII/DII/MF Trend",
        description="Foreign/institutional/mutual fund flow direction",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "midcap_liquidity_score": ParameterDefinition(
        parameter_key="midcap_liquidity_score",
        display_name="Midcap Liquidity Score",
        description="Liquidity adequacy for midcap trading (turnover vs market cap)",
        role_type=RoleType.SCORE,
        weight=4,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "midcap_fii_mf_trend": ParameterDefinition(
        parameter_key="midcap_fii_mf_trend",
        display_name="Midcap FII/DII/MF Trend",
        description="Foreign/institutional/mutual fund flow direction for midcaps",
        role_type=RoleType.SCORE,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "midcap_volatility_adj": ParameterDefinition(
        parameter_key="midcap_volatility_adj",
        display_name="Midcap Volatility Adjustment",
        description="Volatility adj factor for midcap risk management",
        role_type=RoleType.FILTER,
        weight=3,
        source="NSE",
        refresh_schedule="weekly",
    ),
    "midcap_corp_action": ParameterDefinition(
        parameter_key="midcap_corp_action",
        display_name="Midcap Corporate Action",
        description="Corporate actions affecting midcap stocks",
        role_type=RoleType.FLAG,
        weight=3,
        source="NSE",
        refresh_schedule="on-event",
    ),

    # --- Market dial - total 3
    "international_war_situation": ParameterDefinition(
        parameter_key="international_war_situation",
        display_name="International Situation",
        description="Geopolitical risk dial (escalation/reduction)",
        role_type=RoleType.MARKET_DIAL,
        weight=3,
        source="News",
        refresh_schedule="on-event",
    ),

    # --- Sentiment parameters (Score) - total 4
    "historical_news_sentiment": ParameterDefinition(
        parameter_key="historical_news_sentiment",
        display_name="News Sentiment Score",
        description="NLP-analysed sentiment of company/news articles",
        role_type=RoleType.SCORE,
        weight=4,
        source="News",
        refresh_schedule="weekly",
    ),

    # --- SWOT and competition (Advisory) - total 11
    "swot_analytics": ParameterDefinition(
        parameter_key="swot_analytics",
        display_name="SWOT Analytics",
        description="Strengths, Weaknesses, Opportunities, Threats",
        role_type=RoleType.ADVISORY,
        weight=3,
        source="Company Reports",
        refresh_schedule="quarterly",
    ),
    "competitive_plans": ParameterDefinition(
        parameter_key="competitive_plans",
        display_name="Competitive Plans",
        description="Competitor launches, market share changes",
        role_type=RoleType.ADVISORY,
        weight=5,
        source="Company Reports",
        refresh_schedule="quarterly",
    ),

    # --- Cost and edge parameters (Veto/Filter) - total 25
    "legal_cases_directors": ParameterDefinition(
        parameter_key="legal_cases_directors",
        display_name="Legal Cases - Directors",
        description="Serious legal cases against directors/promoters",
        role_type=RoleType.VETO,
        weight=6,
        source="Court Records",
        refresh_schedule="on-event",
    ),
    "credit_rating_changes": ParameterDefinition(
        parameter_key="credit_rating_changes",
        display_name="Credit Rating Changes",
        description="Upgrades/downgrades by rating agencies",
        role_type=RoleType.VETO,
        weight=5,
        source="Credit Agencies",
        refresh_schedule="on-event",
    ),
    "liquidity_floor": ParameterDefinition(
        parameter_key="liquidity_floor",
        display_name="Liquidity Floor",
        description="Minimum daily turnover for consideration",
        role_type=RoleType.FILTER,
        weight=5,
        source="NSE",
        refresh_schedule="daily",
    ),
    "cost_vs_edge_check": ParameterDefinition(
        parameter_key="cost_vs_edge_check",
        display_name="Cost vs Edge Check",
        description="Auto-disable if net edge <= 0 after costs+tax",
        role_type=RoleType.VETO,
        weight=5,
        source="Internal Calculation",
        refresh_schedule="per_trade",
    ),
    "stt_rate_equity": ParameterDefinition(
        parameter_key="stt_rate_equity",
        display_name="STT Rate - Equity",
        description="Securities Transaction Tax rate",
        role_type=RoleType.FILTER,
        weight=3,
        source="Config",
        refresh_schedule="fy_update",
        unit="%",
    ),
    "stcg_tax_rate": ParameterDefinition(
        parameter_key="stcg_tax_rate",
        display_name="STCG Tax Rate",
        description="Short-term capital gains tax rate",
        role_type=RoleType.FILTER,
        weight=3,
        source="Config",
        refresh_schedule="fy_update",
        unit="%",
    ),
    "brokerage_rate_param": ParameterDefinition(
        parameter_key="brokerage_rate",
        display_name="Brokerage Rate",
        description="Per-order brokerage as percentage",
        role_type=RoleType.FILTER,
        weight=4,
        source="Broker API",
        refresh_schedule="per_trade",
        unit="%",
    ),
}

# =============================================================================
# Additional BRD inputs - disabled by default (weight=0)
# These can be enabled by strategy adapters (PKScreener, algo_india, etc.)
# =============================================================================

ADDITIONAL_PARAMETERS = (
    ("stock_recommendation_reports", "Stock recommendation reports", RoleType.ADVISORY, "Broker research", "weekly"),
    ("company_news", "Company news", RoleType.ADVISORY, "Company releases and news", "daily"),
    ("government_news", "Government news", RoleType.MARKET_DIAL, "Press Information Bureau", "on-event"),
    ("political_incidents", "Political incidents", RoleType.FLAG, "Government releases and news", "on-event"),
    ("regulator_announcements", "SEBI, RBI, NSE and BSE announcements", RoleType.FLAG, "Regulator and exchange circulars", "on-event"),
    ("historical_price_series", "Historical price series", RoleType.ADVISORY, "NSE historical market data", "daily"),
    ("historical_news", "Historical news", RoleType.ADVISORY, "News archives", "weekly"),
    ("corporate_actions", "Corporate actions", RoleType.FLAG, "NSE and BSE corporate actions", "on-event"),
    ("predictive_analytics", "Predictive analytics", RoleType.ADVISORY, "Backtested internal models", "weekly"),
    ("unique_features", "Unique company features", RoleType.ADVISORY, "Company filings", "quarterly"),
    ("customer_feedback", "Company customer feedback", RoleType.ADVISORY, "Published customer research", "monthly"),
    ("ownership_breakdown", "Ownership breakdown", RoleType.ADVISORY, "Exchange shareholding filings", "quarterly"),
    ("company_valuation", "Company valuation", RoleType.SCORE, "Financial filings and NSE market data", "quarterly"),
    ("company_analytics", "Company analytics", RoleType.ADVISORY, "Financial filings and internal analytics", "weekly"),
    ("company_collaborations", "Company collaborations", RoleType.FLAG, "Exchange corporate filings", "on-event"),
    ("legal_cases_company_promoters", "Legal cases against companies or promoters", RoleType.VETO, "Court records", "on-event"),
    ("auditor_resignations", "Auditor resignations", RoleType.VETO, "Exchange corporate filings", "on-event"),
    ("asm_gsm_surveillance", "ASM/GSM surveillance", RoleType.FILTER, "NSE surveillance reports", "daily"),
)

for key, name, role, source, schedule in ADDITIONAL_PARAMETERS:
    PARAMETER_CATALOGUE[key] = ParameterDefinition(
        parameter_key=key,
        display_name=name,
        description=name,
        enable_switch=False,
        role_type=role,
        weight=0,
        source=source,
        refresh_schedule=schedule,
    )


# =============================================================================
# Validation
# =============================================================================

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
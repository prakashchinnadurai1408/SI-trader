"""Parameter catalogue for the Nifty 100 weekly scoring system.

48 enabled parameters, total weight exactly 100 (BRD requirement).

Role breakdown:
    Score:      13 params, weight 43
    Filter:     10 params, weight 20
    Veto:        6 params, weight 15
    Market dial: 2 params, weight 5
    Advisory:   12 params, weight 12
    Flag:        5 params, weight 5
    Total:      48 params, weight 100

Section 27.5 weekly selection pipeline:
1. Apply filters (liquidity, ASM/GSM, legal)
2. Apply vetoes (pledging, regulatory, legal cases)
3. Calculate raw score (weighted sum)
4. Cost check: brokerage + STT 0.1% + STCG 20% + slippage
5. Edge check: auto-disable if net edge <= 0
6. Select top N stocks (default: 10) for the weekly basket

Data sources are mapped in data/data_source_catalogue.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class RoleType(Enum):
    SCORE = "Score"
    FILTER = "Filter"
    VETO = "Veto"
    MARKET_DIAL = "Market dial"
    ADVISORY = "Advisory"
    FLAG = "Flag"


@dataclass
class ParameterDefinition:
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
    # ---------- SCORE (13 params, weight 43) ----------
    "price_momentum_weekly": ParameterDefinition(
        "price_momentum_weekly", "Weekly Price Momentum",
        "Price change over the past 7 calendar days",
        True, RoleType.SCORE, 4, "NSE Price History", "weekly", -100, 100, None, "%"),
    "price_momentum_monthly": ParameterDefinition(
        "price_momentum_monthly", "Monthly Price Momentum",
        "Price change over the past 30 calendar days",
        True, RoleType.SCORE, 3, "NSE Price History", "weekly", -100, 100, None, "%"),
    "price_momentum_yearly": ParameterDefinition(
        "price_momentum_yearly", "Yearly Price Momentum",
        "Price change over the past 365 calendar days",
        True, RoleType.SCORE, 3, "NSE Price History", "weekly", -100, 100, None, "%"),
    "f_score": ParameterDefinition(
        "f_score", "Piotroski F-Score",
        "Financial health across 9 criteria (profitability, leverage, "
        "liquidity, operating efficiency). 0-9, higher is healthier.",
        True, RoleType.SCORE, 3, "NSE Financial Statements", "quarterly", 0, 9, None, "0-9"),
    "altman_z_score": ParameterDefinition(
        "altman_z_score", "Altman Z-Score",
        "Bankruptcy risk from 5 financial ratios. Above 3.0 = low risk.",
        True, RoleType.SCORE, 2, "NSE Financial Statements", "quarterly", None, None, None, "score"),
    "pe_ratio_vs_sector": ParameterDefinition(
        "pe_ratio_vs_sector", "PE vs Sector Ratio",
        "Stock PE divided by sector median PE",
        True, RoleType.SCORE, 3, "NSE Fundamentals", "quarterly", 0, None, None, "ratio"),
    "roe_trend": ParameterDefinition(
        "roe_trend", "ROE Trend",
        "Return on equity over recent quarters",
        True, RoleType.SCORE, 4, "NSE Fundamentals", "quarterly", -100, 100, None, "%"),
    "earnings_trend": ParameterDefinition(
        "earnings_trend", "Earnings Trend",
        "EPS growth over last 4 quarters",
        True, RoleType.SCORE, 4, "NSE Fundamentals", "quarterly", -100, None, None, "%"),
    "fii_dii_mf_trend": ParameterDefinition(
        "fii_dii_mf_trend", "FII/DII/MF Trend",
        "Foreign/institutional/mutual fund flow direction",
        True, RoleType.SCORE, 4, "NSE Institutional Flows", "weekly", None, None, None, "net flow"),
    "midcap_liquidity_score": ParameterDefinition(
        "midcap_liquidity_score", "Midcap Liquidity Score",
        "Liquidity adequacy for midcap trading (turnover vs market cap)",
        True, RoleType.SCORE, 3, "NSE Price History", "weekly", 0, 100, None, "0-100"),
    "midcap_fii_mf_trend": ParameterDefinition(
        "midcap_fii_mf_trend", "Midcap FII/DII/MF Trend",
        "Foreign/institutional/mutual fund flow direction for midcaps",
        True, RoleType.SCORE, 4, "NSE Institutional Flows", "weekly", None, None, None, "net flow"),
    "historical_news_sentiment": ParameterDefinition(
        "historical_news_sentiment", "News Sentiment Score",
        "NLP-analysed sentiment of company/news articles",
        True, RoleType.SCORE, 4, "News Sentiment Model", "daily", -1, 1, None, "-1..1"),
    "company_valuation": ParameterDefinition(
        "company_valuation", "Company Valuation",
        "Company valuation relative to peers and sector",
        True, RoleType.SCORE, 2, "Financial filings and NSE market data",
        "quarterly", None, None, None, "ratio"),

    # ---------- FILTER (10 params, weight 20) ----------
    "promoter_holding_pct": ParameterDefinition(
        "promoter_holding_pct", "Promoter Holding %",
        "Promoters' equity holding percentage",
        True, RoleType.FILTER, 2, "NSE Shareholding", "quarterly", 0, 100, None, "%"),
    "debt_equity_ratio": ParameterDefinition(
        "debt_equity_ratio", "Debt/Equity Ratio",
        "Total debt divided by equity",
        True, RoleType.FILTER, 2, "NSE Fundamentals", "quarterly", 0, None, None, "x"),
    "interest_coverage": ParameterDefinition(
        "interest_coverage", "Interest Coverage Ratio",
        "EBIT divided by interest expense",
        True, RoleType.FILTER, 2, "NSE Fundamentals", "quarterly", 0, None, None, "x"),
    "cash_flow_positive": ParameterDefinition(
        "cash_flow_positive", "Cash Flow Positive",
        "Operating cash flow above zero",
        True, RoleType.FILTER, 2, "NSE Fundamentals", "quarterly", None, None, None, "bool"),
    "midcap_volatility_adj": ParameterDefinition(
        "midcap_volatility_adj", "Midcap Volatility Adjustment",
        "Volatility adjustment factor for midcap risk management",
        True, RoleType.FILTER, 2, "NSE Price History", "weekly", 0, None, None, "score"),
    "liquidity_floor": ParameterDefinition(
        "liquidity_floor", "Liquidity Floor",
        "Minimum daily turnover for consideration",
        True, RoleType.FILTER, 2, "NSE Volume Data", "daily", 0, None, 25, "crore"),
    "stt_rate_equity": ParameterDefinition(
        "stt_rate_equity", "STT Rate - Equity",
        "Securities Transaction Tax rate (per side)",
        True, RoleType.FILTER, 2, "Config", "fy_update", 0, None, 0.001, "%"),
    "stcg_tax_rate": ParameterDefinition(
        "stcg_tax_rate", "STCG Tax Rate",
        "Short-term capital gains tax rate",
        True, RoleType.FILTER, 2, "Config", "fy_update", 0, 100, 20, "%"),
    "brokerage_rate_param": ParameterDefinition(
        "brokerage_rate", "Brokerage Rate",
        "Per-order brokerage as percentage",
        True, RoleType.FILTER, 2, "Broker API", "per_trade", 0, None, 0.05, "%"),
    "asm_gsm_surveillance": ParameterDefinition(
        "asm_gsm_surveillance", "ASM/GSM Surveillance",
        "ASM/GSM surveillance status from NSE",
        True, RoleType.FILTER, 2, "NSE surveillance reports", "daily", None, None, None, "status"),

    # ---------- VETO (6 params, weight 15) ----------
    "promoter_pledging_pct": ParameterDefinition(
        "promoter_pledging_pct", "Promoter Pledging %",
        "% of promoter holding pledged as security",
        True, RoleType.VETO, 3, "NSE Shareholding", "quarterly", 0, 100, 25, "%"),
    "legal_cases_directors": ParameterDefinition(
        "legal_cases_directors", "Legal Cases - Directors",
        "Serious legal cases against directors/promoters",
        True, RoleType.VETO, 3, "Court Records", "on-event", 0, None, 0, "count"),
    "credit_rating_changes": ParameterDefinition(
        "credit_rating_changes", "Credit Rating Changes",
        "Upgrades/downgrades by rating agencies",
        True, RoleType.VETO, 3, "Credit Agencies", "on-event", None, None, None, "rating"),
    "legal_cases_company_promoters": ParameterDefinition(
        "legal_cases_company_promoters", "Legal Cases - Company/Promoters",
        "Legal cases against companies or promoters",
        True, RoleType.VETO, 2, "Court records", "on-event", 0, None, 0, "count"),
    "auditor_resignations": ParameterDefinition(
        "auditor_resignations", "Auditor Resignations",
        "Auditor resignations during the period",
        True, RoleType.VETO, 2, "Exchange corporate filings", "on-event", 0, None, 0, "count"),
    "cost_vs_edge_check": ParameterDefinition(
        "cost_vs_edge_check", "Cost vs Edge Check",
        "Auto-disable if net edge is zero or negative after costs+tax",
        True, RoleType.VETO, 2, "Internal Calculation", "per_trade", None, None, None, "pass/fail"),

    # ---------- MARKET DIAL (2 params, weight 5) ----------
    "international_war_situation": ParameterDefinition(
        "international_war_situation", "International Situation",
        "Geopolitical risk dial (escalation/reduction)",
        True, RoleType.MARKET_DIAL, 3, "Geopolitical Risk API", "daily", 0, 10, None, "0-10"),
    "government_news": ParameterDefinition(
        "government_news", "Government News",
        "Government releases and news (Press Information Bureau)",
        True, RoleType.MARKET_DIAL, 2, "Press Information Bureau", "on-event", None, None, None, "count"),

    # ---------- ADVISORY (12 params, weight 12) ----------
    "industry_expectations": ParameterDefinition(
        "industry_expectations", "Industry Expectations",
        "Qualitative sentiment on sector outlook",
        True, RoleType.ADVISORY, 1, "Research Reports", "quarterly", None, None, None, ""),
    "swot_analytics": ParameterDefinition(
        "swot_analytics", "SWOT Analytics",
        "Strengths, Weaknesses, Opportunities, Threats",
        True, RoleType.ADVISORY, 1, "Company Reports", "quarterly", 0, 100, None, "0-100"),
    "competitive_plans": ParameterDefinition(
        "competitive_plans", "Competitive Plans",
        "Competitor launches and market share changes",
        True, RoleType.ADVISORY, 1, "Company Reports", "quarterly", 0, 100, None, "0-100"),
    "company_news": ParameterDefinition(
        "company_news", "Company News",
        "Company releases and news",
        True, RoleType.ADVISORY, 1, "Company releases and news", "daily", None, None, None, "count"),
    "company_analytics": ParameterDefinition(
        "company_analytics", "Company Analytics",
        "Financial filings and internal analytics",
        True, RoleType.ADVISORY, 1, "Financial filings and internal analytics",
        "weekly", 0, 100, None, "0-100"),
    "customer_feedback": ParameterDefinition(
        "customer_feedback", "Company Customer Feedback",
        "Published customer research",
        True, RoleType.ADVISORY, 1, "Published customer research", "monthly", 0, 100, None, "0-100"),
    "ownership_breakdown": ParameterDefinition(
        "ownership_breakdown", "Ownership Breakdown",
        "Ownership by promoters, government, institutions, funds and individuals",
        True, RoleType.ADVISORY, 1, "Exchange shareholding filings", "quarterly", 0, 100, None, "%"),
    "historical_price_series": ParameterDefinition(
        "historical_price_series", "Historical Price Series",
        "Historical price series (daily, weekly, monthly, yearly)",
        True, RoleType.ADVISORY, 1, "NSE historical market data", "daily", None, None, None, "series"),
    "unique_features": ParameterDefinition(
        "unique_features", "Unique Company Features",
        "Unique company features",
        True, RoleType.ADVISORY, 1, "Company filings", "quarterly", None, None, None, "list"),
    "stock_recommendation_reports": ParameterDefinition(
        "stock_recommendation_reports", "Stock Recommendation Reports",
        "Broker research recommendation reports",
        True, RoleType.ADVISORY, 1, "Broker research", "weekly", None, None, None, "rating"),
    "company_collaborations": ParameterDefinition(
        "company_collaborations", "Company Collaborations",
        "Company collaborations and partnerships",
        True, RoleType.ADVISORY, 1, "Exchange corporate filings", "on-event", 0, None, None, "count"),
    "historical_news": ParameterDefinition(
        "historical_news", "Historical News",
        "Historical news archives",
        True, RoleType.ADVISORY, 1, "News archives", "weekly", -1, 1, None, "-1..1"),

    # ---------- FLAG (5 params, weight 5) ----------
    "midcap_corp_action": ParameterDefinition(
        "midcap_corp_action", "Midcap Corporate Action",
        "Corporate actions affecting midcap stocks",
        True, RoleType.FLAG, 1, "NSE Corporate Actions", "on-event", 0, None, None, "count"),
    "corporate_actions": ParameterDefinition(
        "corporate_actions", "Corporate Actions",
        "Corporate actions affecting stocks",
        True, RoleType.FLAG, 1, "NSE and BSE corporate actions", "on-event", 0, None, None, "count"),
    "political_incidents": ParameterDefinition(
        "political_incidents", "Political Incidents",
        "Political incidents impacting markets",
        True, RoleType.FLAG, 1, "Government releases and news", "on-event", 0, None, None, "count"),
    "regulator_announcements": ParameterDefinition(
        "regulator_announcements", "Regulator Announcements",
        "SEBI, RBI, NSE and BSE announcements",
        True, RoleType.FLAG, 1, "SEBI/RBI/NSE/BSE", "on-event", 0, None, None, "count"),
    "bulk_block_deals": ParameterDefinition(
        "bulk_block_deals", "Bulk/Block Deals",
        "Large block trades in the week",
        True, RoleType.FLAG, 1, "NSE Corporate Filings", "daily", 0, None, None, "count"),
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


if not validate_weight_total():
    import warnings
    warnings.warn(
        f"Parameter catalogue weight total is {get_total_weight()}, not 100. "
        "BRD compliance may be affected.",
        stacklevel=2,
    )
"""Data Source Catalogue for SI-Trader's 48 Parameters.

Maps every parameter in the parameter catalogue to its actual data source,
refresh schedule, data provider, API endpoint, and validation rules.

This module provides the single source of truth for all data ingestion
across the SI-Trader platform.

Data Source Categories:
1. NSE Price History - Price/volume data from NSE (price_momentum, liquidity)
2. NSE Fundamentals - Company financials from NSE/BSE filings (PE, ROE, debt, cash flow)
3. NSE Shareholding - Promoter/FII/DII/MF shareholding data from NSE
4. NSE Corporate Actions - Results, dividends, ASM/GSM from NSE
5. SEBI/RBI/NSE/BSE Announcements - Regulatory circulars from exchanges
6. News & Sentiment - News sentiment from news providers
7. Geopolitical & Government - War situations, government news, political incidents
8. Court Records - Legal cases against directors/promoters
9. Credit Rating Agencies - Credit rating upgrades/downgrades
10. Broker Research - Stock recommendation reports
11. Exchange Circulars - SEBI/RBI/NSE/BSE circulars
12. Internal Calculation - Cost vs edge check (computed internally)
13. Config - STT, STCG tax rates (configured by BRD)
14. Broker API - Brokerage rates (from broker API)

Each data source has:
- parameter_keys: List of parameter keys that use this source
- refresh_schedule: How often data is refreshed (daily/weekly/monthly/quarterly/on-event/fy_update/per_trade)
- source_type: The type of data source (price, fundamental, shareholding, news, etc.)
- api_endpoint: API endpoint template
- data_provider: The actual data provider name
- validation_rules: Validation rules for the data
- priority: Priority level for data fetching (1=critical, 2=important, 3=optional)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """Type of data source."""
    PRICE = "price"                    # Price/volume data
    FUNDAMENTAL = "fundamental"        # Financial statements
    SHAREHOLDING = "shareholding"      # Promoter/FII/DII/MF shareholding
    CORPORATE_ACTION = "corporate_action"  # Results, dividends, ASM/GSM
    REGULATORY = "regulatory"          # SEBI/RBI/NSE/BSE circulars
    NEWS_SENTIMENT = "news_sentiment"  # News sentiment analysis
    GEOPOLITICAL = "geopolitical"      # Geopolitical events
    GOVERNMENT = "government"          # Government announcements
    LEGAL = "legal"                    # Court cases
    CREDIT_RATING = "credit_rating"    # Credit rating changes
    BROKER_RESEARCH = "broker_research"  # Broker recommendation reports
    INTERNAL = "internal"              # Internal calculations
    CONFIG = "config"                  # Configuration values
    BROKER_API = "broker_api"          # Broker API data


class RefreshSchedule(Enum):
    """Data refresh schedule."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ON_EVENT = "on-event"
    FY_UPDATE = "fy_update"
    PER_TRADE = "per_trade"
    ANNUALLY = "annually"


class DataPriority(Enum):
    """Data priority for fetching."""
    CRITICAL = 1   # Must have for trading
    IMPORTANT = 2  # Important for scoring
    OPTIONAL = 3   # Nice to have


@dataclass
class DataSourceConfig:
    """Configuration for a data source."""
    source_name: str
    source_type: DataSourceType
    refresh_schedule: RefreshSchedule
    api_endpoint: str
    data_provider: str
    priority: DataPriority
    validation_rules: List[str] = field(default_factory=list)
    rate_limit_per_minute: int = 60
    timeout_seconds: int = 30
    retry_count: int = 3
    requires_auth: bool = False
    api_key_env_var: Optional[str] = None


# =============================================================================
# DATA SOURCE CATALOGUE - Maps each parameter to its data source
# =============================================================================

# Define all data sources used by the 48 parameters
DATA_SOURCES: Dict[str, DataSourceConfig] = {

    # ===== PRICE & VOLUME DATA (NSE) =====
    "nse_price_history": DataSourceConfig(
        source_name="NSE Price History",
        source_type=DataSourceType.PRICE,
        refresh_schedule=RefreshSchedule.DAILY,
        api_endpoint="https://www.nseindia.com/api/historical/cm/equity?symbol={symbol}&from={from_date}&to={to_date}",
        data_provider="NSE India",
        priority=DataPriority.CRITICAL,
        validation_rules=["price > 0", "volume > 0", "date_format=YYYY-MM-DD"],
        rate_limit_per_minute=30,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    # ===== FUNDAMENTAL DATA (NSE/BSE Filings) =====
    "nse_fundamentals": DataSourceConfig(
        source_name="NSE Fundamentals",
        source_type=DataSourceType.FUNDAMENTAL,
        refresh_schedule=RefreshSchedule.QUARTERLY,
        api_endpoint="https://www.nseindia.com/api/corporate-financial-results?symbol={symbol}",
        data_provider="NSE India",
        priority=DataPriority.CRITICAL,
        validation_rules=["pe_ratio > 0", "roe >= -100", "debt_equity >= 0", "cash_flow can be negative"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    "nse_financial_statements": DataSourceConfig(
        source_name="NSE Financial Statements",
        source_type=DataSourceType.FUNDAMENTAL,
        refresh_schedule=RefreshSchedule.QUARTERLY,
        api_endpoint="https://www.nseindia.com/api/corporate-filings?symbol={symbol}&type=financial",
        data_provider="NSE India",
        priority=DataPriority.CRITICAL,
        validation_rules=["revenue > 0", "net_profit can be negative", "total_assets > 0"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    # ===== SHAREHOLDING DATA (NSE) =====
    "nse_shareholding": DataSourceConfig(
        source_name="NSE Shareholding Pattern",
        source_type=DataSourceType.SHAREHOLDING,
        refresh_schedule=RefreshSchedule.QUARTERLY,
        api_endpoint="https://www.nseindia.com/api/corporate-shareholding?symbol={symbol}",
        data_provider="NSE India",
        priority=DataPriority.CRITICAL,
        validation_rules=["promoter_holding >= 0", "promoter_pledging >= 0", "promoter_pledging <= promoter_holding"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    "nse_institutional_flows": DataSourceConfig(
        source_name="NSE Institutional Flows",
        source_type=DataSourceType.SHAREHOLDING,
        refresh_schedule=RefreshSchedule.WEEKLY,
        api_endpoint="https://www.nseindia.com/api/fii-dii-data?symbol={symbol}",
        data_provider="NSE India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["fii_net can be negative", "dii_net can be negative", "mf_net can be negative"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    # ===== CORPORATE ACTIONS (NSE/BSE) =====
    "nse_corporate_actions": DataSourceConfig(
        source_name="NSE Corporate Actions",
        source_type=DataSourceType.CORPORATE_ACTION,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://www.nseindia.com/api/corporate-actions?symbol={symbol}",
        data_provider="NSE India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["result_date not null", "dividend_amount >= 0", "asm_gsm_status in [ASM, GSM, None]"],
        rate_limit_per_minute=30,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    "bse_corporate_actions": DataSourceConfig(
        source_name="BSE Corporate Actions",
        source_type=DataSourceType.CORPORATE_ACTION,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://api.bseindia.com/corporate-actions?scripcode={scrip_code}",
        data_provider="BSE India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["result_date not null", "dividend_amount >= 0"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    # ===== REGULATORY ANNOUNCEMENTS (SEBI/RBI/NSE/BSE) =====
    "sebi_announcements": DataSourceConfig(
        source_name="SEBI Announcements",
        source_type=DataSourceType.REGULATORY,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://www.sebi.gov.in/api/announcements?date={date}",
        data_provider="SEBI India",
        priority=DataPriority.CRITICAL,
        validation_rules=["announcement_date not null", "circular_type not null"],
        rate_limit_per_minute=10,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    "rbi_announcements": DataSourceConfig(
        source_name="RBI Announcements",
        source_type=DataSourceType.REGULATORY,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://www.rbi.org.in/api/announcements?date={date}",
        data_provider="RBI India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["announcement_date not null", "circular_type not null"],
        rate_limit_per_minute=10,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    "nse_announcements": DataSourceConfig(
        source_name="NSE Announcements",
        source_type=DataSourceType.REGULATORY,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://www.nseindia.com/api/announcements?symbol={symbol}",
        data_provider="NSE India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["announcement_date not null"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    "bse_announcements": DataSourceConfig(
        source_name="BSE Announcements",
        source_type=DataSourceType.REGULATORY,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://api.bseindia.com/announcements?scripcode={scrip_code}",
        data_provider="BSE India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["announcement_date not null"],
        rate_limit_per_minute=20,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    # ===== NEWS & SENTIMENT =====
    "news_sentiment_api": DataSourceConfig(
        source_name="News Sentiment API",
        source_type=DataSourceType.NEWS_SENTIMENT,
        refresh_schedule=RefreshSchedule.DAILY,
        api_endpoint="https://newsapi.org/v2/everything?q={symbol}&language=en&sortBy=publishedAt",
        data_provider="NewsAPI.org / Google News",
        priority=DataPriority.IMPORTANT,
        validation_rules=["sentiment_score between -1 and 1", "article_date not null"],
        rate_limit_per_minute=100,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=True,
        api_key_env_var="NEWS_API_KEY",
    ),

    # ===== GEOPOLITICAL & GOVERNMENT =====
    "geopolitical_risk_api": DataSourceConfig(
        source_name="Geopolitical Risk API",
        source_type=DataSourceType.GEOPOLITICAL,
        refresh_schedule=RefreshSchedule.DAILY,
        api_endpoint="https://api.geopolitical-risk.com/v1/risk-indicators",
        data_provider="Geopolitical Risk Providers",
        priority=DataPriority.IMPORTANT,
        validation_rules=["risk_score between 0 and 10", "region not null"],
        rate_limit_per_minute=60,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=True,
        api_key_env_var="GEOPOLITICAL_API_KEY",
    ),

    "government_news_api": DataSourceConfig(
        source_name="Government News API",
        source_type=DataSourceType.GOVERNMENT,
        refresh_schedule=RefreshSchedule.DAILY,
        api_endpoint="https://api.pib.gov.in/v1/press-releases?date={date}",
        data_provider="Press Information Bureau (PIB) India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["release_date not null", "category not null"],
        rate_limit_per_minute=60,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=False,
    ),

    # ===== LEGAL CASES =====
    "court_records_api": DataSourceConfig(
        source_name="Court Records API",
        source_type=DataSourceType.LEGAL,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://api.ecourts.gov.in/v1/case-status?case_number={case_number}",
        data_provider="eCourts India",
        priority=DataPriority.IMPORTANT,
        validation_rules=["case_number not null", "case_status not null"],
        rate_limit_per_minute=30,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=True,
        api_key_env_var="ECOURTS_API_KEY",
    ),

    # ===== CREDIT RATING =====
    "credit_rating_api": DataSourceConfig(
        source_name="Credit Rating API",
        source_type=DataSourceType.CREDIT_RATING,
        refresh_schedule=RefreshSchedule.ON_EVENT,
        api_endpoint="https://api.crisil.com/v1/ratings?company={symbol}",
        data_provider="CRISIL / ICRA / CARE Ratings",
        priority=DataPriority.IMPORTANT,
        validation_rules=["rating not null", "rating_date not null"],
        rate_limit_per_minute=30,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=True,
        api_key_env_var="CREDIT_RATING_API_KEY",
    ),

    # ===== BROKER RESEARCH =====
    "broker_research_api": DataSourceConfig(
        source_name="Broker Research Reports",
        source_type=DataSourceType.BROKER_RESEARCH,
        refresh_schedule=RefreshSchedule.WEEKLY,
        api_endpoint="https://api.broker-research.com/v1/recommendations?symbol={symbol}",
        data_provider="Multiple Broker Research Desks",
        priority=DataPriority.IMPORTANT,
        validation_rules=["recommendation in [BUY, SELL, HOLD, ACCUMULATE, REDUCE]", "target_price > 0"],
        rate_limit_per_minute=60,
        timeout_seconds=30,
        retry_count=3,
        requires_auth=True,
        api_key_env_var="BROKER_RESEARCH_API_KEY",
    ),

    # ===== INTERNAL CALCULATION =====
    "internal_cost_model": DataSourceConfig(
        source_name="Internal Cost Model",
        source_type=DataSourceType.INTERNAL,
        refresh_schedule=RefreshSchedule.PER_TRADE,
        api_endpoint="internal://cost-model",
        data_provider="SI-Trader Internal",
        priority=DataPriority.CRITICAL,
        validation_rules=["stt_rate > 0", "stcg_tax_rate > 0", "brokerage_rate > 0"],
        rate_limit_per_minute=1000,
        timeout_seconds=5,
        retry_count=1,
        requires_auth=False,
    ),

    # ===== CONFIG VALUES =====
    "config_values": DataSourceConfig(
        source_name="Configuration Values",
        source_type=DataSourceType.CONFIG,
        refresh_schedule=RefreshSchedule.FY_UPDATE,
        api_endpoint="internal://config",
        data_provider="SI-Trader Configuration",
        priority=DataPriority.CRITICAL,
        validation_rules=["stt_rate_equity == 0.001", "stcg_tax_rate == 0.20", "brokerage_rate > 0"],
        rate_limit_per_minute=1000,
        timeout_seconds=5,
        retry_count=1,
        requires_auth=False,
    ),

    # ===== BROKER API =====
    "broker_api_rates": DataSourceConfig(
        source_name="Broker API Rates",
        source_type=DataSourceType.BROKER_API,
        refresh_schedule=RefreshSchedule.PER_TRADE,
        api_endpoint="internal://broker-rates",
        data_provider="Connected Broker API",
        priority=DataPriority.CRITICAL,
        validation_rules=["brokerage_rate > 0"],
        rate_limit_per_minute=1000,
        timeout_seconds=5,
        retry_count=1,
        requires_auth=False,
    ),
}


# =============================================================================
# PARAMETER TO DATA SOURCE MAPPING
# Maps each of the 48 parameters to its data source configuration
# =============================================================================

PARAMETER_TO_DATA_SOURCE: Dict[str, DataSourceConfig] = {

    # --- Momentum Parameters (Score) ---
    "price_momentum_weekly": DATA_SOURCES["nse_price_history"],
    "price_momentum_monthly": DATA_SOURCES["nse_price_history"],
    "price_momentum_yearly": DATA_SOURCES["nse_price_history"],

    # --- Fundamental Scores ---
    "f_score": DATA_SOURCES["nse_fundamentals"],
    "altman_z_score": DATA_SOURCES["nse_financial_statements"],

    # --- Valuation Parameters ---
    "pe_ratio_vs_sector": DATA_SOURCES["nse_fundamentals"],

    # --- Shareholding Parameters ---
    "promoter_holding_pct": DATA_SOURCES["nse_shareholding"],
    "promoter_pledging_pct": DATA_SOURCES["nse_shareholding"],
    "fii_dii_mf_trend": DATA_SOURCES["nse_institutional_flows"],

    # --- Midcap Specific ---
    "midcap_liquidity_score": DATA_SOURCES["nse_price_history"],
    "midcap_fii_mf_trend": DATA_SOURCES["nse_institutional_flows"],
    "midcap_volatility_adj": DATA_SOURCES["nse_price_history"],
    "midcap_corp_action": DATA_SOURCES["nse_corporate_actions"],

    # --- Market Dial ---
    "international_war_situation": DATA_SOURCES["geopolitical_risk_api"],

    # --- Sentiment ---
    "historical_news_sentiment": DATA_SOURCES["news_sentiment_api"],

    # --- SWOT & Competition ---
    "swot_analytics": DATA_SOURCES["nse_financial_statements"],  # Uses financial data for SWOT
    "competitive_plans": DATA_SOURCES["broker_research_api"],    # Uses broker research for competitive plans

    # --- Legal Cases ---
    "legal_cases_directors": DATA_SOURCES["court_records_api"],

    # --- Credit Rating ---
    "credit_rating_changes": DATA_SOURCES["credit_rating_api"],

    # --- Cost & Edge Parameters ---
    "liquidity_floor": DATA_SOURCES["nse_price_history"],
    "cost_vs_edge_check": DATA_SOURCES["internal_cost_model"],
    "stt_rate_equity": DATA_SOURCES["config_values"],
    "stcg_tax_rate": DATA_SOURCES["config_values"],
    "brokerage_rate": DATA_SOURCES["broker_api_rates"],

    # --- Additional Parameters (Disabled by default but configured) ---
    "stock_recommendation_reports": DATA_SOURCES["broker_research_api"],
    "company_news": DATA_SOURCES["news_sentiment_api"],
    "government_news": DATA_SOURCES["government_news_api"],
    "political_incidents": DATA_SOURCES["government_news_api"],
    "regulator_announcements": DATA_SOURCES["sebi_announcements"],
    "historical_price_series": DATA_SOURCES["nse_price_history"],
    "historical_news": DATA_SOURCES["news_sentiment_api"],
    "corporate_actions": DATA_SOURCES["nse_corporate_actions"],
    "predictive_analytics": DATA_SOURCES["internal_cost_model"],
    "unique_features": DATA_SOURCES["nse_financial_statements"],
    "customer_feedback": DATA_SOURCES["news_sentiment_api"],
    "ownership_breakdown": DATA_SOURCES["nse_shareholding"],
    "company_valuation": DATA_SOURCES["nse_financial_statements"],
    "company_analytics": DATA_SOURCES["nse_financial_statements"],
    "company_collaborations": DATA_SOURCES["nse_corporate_actions"],
    "legal_cases_company_promoters": DATA_SOURCES["court_records_api"],
    "auditor_resignations": DATA_SOURCES["nse_corporate_actions"],
    "asm_gsm_surveillance": DATA_SOURCES["nse_corporate_actions"],
}


# =============================================================================
# PARAMETER TO REFRESH SCHEDULE MAPPING
# =============================================================================

PARAMETER_REFRESH_SCHEDULE: Dict[str, str] = {
    # Price/Momentum
    "price_momentum_weekly": "weekly",
    "price_momentum_monthly": "monthly",
    "price_momentum_yearly": "yearly",
    "price_momentum_daily": "daily",

    # Fundamental Scores
    "f_score": "quarterly",
    "altman_z_score": "quarterly",

    # Valuation
    "pe_ratio_vs_sector": "quarterly",

    # Shareholding
    "promoter_holding_pct": "quarterly",
    "promoter_pledging_pct": "quarterly",
    "fii_dii_mf_trend": "weekly",

    # Midcap
    "midcap_liquidity_score": "daily",
    "midcap_fii_mf_trend": "weekly",
    "midcap_volatility_adj": "daily",
    "midcap_corp_action": "on-event",

    # Market Dial
    "international_war_situation": "daily",

    # Sentiment
    "historical_news_sentiment": "daily",

    # SWOT & Competition
    "swot_analytics": "quarterly",
    "competitive_plans": "annually",

    # Legal & Credit
    "legal_cases_directors": "on-event",
    "credit_rating_changes": "on-event",

    # Cost & Edge
    "liquidity_floor": "daily",
    "cost_vs_edge_check": "per_trade",
    "stt_rate_equity": "fy_update",
    "stcg_tax_rate": "fy_update",
    "brokerage_rate": "per_trade",

    # Additional Parameters
    "stock_recommendation_reports": "weekly",
    "company_news": "daily",
    "government_news": "on-event",
    "political_incidents": "on-event",
    "regulator_announcements": "on-event",
    "historical_price_series": "daily",
    "historical_news": "weekly",
    "corporate_actions": "on-event",
    "predictive_analytics": "weekly",
    "unique_features": "quarterly",
    "customer_feedback": "monthly",
    "ownership_breakdown": "quarterly",
    "company_valuation": "quarterly",
    "company_analytics": "weekly",
    "company_collaborations": "on-event",
    "legal_cases_company_promoters": "on-event",
    "auditor_resignations": "on-event",
    "asm_gsm_surveillance": "daily",
}


# =============================================================================
# VALIDATION RULES BY PARAMETER
# =============================================================================

PARAMETER_VALIDATION_RULES: Dict[str, List[str]] = {
    "price_momentum_weekly": ["value between -100 and 100", "not null"],
    "price_momentum_monthly": ["value between -100 and 100", "not null"],
    "price_momentum_yearly": ["value between -100 and 100", "not null"],
    "f_score": ["integer between 0 and 9"],
    "altman_z_score": ["numeric", "not null"],
    "pe_ratio_vs_sector": ["positive number", "not null"],
    "promoter_holding_pct": ["between 0 and 100"],
    "promoter_pledging_pct": ["between 0 and 100", "must be <= promoter_holding"],
    "fii_dii_mf_trend": ["numeric", "not null"],
    "midcap_liquidity_score": ["between 0 and 100"],
    "midcap_fii_mf_trend": ["numeric", "not null"],
    "midcap_volatility_adj": ["positive number"],
    "midcap_corp_action": ["boolean or event type"],
    "international_war_situation": ["between 0 and 10"],
    "historical_news_sentiment": ["between -1 and 1"],
    "swot_analytics": ["between 0 and 100"],
    "competitive_plans": ["between 0 and 100"],
    "legal_cases_directors": ["integer >= 0"],
    "credit_rating_changes": ["string or numeric rating"],
    "liquidity_floor": ["positive number"],
    "cost_vs_edge_check": ["boolean or numeric edge"],
    "stt_rate_equity": ["positive decimal"],
    "stcg_tax_rate": ["between 0 and 100"],
    "brokerage_rate": ["positive decimal"],
}


def get_parameter_data_source(parameter_key: str) -> Optional[DataSourceConfig]:
    """Get the data source configuration for a parameter."""
    return DATA_SOURCES.get(PARAMETER_CATALOGUE.get(parameter_key, {}).get("source", ""), None)


def get_parameters_by_data_source(source_name: str) -> List[str]:
    """Get all parameters that use a specific data source."""
    return [
        key for key, source in PARAMETER_TO_DATA_SOURCE.items()
        if source.source_name == source_name
    ]


def get_parameters_by_refresh_schedule(schedule: str) -> List[str]:
    """Get all parameters that need refreshing on a specific schedule."""
    return [
        key for key, sched in PARAMETER_REFRESH_SCHEDULE.items()
        if sched == schedule
    ]


def validate_parameter_value(parameter_key: str, value: Any) -> tuple[bool, Optional[str]]:
    """Validate a parameter value against its validation rules."""
    rules = PARAMETER_VALIDATION_RULES.get(parameter_key, [])
    if not rules:
        return True, None

    # Basic validation checks
    try:
        if "between 0 and 100" in rules:
            val = float(value)
            if not (0 <= val <= 100):
                return False, f"Value {val} not between 0 and 100"
        if "between -100 and 100" in rules:
            val = float(value)
            if not (-100 <= val <= 100):
                return False, f"Value {val} not between -100 and 100"
        if "between -1 and 1" in rules:
            val = float(value)
            if not (-1 <= val <= 1):
                return False, f"Value {val} not between -1 and 1"
        if "integer between 0 and 9" in rules:
            val = int(value)
            if not (0 <= val <= 9):
                return False, f"Value {val} not between 0 and 9"
        if "positive number" in rules:
            val = float(value)
            if val <= 0:
                return False, f"Value {val} must be positive"
        if "not null" in rules:
            if value is None or value == "":
                return False, "Value cannot be null"
    except (ValueError, TypeError):
        return False, f"Invalid value format: {value}"

    return True, None
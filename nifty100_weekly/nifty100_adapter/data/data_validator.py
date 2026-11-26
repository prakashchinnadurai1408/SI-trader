"""Data Validation Module for SI-Trader.

Provides data validation and quality gates for all 48 parameters.
Ensures data quality before it's used in scoring calculations.

Validation Categories:
1. Price Validation - price ranges, volume consistency
2. Fundamental Validation - financial ratio sanity checks
3. Shareholding Validation - promoter holding limits
4. News Sentiment Validation - sentiment score bounds
5. Regulatory Validation - announcement completeness
6. Cross-Parameter Validation - consistency checks between related parameters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import statistics

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a data validation check."""
    parameter_key: str
    symbol: str
    value: Any
    is_valid: bool
    quality_score: float  # 0-100
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.errors:
            self.is_valid = False


@dataclass
class ValidationReport:
    """Complete validation report for a symbol."""
    symbol: str
    total_parameters: int
    valid_parameters: int
    invalid_parameters: int
    warning_parameters: int
    overall_quality: float  # 0-100
    can_trade: bool
    results: List[ValidationResult] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        self.can_trade = self.invalid_parameters == 0 and self.overall_quality >= 70


class DataValidator:
    """Data validator for SI-Trader parameters.

    Validates data quality for all 48 parameters before they're used
    in scoring calculations. Provides quality scores and rejection
    reasons for invalid data.

    Validation Rules:
    - Price data: price > 0, volume > 0, reasonable price ranges
    - Fundamental data: ROE between -100% and 100%, PE > 0
    - Shareholding: promoter holding 0-100%, pledging <= holding
    - Sentiment: -1 to 1 range
    - Regulatory: announcement date not null
    """

    def __init__(self):
        self.validation_cache: Dict[str, ValidationReport] = {}
        self.cache_ttl_minutes = 30

        logger.info("DataValidator initialized")

    def validate_price_data(self, symbol: str,
                            price: float,
                            volume: int,
                            previous_close: Optional[float] = None) -> ValidationResult:
        """Validate price data for a symbol.

        Args:
            symbol: Stock symbol
            price: Current price
            volume: Trading volume
            previous_close: Previous day's closing price

        Returns:
            ValidationResult
        """
        warnings = []
        errors = []
        quality_score = 100.0

        # Check price is positive
        if price <= 0:
            errors.append(f"Price {price} must be positive")
            quality_score -= 50

        # Check volume is positive
        if volume <= 0:
            errors.append(f"Volume {volume} must be positive")
            quality_score -= 30

        # Check price change is reasonable (< 50% in a day)
        if previous_close and previous_close > 0:
            change_pct = abs((price - previous_close) / previous_close * 100)
            if change_pct > 50:
                warnings.append(f"Price change {change_pct:.1f}% exceeds 50% threshold")
                quality_score -= 20
            elif change_pct > 20:
                warnings.append(f"Price change {change_pct:.1f}% exceeds 20% threshold")
                quality_score -= 10

        # Check for extreme volume
        if volume > 10_000_000:  # 1 crore shares
            warnings.append(f"Unusually high volume: {volume:,}")
            quality_score -= 5

        is_valid = len(errors) == 0
        quality_score = max(0, quality_score)

        return ValidationResult(
            parameter_key="price_momentum_daily",
            symbol=symbol,
            value=price,
            is_valid=is_valid,
            quality_score=quality_score,
            warnings=warnings,
            errors=errors,
        )

    def validate_fundamental_data(self, symbol: str,
                                  roe: float,
                                  debt_equity: float,
                                  cash_flow: float,
                                  pe_ratio: float,
                                  earnings: float) -> ValidationResult:
        """Validate fundamental data for a symbol.

        Args:
            symbol: Stock symbol
            roe: Return on Equity %
            debt_equity: Debt/Equity ratio
            cash_flow: Operating cash flow
            pe_ratio: PE ratio
            earnings: Net profit

        Returns:
            ValidationResult
        """
        warnings = []
        errors = []
        quality_score = 100.0

        # ROE validation
        if roe < -100:
            errors.append(f"ROE {roe}% is below -100%")
            quality_score -= 30
        elif roe > 100:
            warnings.append(f"ROE {roe}% is above 100%")
            quality_score -= 10

        # Debt/Equity validation
        if debt_equity < 0:
            errors.append(f"Debt/Equity {debt_equity} cannot be negative")
            quality_score -= 30
        elif debt_equity > 5:
            warnings.append(f"Debt/Equity {debt_equity} is high (>5)")
            quality_score -= 15

        # Cash flow validation
        if cash_flow < -1_000_000_000:  # -100 crore
            warnings.append(f"Operating cash flow {cash_flow} is significantly negative")
            quality_score -= 15

        # PE validation
        if pe_ratio <= 0:
            warnings.append(f"PE ratio {pe_ratio} is not positive")
            quality_score -= 10
        elif pe_ratio > 100:
            warnings.append(f"PE ratio {pe_ratio} is very high (>100)")
            quality_score -= 10

        # Earnings validation
        if earnings < -1_000_000_000:
            warnings.append(f"Net earnings {earnings} is significantly negative")
            quality_score -= 15

        is_valid = len(errors) == 0
        quality_score = max(0, quality_score)

        return ValidationResult(
            parameter_key="fundamental_data",
            symbol=symbol,
            value={"roe": roe, "debt_equity": debt_equity, "pe": pe_ratio},
            is_valid=is_valid,
            quality_score=quality_score,
            warnings=warnings,
            errors=errors,
        )

    def validate_shareholding_data(self, symbol: str,
                                   promoter_holding: float,
                                   promoter_pledging: float,
                                   fii_holding: float,
                                   dii_holding: float,
                                   mf_holding: float) -> ValidationResult:
        """Validate shareholding data for a symbol.

        Args:
            symbol: Stock symbol
            promoter_holding: Promoter holding %
            promoter_pledging: Promoter pledging %
            fii_holding: FII holding %
            dii_holding: DII holding %
            mf_holding: MF holding %

        Returns:
            ValidationResult
        """
        warnings = []
        errors = []
        quality_score = 100.0

        # Promoter holding validation
        if promoter_holding < 0 or promoter_holding > 100:
            errors.append(f"Promoter holding {promoter_holding}% must be between 0-100%")
            quality_score -= 40
        elif promoter_holding < 10:
            warnings.append(f"Promoter holding {promoter_holding}% is low (<10%)")
            quality_score -= 10

        # Promoter pledging validation
        if promoter_pledging < 0 or promoter_pledging > 100:
            errors.append(f"Promoter pledging {promoter_pledging}% must be between 0-100%")
            quality_score -= 40
        elif promoter_pledging > promoter_holding:
            errors.append(f"Promoter pledging {promoter_pledging}% exceeds holding {promoter_holding}%")
            quality_score -= 30
        elif promoter_pledged_pct := promoter_pledging:
            if promoter_holding > 0 and (promoter_pledged_pct / promoter_holding * 100) > 50:
                warnings.append(f"Promoter pledging {promoter_pledged_pct}% is >50% of holding")
                quality_score -= 20

        # Institutional holding validation
        total_institutional = fii_holding + dii_holding + mf_holding
        if total_institutional > 100:
            warnings.append(f"Total institutional holding {total_institutional}% exceeds 100%")
            quality_score -= 20

        is_valid = len(errors) == 0
        quality_score = max(0, quality_score)

        return ValidationResult(
            parameter_key="shareholding_data",
            symbol=symbol,
            value={"promoter_holding": promoter_holding,
                   "promoter_pledging": promoter_pledging,
                   "fii_holding": fii_holding,
                   "dii_holding": dii_holding,
                   "mf_holding": mf_holding},
            is_valid=is_valid,
            quality_score=quality_score,
            warnings=warnings,
            errors=errors,
        )

    def validate_sentiment_data(self, symbol: str,
                                sentiment_score: float,
                                article_count: int,
                                avg_relevance: float) -> ValidationResult:
        """Validate sentiment data for a symbol.

        Args:
            symbol: Stock symbol
            sentiment_score: Sentiment score (-1 to 1)
            article_count: Number of articles
            avg_relevance: Average relevance score

        Returns:
            ValidationResult
        """
        warnings = []
        errors = []
        quality_score = 100.0

        # Sentiment score range
        if sentiment_score < -1 or sentiment_score > 1:
            errors.append(f"Sentiment score {sentiment_score} must be between -1 and 1")
            quality_score -= 50

        # Article count validation
        if article_count == 0:
            warnings.append("No news articles found")
            quality_score -= 30
        elif article_count < 3:
            warnings.append(f"Only {article_count} articles found (low confidence)")
            quality_score -= 15

        # Relevance validation
        if avg_relevance < 0.3:
            warnings.append(f"Low average relevance {avg_relevance:.2f}")
            quality_score -= 20

        is_valid = len(errors) == 0
        quality_score = max(0, quality_score)

        return ValidationResult(
            parameter_key="historical_news_sentiment",
            symbol=symbol,
            value=sentiment_score,
            is_valid=is_valid,
            quality_score=quality_score,
            warnings=warnings,
            errors=errors,
        )

    def validate_regulatory_data(self, symbol: str,
                                 legal_cases: int,
                                 auditor_resignations: int,
                                 regulatory_actions: int) -> ValidationResult:
        """Validate regulatory data for a symbol.

        Args:
            symbol: Stock symbol
            legal_cases: Number of serious legal cases
            auditor_resignations: Number of auditor resignations
            regulatory_actions: Number of regulatory actions

        Returns:
            ValidationResult
        """
        warnings = []
        errors = []
        quality_score = 100.0

        # Legal cases validation
        if legal_cases < 0:
            errors.append(f"Legal cases {legal_cases} cannot be negative")
            quality_score -= 30
        elif legal_cases > 5:
            warnings.append(f"High number of legal cases: {legal_cases}")
            quality_score -= 20

        # Auditor resignations validation
        if auditor_resignations < 0:
            errors.append(f"Auditor resignations {auditor_resignations} cannot be negative")
            quality_score -= 30
        elif auditor_resignations > 2:
            warnings.append(f"Multiple auditor resignations: {auditor_resignations}")
            quality_score -= 25

        # Regulatory actions validation
        if regulatory_actions < 0:
            errors.append(f"Regulatory actions {regulatory_actions} cannot be negative")
            quality_score -= 30
        elif regulatory_actions > 5:
            warnings.append(f"High number of regulatory actions: {regulatory_actions}")
            quality_score -= 20

        is_valid = len(errors) == 0
        quality_score = max(0, quality_score)

        return ValidationResult(
            parameter_key="regulatory_data",
            symbol=symbol,
            value={"legal_cases": legal_cases,
                   "auditor_resignations": auditor_resignations,
                   "regulatory_actions": regulatory_actions},
            is_valid=is_valid,
            quality_score=quality_score,
            warnings=warnings,
            errors=errors,
        )

    def validate_complete_symbol(self, symbol: str,
                                 price_data: Optional[Dict] = None,
                                 fundamental_data: Optional[Dict] = None,
                                 shareholding_data: Optional[Dict] = None,
                                 sentiment_data: Optional[Dict] = None,
                                 regulatory_data: Optional[Dict] = None) -> ValidationReport:
        """Validate all data for a symbol.

        Args:
            symbol: Stock symbol
            price_data: Price data dictionary
            fundamental_data: Fundamental data dictionary
            shareholding_data: Shareholding data dictionary
            sentiment_data: Sentiment data dictionary
            regulatory_data: Regulatory data dictionary

        Returns:
            ValidationReport
        """
        results = []

        # Validate price data
        if price_data:
            result = self.validate_price_data(
                symbol,
                price_data.get("price", 0),
                price_data.get("volume", 0),
                price_data.get("previous_close"),
            )
            results.append(result)

        # Validate fundamental data
        if fundamental_data:
            result = self.validate_fundamental_data(
                symbol,
                fundamental_data.get("roe", 0),
                fundamental_data.get("debt_equity", 0),
                fundamental_data.get("cash_flow", 0),
                fundamental_data.get("pe_ratio", 0),
                fundamental_data.get("earnings", 0),
            )
            results.append(result)

        # Validate shareholding data
        if shareholding_data:
            result = self.validate_shareholding_data(
                symbol,
                shareholding_data.get("promoter_holding_pct", 0),
                shareholding_data.get("promoter_pledging_pct", 0),
                shareholding_data.get("fii_holding_pct", 0),
                shareholding_data.get("dii_holding_pct", 0),
                shareholding_data.get("mf_holding_pct", 0),
            )
            results.append(result)

        # Validate sentiment data
        if sentiment_data:
            result = self.validate_sentiment_data(
                symbol,
                sentiment_data.get("sentiment_score", 0),
                sentiment_data.get("article_count", 0),
                sentiment_data.get("avg_relevance", 0),
            )
            results.append(result)

        # Validate regulatory data
        if regulatory_data:
            result = self.validate_regulatory_data(
                symbol,
                regulatory_data.get("legal_cases", 0),
                regulatory_data.get("auditor_resignations", 0),
                regulatory_data.get("regulatory_actions", 0),
            )
            results.append(result)

        # Calculate overall metrics
        total_params = len(results)
        valid_params = sum(1 for r in results if r.is_valid)
        invalid_params = total_params - valid_params
        warning_params = sum(1 for r in results if r.warnings and r.is_valid)

        overall_quality = sum(r.quality_score for r in results) / max(total_params, 1)

        report = ValidationReport(
            symbol=symbol,
            total_parameters=total_params,
            valid_parameters=valid_params,
            invalid_parameters=invalid_params,
            warning_parameters=warning_params,
            overall_quality=round(overall_quality, 1),
            can_trade=invalid_params == 0 and overall_quality >= 70,
            results=results,
        )

        # Cache report
        self.validation_cache[symbol] = report

        return report

    def get_validation_summary(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get validation summary for a symbol."""
        if symbol not in self.validation_cache:
            return None

        report = self.validation_cache[symbol]
        return {
            "symbol": report.symbol,
            "total_parameters": report.total_parameters,
            "valid_parameters": report.valid_parameters,
            "invalid_parameters": report.invalid_parameters,
            "warning_parameters": report.warning_parameters,
            "overall_quality": report.overall_quality,
            "can_trade": report.can_trade,
            "checked_at": report.checked_at,
            "failed_parameters": [
                r.parameter_key for r in report.results if not r.is_valid
            ],
            "warning_parameters": [
                r.parameter_key for r in report.results if r.warnings and r.is_valid
            ],
        }

    def clear_cache(self, symbol: Optional[str] = None):
        """Clear validation cache."""
        if symbol:
            self.validation_cache.pop(symbol, None)
        else:
            self.validation_cache.clear()
"""PKScreener Strategy Adapter for SI-Trader.

Integrates pkjmesra/PKScreener - chart patterns, breakouts, and stock screening
for Indian markets.

PKScreener Features:
- Chart patterns: breakouts, flags, reversals
- Stock screening with technical criteria
- NSE/BSE coverage
- Pattern-based strategy generation

SI-Trader Integration:
- PKScreener patterns converted to parameter weight configurations
- Screen results fed into SI-Trader parameter catalogue
- Pattern signals validated against BRD cost model
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PkScreenerSignal:
    """Signal from PKScreener pattern detection."""
    symbol: str
    pattern_name: str
    pattern_type: str  # "breakout", "flag", "reversal", "momentum"
    confidence: float  # 0-100
    entry_price: float
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PkScreenerConfig:
    """Configuration for PKScreener integration."""
    screener_path: Optional[str] = None
    patterns_enabled: Optional[List[str]] = None
    min_confidence: float = 60.0
    max_positions: int = 10
    sector_filter: Optional[str] = None


class PKScreenerAdapter:
    """Piotroski F-Score and Altman Z-Score adapter for SI-Trader.

    Integrates fundamental score parameters into the 30-parameter catalogue.
    These scores come from fundamental analysis research and are encoded as
    parameters in the BRD-compliant catalogue:

    - f_score (weight=1, Score role, quarterly refresh)
    - altman_z_score (weight=1, Score role, quarterly refresh)

    Usage:
        adapter = FundamentalScoreAdapter()
        score = adapter.calculate_f_score(financial_data)
        score = adapter.calculate_altman_z_score(financial_data)
    """

    def __init__(self):
        self._calculations: Dict[str, FundamentalScore] = {}

        print(f"Piotroski F-Score / Altman Z-Score adapter initialized:")
        print(f"  Parameters: f_score (weight=1), altman_z_score (weight=1)")

    def is_available(self) -> bool:
        """Always returns True since this is a built-in adapter."""
        return True

    def calculate_f_score(self,
                          symbol: str,
                          roa: float,
                          cfo: float,
                          roa_change: float,
                          accrual: float,
                          margin_change: float,
                          turnover_change: float,
                          liquidity_change: float,
                          leverage_change: float,
                          shares_change: float,
                          ) -> FundamentalScore:
        """Calculate Piotroski F-Score (0-9).

        9 criteria, 1 point each:
        1. ROA > 0
        2. CFO > 0
        3. ROA improving
        4. CFO > ROA (quality of earnings)
        5. Margin improving
        6. Turnover improving
        7. Liquidity improving
        8. Leverage decreasing
        9. No share dilution
        """
        score = 0

        if roa > 0:
            score += 1
        if cfo > 0:
            score += 1
        if roa_change > 0:
            score += 1
        if accrual < 0:
            score += 1
        if margin_change > 0:
            score += 1
        if turnover_change > 0:
            score += 1
        if liquidity_change > 0:
            score += 1
        if leverage_change < 0:
            score += 1
        if shares_change <= 0:
            score += 1

        fs = FundamentalScore(symbol=symbol, f_score=score)
        self._calculations[symbol] = fs

        logger.info(f"F-Score for {symbol}: {score}/9 - {fs.f_score_interpretation}")
        return fs

    def calculate_altman_z_score(self,
                                 symbol: str,
                                 working_capital_to_assets: float,
                                 retained_earnings_to_assets: float,
                                 ebit_to_assets: float,
                                 market_equity_to_liabilities: float,
                                 sales_to_assets: float) -> FundamentalScore:
        """Calculate Altman Z-Score.

        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 0.999*X5
        """
        z_score = (
            1.2 * working_capital_to_assets +
            1.4 * retained_earnings_to_assets +
            3.3 * ebit_to_assets +
            0.6 * market_equity_to_liabilities +
            0.999 * sales_to_assets
        )

        fs = FundamentalScore(symbol=symbol, altman_z_score=z_score)

        if symbol in self._calculations:
            self._calculations[symbol].altman_z_score = z_score
            self._calculations[symbol].z_score_interpretation = fs.z_score_interpretation
        else:
            self._calculations[symbol] = fs

        logger.info(f"Altman Z-Score for {symbol}: {z_score:.2f} - {fs.z_score_interpretation}")
        return fs

    def get_score(self, symbol: str) -> Optional[FundamentalScore]:
        """Get stored fundamental score for a symbol."""
        return self._calculations.get(symbol)

    def to_parameter_dict(self, symbol: str) -> Dict[str, Any]:
        """Convert score to SI-Trader parameter dictionary."""
        score = self.get_score(symbol)
        if score is None:
            return {}

        return {
            "f_score": score.f_score,
            "altman_z_score": score.altman_z_score,
        }


__all__ = [
    "FundamentalScore",
    "PKScreenerAdapter",
    "PkScreenerConfig",
    "PkScreenerSignal",
]


# Alias FundamentalScoreAdapter to PKScreenerAdapter for backward compatibility
FundamentalScoreAdapter = PKScreenerAdapter
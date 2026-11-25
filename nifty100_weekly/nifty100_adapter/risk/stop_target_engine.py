"""Stop Loss & Target Engine for SI-Trader.

Sets stop and target before entry, so you know when to get out.
BRD Section 14: Risk management requirements.

Stop placement methods:
1. Opening-range midpoint (default) - midpoint of first 15-min OR
2. Opening range low - low of first 15 minutes
3. Fixed price - trader-specified stop
4. Percent - X% below entry
5. ATR multiple - multiple of Average True Range below entry

Target placement:
1. 2R (default) - target at 2x risk distance above entry
2. 1R - target at 1x risk distance
3. Custom price - trader-specified target

Validation rules:
- Stop must be below entry (long side only)
- Target must be above entry
- Stop too tight to survive spread → refused
- Stop at or above entry → refused
- Target at or below entry → refused

Stops are rounded down to the cent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, time
import math
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Stop & Target Configuration
# =============================================================================

@dataclass
class StopTargetConfig:
    """Configuration for stop loss and target calculation."""
    # Stop method
    stop_method: str = "opening_range_midpoint"  # opening_range_midpoint, opening_range_low, fixed_price, percent, atr_multiple
    
    # Stop values (depends on method)
    stop_price: Optional[float] = None  # For fixed_price method
    stop_percent: Optional[float] = None  # For percent method (e.g., 2.0 = 2% below entry)
    atr_multiple: Optional[float] = None  # For atr_multiple method (e.g., 2.0 = 2x ATR)
    atr_value: Optional[float] = None  # ATR value for atr_multiple method
    
    # Opening range settings
    opening_range_minutes: int = 15  # First 15 minutes by default
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    
    # Target method
    target_method: str = "2R"  # 2R, 1R, custom_price
    target_price: Optional[float] = None  # For custom_price method
    
    # Rounding
    round_stop_to_cent: bool = True  # Round stop down to nearest 0.01
    
    # Minimum stop distance (to survive spread)
    min_stop_distance_pct: float = 0.05  # Minimum 0.05% below entry
    
    # Maximum stop distance (to avoid too-wide stops)
    max_stop_distance_pct: float = 10.0  # Maximum 10% below entry


@dataclass
class StopTargetResult:
    """Result of stop loss and target calculation."""
    entry_price: float
    stop_loss: float
    target: Optional[float] = None
    
    # Risk metrics
    risk_per_share: float = 0.0
    total_risk: float = 0.0  # risk_per_share * shares (set later)
    reward_per_share: float = 0.0
    reward_risk_ratio: float = 0.0
    
    # Method used
    stop_method_used: str = ""
    target_method_used: str = ""
    
    # Validation
    is_valid: bool = False
    rejection_reason: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    
    # Warnings (non-blocking)
    warnings: List[str] = field(default_factory=list)
    
    # Metadata
    calculated_at: Optional[str] = None
    shares: int = 0  # Set later by budget manager


# =============================================================================
# Stop & Target Engine
# =============================================================================

class StopTargetEngine:
    """Calculates stop loss and target prices before entry.
    
    Ensures every trade has a defined exit before capital is at risk.
    BRD Section 14: Stop is required for day trades.
    """
    
    def __init__(self, config: Optional[StopTargetConfig] = None):
        self.config = config or StopTargetConfig()
        
        print(f"StopTargetEngine initialized:")
        print(f"  Stop method: {self.config.stop_method}")
        print(f"  Target method: {self.config.target_method}")
        print(f"  Min stop distance: {self.config.min_stop_distance_pct}%")
        print(f"  Max stop distance: {self.config.max_stop_distance_pct}%")
        print(f"  Round stop to cent: {self.config.round_stop_to_cent}")
    
    # =========================================================================
    # Stop Loss Calculation
    # =========================================================================
    
    def calculate_stop(self,
                       entry_price: float,
                       config: Optional[StopTargetConfig] = None) -> float:
        """Calculate stop loss price.
        
        Args:
            entry_price: Entry price per share
            config: Optional config override
            
        Returns:
            Stop loss price (rounded down to cent if configured)
        """
        cfg = config or self.config
        stop_price = None
        
        if cfg.stop_method == "opening_range_midpoint":
            if cfg.opening_range_high is None or cfg.opening_range_low is None:
                raise ValueError("Opening range high and low required for opening_range_midpoint method")
            stop_price = (cfg.opening_range_high + cfg.opening_range_low) / 2
        
        elif cfg.stop_method == "opening_range_low":
            if cfg.opening_range_low is None:
                raise ValueError("Opening range low required for opening_range_low method")
            stop_price = cfg.opening_range_low
        
        elif cfg.stop_method == "fixed_price":
            if cfg.stop_price is None:
                raise ValueError("Stop price required for fixed_price method")
            stop_price = cfg.stop_price
        
        elif cfg.stop_method == "percent":
            if cfg.stop_percent is None:
                raise ValueError("Stop percent required for percent method")
            stop_price = entry_price * (1 - cfg.stop_percent / 100)
        
        elif cfg.stop_method == "atr_multiple":
            if cfg.atr_multiple is None or cfg.atr_value is None:
                raise ValueError("ATR multiple and ATR value required for atr_multiple method")
            stop_price = entry_price - (cfg.atr_multiple * cfg.atr_value)
        
        else:
            raise ValueError(f"Unknown stop method: {cfg.stop_method}")
        
        # Round down to cent
        if cfg.round_stop_to_cent and stop_price is not None:
            stop_price = math.floor(stop_price * 100) / 100
        
        return stop_price
    
    # =========================================================================
    # Target Calculation
    # =========================================================================
    
    def calculate_target(self,
                        entry_price: float,
                        stop_loss: float,
                        config: Optional[StopTargetConfig] = None) -> float:
        """Calculate target price.
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            config: Optional config override
            
        Returns:
            Target price
        """
        cfg = config or self.config
        risk_per_share = entry_price - stop_loss
        
        if cfg.target_method == "2R":
            target = entry_price + (2.0 * risk_per_share)
        
        elif cfg.target_method == "1R":
            target = entry_price + risk_per_share
        
        elif cfg.target_method == "custom_price":
            if cfg.target_price is None:
                raise ValueError("Target price required for custom_price method")
            target = cfg.target_price
        
        else:
            raise ValueError(f"Unknown target method: {cfg.target_method}")
        
        return target
    
    # =========================================================================
    # Full Stop & Target Calculation with Validation
    # =========================================================================
    
    def calculate(self,
                  entry_price: float,
                  config: Optional[StopTargetConfig] = None,
                  shares: int = 0) -> StopTargetResult:
        """Complete stop loss and target calculation with validation.
        
        Validates:
        - Stop must be below entry
        - Target must be above entry
        - Stop not too tight (survive spread)
        - Stop not too wide (max distance)
        - Reward:risk meets minimum
        
        Args:
            entry_price: Entry price per share
            config: Optional config override
            shares: Number of shares (for total risk calc)
            
        Returns:
            StopTargetResult with stop, target, risk metrics, and validation
        """
        cfg = config or self.config
        result = StopTargetResult(
            entry_price=entry_price,
            stop_loss=0.0,  # Will be set below
            stop_method_used=cfg.stop_method,
            target_method_used=cfg.target_method,
            shares=shares,
            calculated_at=datetime.now().isoformat(),
        )
        
        # Calculate stop loss
        try:
            stop_price = self.calculate_stop(entry_price, cfg)
        except ValueError as e:
            result.rejection_reason = str(e)
            result.validation_errors.append(str(e))
            return result
        
        result.stop_loss = stop_price
        result.risk_per_share = entry_price - stop_price
        
        # Validate stop
        if result.risk_per_share <= 0:
            result.rejection_reason = "Stop at or above entry - refused"
            result.validation_errors.append("Stop loss must be below entry price")
            result.is_valid = False
            return result
        
        # Check stop not too tight (survive spread)
        min_distance = entry_price * (cfg.min_stop_distance_pct / 100)
        if result.risk_per_share < min_distance:
            result.rejection_reason = (
                f"Stop too tight: {result.risk_per_share:.2f} below entry, "
                f"minimum {min_distance:.2f} required to survive spread"
            )
            result.validation_errors.append(result.rejection_reason)
            result.is_valid = False
            return result
        
        # Check stop not too wide
        max_distance = entry_price * (cfg.max_stop_distance_pct / 100)
        if result.risk_per_share > max_distance:
            result.warnings.append(
                f"Stop wide: {result.risk_per_share:.2f} below entry "
                f"({(result.risk_per_share/entry_price)*100:.2f}%), "
                f"max recommended {max_distance:.2f} ({cfg.max_stop_distance_pct}%)"
            )
        
        # Calculate target
        try:
            target_price = self.calculate_target(entry_price, stop_price, cfg)
        except ValueError as e:
            result.rejection_reason = str(e)
            result.validation_errors.append(str(e))
            result.is_valid = False
            return result
        
        result.target = target_price
        result.reward_per_share = target_price - entry_price
        
        # Validate target
        if result.reward_per_share <= 0:
            result.rejection_reason = "Target at or below entry - refused"
            result.validation_errors.append("Target must be above entry price")
            result.is_valid = False
            return result
        
        # Calculate reward:risk
        result.reward_risk_ratio = result.reward_per_share / result.risk_per_share
        
        # Check minimum reward:risk
        if result.reward_risk_ratio < cfg.min_reward_risk_ratio if hasattr(cfg, 'min_reward_risk_ratio') else result.reward_risk_ratio < 1.0:
            min_rr = getattr(cfg, 'min_reward_risk_ratio', 1.0)
            result.warnings.append(
                f"Reward:risk {result.reward_risk_ratio:.2f}:1 below {min_rr}:1"
            )
        
        # Calculate total risk if shares provided
        if shares > 0:
            result.total_risk = result.risk_per_share * shares
        
        # All validations passed
        result.is_valid = True
        
        logger.info(
            f"Stop/T calculated: Entry={entry_price:.2f}, Stop={stop_price:.2f}, "
            f"Target={target_price:.2f}, Risk={result.risk_per_share:.2f}/share, "
            f"R:R={result.reward_risk_ratio:.2f}:1"
        )
        
        return result
    
    # =========================================================================
    # Opening Range Calculation
    # =========================================================================
    
    def calculate_opening_range(self,
                               high_prices: List[float],
                               low_prices: List[float],
                               minutes: int = 15) -> tuple[float, float]:
        """Calculate opening range high and low from intraday prices.
        
        Args:
            high_prices: List of high prices in the opening range period
            low_prices: List of low prices in the opening range period
            minutes: Opening range window in minutes (default 15)
            
        Returns:
            (range_high, range_low)
        """
        if not high_prices or not low_prices:
            raise ValueError("High and low prices required for opening range calculation")
        
        range_high = max(high_prices)
        range_low = min(low_prices)
        
        return range_high, range_low
    
    # =========================================================================
    # Validation Helpers
    # =========================================================================
    
    def validate_existing_stop(self,
                              entry_price: float,
                              stop_loss: float,
                              target: Optional[float] = None) -> StopTargetResult:
        """Validate an existing stop loss and target without recalculating.
        
        Useful for reviewing existing orders or backtesting.
        """
        result = StopTargetResult(
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            stop_method_used="validation",
            target_method_used="validation",
            shares=0,
            calculated_at=datetime.now().isoformat(),
        )
        
        result.risk_per_share = entry_price - stop_loss
        
        # Validate stop
        if result.risk_per_share <= 0:
            result.rejection_reason = "Stop at or above entry"
            result.validation_errors.append(result.rejection_reason)
            result.is_valid = False
            return result
        
        # Check stop distance
        min_distance = entry_price * (self.config.min_stop_distance_pct / 100)
        if result.risk_per_share < min_distance:
            result.rejection_reason = f"Stop too tight (< {self.config.min_stop_distance_pct}%)"
            result.validation_errors.append(result.rejection_reason)
            result.is_valid = False
            return result
        
        # Validate target
        if target is not None:
            result.target = target
            result.reward_per_share = target - entry_price
            
            if result.reward_per_share <= 0:
                result.rejection_reason = "Target at or below entry"
                result.validation_errors.append(result.rejection_reason)
                result.is_valid = False
                return result
            
            result.reward_risk_ratio = result.reward_per_share / result.risk_per_share
        
        result.is_valid = True
        return result
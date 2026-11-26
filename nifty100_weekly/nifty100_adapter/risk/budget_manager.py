"""Risk & Budget Manager for SI-Trader.

Sizes every position to budget and max loss per trade limits.
Implements BRD Section 14 risk management requirements:

Four position sizing limits (whichever is most restrictive wins):
1. Max loss per trade limit - loss at stop must fit max loss per trade
2. Position cap limit - max number of concurrent positions
3. Max order size limit - max value per single order
4. Cash buffer limit - keep N% in cash, never deploy 100%

BRD Compliance:
- Section 14: Risk gate (position limits, kill switch, max weekly loss)
- Section 14: 3+ month paper trading before REAL_MONEY
- Cost model: STT 0.1% both sides, STCG 20%, brokerage 0.05%, roundtrip 0.38%
- Weekly delivery: CNC product type, top N selection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Budget Rules Configuration
# =============================================================================

@dataclass
class BudgetRules:
    """Trader's budget and risk limits.
    
    All values configurable per trader. Defaults match BRD pilot
    capital of ₹25,000.
    """
    pilot_capital: float = 25000.0
    
    # Max loss per trade (default: ₹500 = 2% of capital)
    max_loss_per_trade: float = 500.0
    
    # Max daily loss limit (default: ₹1,000 = 4% of capital)
    max_daily_loss: float = 1000.0
    
    # Max weekly loss limit (default: ₹5,000 = 20% of capital)
    max_weekly_loss: float = 5000.0
    
    # Position cap: max concurrent positions (default: 10)
    max_positions: int = 10
    
    # Max order size: max value per single order (default: ₹2,500 = 10%)
    max_order_size: float = 2500.0
    
    # Cash buffer: keep N% in cash (default: 10%)
    cash_buffer_pct: float = 0.10
    
    # Max position size as % of capital (default: 10%)
    max_position_pct: float = 0.10
    
    # Max single trade as % of capital (default: 5%)
    max_single_trade_pct: float = 0.05
    
    # Minimum position value (default: ₹500)
    min_position_value: float = 500.0
    
    # Reward:risk minimum (default: 2:1)
    min_reward_risk_ratio: float = 2.0
    
    # Day trade limits
    max_trades_per_day: int = 5
    entry_window_start: str = "09:15"
    entry_window_end: str = "15:30"
    
    # Blocked tickers
    blocked_tickers: List[str] = field(default_factory=list)
    
    # Margin/short/options restrictions
    allow_short_sales: bool = False
    allow_options: bool = False
    allow_crypto: bool = False
    allow_margin: bool = False


@dataclass
class PositionSizingResult:
    """Result of position sizing calculation."""
    symbol: str
    entry_price: float
    stop_loss: float
    target: Optional[float] = None
    
    # Sizing decision
    recommended_shares: int = 0
    position_value: float = 0.0
    position_pct_of_capital: float = 0.0
    
    # Risk metrics
    risk_per_share: float = 0.0
    total_risk_at_stop: float = 0.0
    max_loss_allowed: float = 0.0
    
    # Which limit decided
    deciding_limit: str = ""
    limit_reason: str = ""
    
    # Validation
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    # Costs
    estimated_brokerage: float = 0.0
    estimated_stt: float = 0.0
    estimated_stcg_tax: float = 0.0
    estimated_net_pnl_at_target: float = 0.0
    estimated_net_pnl_at_stop: float = 0.0
    
    # Reward:risk
    reward_risk_ratio: float = 0.0
    
    # Cash impact
    cash_after_position: float = 0.0
    cash_buffer_remaining: float = 0.0


# =============================================================================
# Budget Manager
# =============================================================================

class BudgetManager:
    """Sizes every position to budget and max loss per trade limits.
    
    Implements the four-limit position sizing framework:
    
    1. Max Loss Per Trade Limit: Loss at stop must fit within max_loss_per_trade
    2. Position Cap Limit: No more than max_positions concurrent positions
    3. Max Order Size Limit: Order value ≤ max_order_size
    4. Cash Buffer Limit: Keep cash_buffer_pct% in cash after position
    
    The deciding limit (most restrictive) determines position size.
    Nothing is placed - this is a sizing/refusal engine only.
    """
    
    def __init__(self, rules: Optional[BudgetRules] = None):
        self.rules = rules or BudgetRules()
        self.daily_trades_count = 0
        self.daily_loss = 0.0
        self.weekly_loss = 0.0
        self.current_positions: Dict[str, Any] = {}
        self.trades_today: List[Dict[str, Any]] = []
        
        # Cost model reference
        from ..config.indian_cost_model import IndianCostModel, get_cost_model
        self.cost_model = get_cost_model()
        
        print(f"BudgetManager initialized:")
        print(f"  Pilot capital: ₹{self.rules.pilot_capital:,.2f}")
        print(f"  Max loss per trade: ₹{self.rules.max_loss_per_trade:,.2f}")
        print(f"  Max daily loss: ₹{self.rules.max_daily_loss:,.2f}")
        print(f"  Max weekly loss: ₹{self.rules.max_weekly_loss:,.2f}")
        print(f"  Max positions: {self.rules.max_positions}")
        print(f"  Max order size: ₹{self.rules.max_order_size:,.2f}")
        print(f"  Cash buffer: {self.rules.cash_buffer_pct*100:.0f}%")
        print(f"  Min reward:risk: {self.rules.min_reward_risk_ratio}:1")
    
    # =========================================================================
    # Core Sizing Logic
    # =========================================================================
    
    def size_position(self,
                      symbol: str,
                      entry_price: float,
                      stop_loss: float,
                      target: Optional[float] = None,
                      current_cash: Optional[float] = None,
                      current_positions_count: Optional[int] = None) -> PositionSizingResult:
        """Size a position against all four limits.
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            target: Target price per share (optional, calculated if not given)
            current_cash: Current available cash (defaults to pilot_capital)
            current_positions_count: Current number of open positions
            
        Returns:
            PositionSizingResult with recommended shares and deciding limit
        """
        errors = []
        
        # Validate inputs
        if entry_price <= 0:
            errors.append("Entry price must be positive")
        if stop_loss <= 0:
            errors.append("Stop loss must be positive")
        if stop_loss >= entry_price:
            errors.append("Stop loss must be below entry price (long side only)")
        
        # Calculate target if not provided (2R default)
        if target is None:
            risk_per_share = entry_price - stop_loss
            target = entry_price + (2.0 * risk_per_share)  # 2:1 reward:risk
        
        if target <= entry_price:
            errors.append("Target must be above entry price")
        
        if errors:
            return PositionSizingResult(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target=target,
                is_valid=False,
                validation_errors=errors,
            )
        
        risk_per_share = entry_price - stop_loss
        reward_per_share = target - entry_price
        reward_risk_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0
        
        # Reward:risk check
        if reward_risk_ratio < self.rules.min_reward_risk_ratio:
            errors.append(
                f"Reward:risk {reward_risk_ratio:.2f}:1 below minimum "
                f"{self.rules.min_reward_risk_ratio}:1"
            )
        
        current_cash = current_cash or self.rules.pilot_capital
        current_positions_count = current_positions_count or len(self.current_positions)
        
        # --- Limit 1: Max Loss Per Trade ---
        # Loss at stop = risk_per_share * shares
        # Must be ≤ max_loss_per_trade
        max_shares_by_loss = int(self.rules.max_loss_per_trade / risk_per_share) if risk_per_share > 0 else 0
        loss_limit_deciding = True
        
        # --- Limit 2: Position Cap ---
        max_shares_by_cap = int((self.rules.pilot_capital * self.rules.max_position_pct) / entry_price)
        cap_limit_deciding = max_shares_by_cap < max_shares_by_loss
        
        # --- Limit 3: Max Order Size ---
        max_shares_by_order = int(self.rules.max_order_size / entry_price)
        order_limit_deciding = max_shares_by_order < max_shares_by_loss and max_shares_by_order < max_shares_by_cap
        
        # --- Limit 4: Cash Buffer ---
        cash_available_after_buffer = current_cash * (1 - self.rules.cash_buffer_pct)
        max_shares_by_cash = int(cash_available_after_buffer / entry_price)
        cash_limit_deciding = max_shares_by_cash < max_shares_by_loss and \
                             max_shares_by_cash < max_shares_by_cap and \
                             max_shares_by_cash < max_shares_by_order
        
        # --- Limit 5: Daily Loss ---
        # If daily loss already near limit, reduce or block
        daily_loss_remaining = self.rules.max_daily_loss - self.daily_loss
        if daily_loss_remaining <= 0:
            errors.append(f"Daily loss limit reached: ₹{self.daily_loss:.2f} ≥ ₹{self.rules.max_daily_loss:.2f}")
            max_shares_by_daily = 0
        else:
            max_shares_by_daily = int(daily_loss_remaining / risk_per_share) if risk_per_share > 0 else 0
        daily_limit_deciding = max_shares_by_daily < max_shares_by_loss and \
                              max_shares_by_daily < max_shares_by_cap and \
                              max_shares_by_daily < max_shares_by_order and \
                              max_shares_by_daily < max_shares_by_cash
        
        # Determine the deciding limit (most restrictive)
        share_limits = {
            "max_loss_per_trade": max_shares_by_loss,
            "position_cap": max_shares_by_cap,
            "max_order_size": max_shares_by_order,
            "cash_buffer": max_shares_by_cash,
            "daily_loss": max_shares_by_daily,
        }
        
        # Check if ANY limit gives 0 shares - trade is blocked
        zero_limit = None
        for name, val in share_limits.items():
            if val <= 0:
                zero_limit = name
                break
        
        if zero_limit:
            recommended_shares = 0
            deciding_limit = zero_limit
            limit_reasons = {
                "max_loss_per_trade": f"Max loss per trade: ₹{self.rules.max_loss_per_trade:,.2f} at stop",
                "position_cap": f"Position cap: {self.rules.max_positions} max positions, {self.rules.max_position_pct*100:.0f}% of capital each",
                "max_order_size": f"Max order size: ₹{self.rules.max_order_size:,.2f} per order",
                "cash_buffer": f"Cash buffer: keep {self.rules.cash_buffer_pct*100:.0f}% in cash",
                "daily_loss": f"Daily loss remaining: ₹{daily_loss_remaining:,.2f}",
            }
            limit_reason = limit_reasons.get(zero_limit, zero_limit)
        else:
            # Find minimum non-zero limit
            deciding_limit = min(share_limits, key=share_limits.get)
            recommended_shares = share_limits[deciding_limit]
            
            limit_reasons = {
                "max_loss_per_trade": f"Max loss per trade: ₹{self.rules.max_loss_per_trade:,.2f} at stop",
                "position_cap": f"Position cap: {self.rules.max_positions} max positions, {self.rules.max_position_pct*100:.0f}% of capital each",
                "max_order_size": f"Max order size: ₹{self.rules.max_order_size:,.2f} per order",
                "cash_buffer": f"Cash buffer: keep {self.rules.cash_buffer_pct*100:.0f}% in cash",
                "daily_loss": f"Daily loss remaining: ₹{daily_loss_remaining:,.2f}",
            }
            limit_reason = limit_reasons.get(deciding_limit, deciding_limit)
        
        # Apply minimum position value check
        position_value = recommended_shares * entry_price
        if position_value < self.rules.min_position_value and recommended_shares > 0:
            recommended_shares = 0
            deciding_limit = "min_position_value"
            limit_reason = f"Position value ₹{position_value:.2f} below minimum ₹{self.rules.min_position_value:.2f}"
        
        # Apply blocked tickers check
        if symbol in self.rules.blocked_tickers:
            recommended_shares = 0
            deciding_limit = "blocked_ticker"
            limit_reason = f"{symbol} is in blocked tickers list"
        
        # Apply position cap check
        if current_positions_count >= self.rules.max_positions and recommended_shares > 0:
            recommended_shares = 0
            deciding_limit = "position_cap"
            limit_reason = f"Already at max positions ({self.rules.max_positions})"
        
        # Calculate final metrics
        total_risk = recommended_shares * risk_per_share if recommended_shares > 0 else 0
        position_pct = (position_value / self.rules.pilot_capital * 100) if position_value > 0 else 0
        
        # Cost calculations (roundtrip: buy + sell)
        estimated_brokerage = self.cost_model.brokerage_rate * (entry_price + (target or entry_price)) * recommended_shares * 1.18  # +18% GST
        estimated_stt = self.cost_model.stt_rate_equity * entry_price * recommended_shares + \
                       self.cost_model.stt_rate_equity * (target or entry_price) * recommended_shares
        
        # P&L at target and stop
        net_at_target = (target - entry_price) * recommended_shares - estimated_brokerage - estimated_stt
        # STCG tax on profit only
        if net_at_target > 0:
            net_at_target = net_at_target * (1 - self.cost_model.stcg_tax_rate)
        
        net_at_stop = -total_risk - estimated_brokerage  # Loss at stop + costs
        
        cash_after = current_cash - position_value
        cash_buffer_after = cash_after / self.rules.pilot_capital
        
        is_valid = recommended_shares > 0 and len(errors) == 0
        
        return PositionSizingResult(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            recommended_shares=recommended_shares,
            position_value=position_value,
            position_pct_of_capital=position_pct,
            risk_per_share=risk_per_share,
            total_risk_at_stop=total_risk,
            max_loss_allowed=self.rules.max_loss_per_trade,
            deciding_limit=deciding_limit,
            limit_reason=limit_reason,
            is_valid=is_valid,
            validation_errors=errors,
            estimated_brokerage=estimated_brokerage,
            estimated_stt=estimated_stt,
            estimated_stcg_tax=0.0,  # Calculated on profit only
            estimated_net_pnl_at_target=net_at_target,
            estimated_net_pnl_at_stop=net_at_stop,
            reward_risk_ratio=reward_risk_ratio,
            cash_after_position=cash_after,
            cash_buffer_remaining=cash_buffer_after,
        )
    
    # =========================================================================
    # Daily/Weekly Risk Tracking
    # =========================================================================
    
    def can_trade_today(self) -> tuple[bool, str]:
        """Check if trading is allowed today based on daily limits."""
        if self.daily_trades_count >= self.rules.max_trades_per_day:
            return False, f"Daily trade limit reached: {self.daily_trades_count}/{self.rules.max_trades_per_day}"
        
        if self.daily_loss >= self.rules.max_daily_loss:
            return False, f"Daily loss limit reached: ₹{self.daily_loss:.2f}/₹{self.rules.max_daily_loss:.2f}"
        
        if self.weekly_loss >= self.rules.max_weekly_loss:
            return False, f"Weekly loss limit reached: ₹{self.weekly_loss:.2f}/₹{self.rules.max_weekly_loss:.2f}"
        
        return True, "OK"
    
    def record_trade(self, symbol: str, pnl: float, shares: int, price: float) -> None:
        """Record a completed trade for daily/weekly tracking."""
        self.daily_trades_count += 1
        self.daily_loss += abs(min(pnl, 0))  # Only count losses
        self.weekly_loss += abs(min(pnl, 0))
        
        self.trades_today.append({
            "symbol": symbol,
            "pnl": pnl,
            "shares": shares,
            "price": price,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Update current positions
        if pnl != 0:  # Trade closed
            if symbol in self.current_positions:
                del self.current_positions[symbol]
    
    def open_position(self, symbol: str, shares: int, price: float) -> None:
        """Record an opened position."""
        self.current_positions[symbol] = {
            "shares": shares,
            "entry_price": price,
            "opened_at": datetime.now().isoformat(),
        }
    
    def close_position(self, symbol: str, pnl: float) -> None:
        """Close a position and update risk tracking."""
        if symbol in self.current_positions:
            del self.current_positions[symbol]
        self.record_trade(symbol, pnl, 0, 0)
    
    def reset_daily(self) -> None:
        """Reset daily counters (call at start of each trading day)."""
        self.daily_trades_count = 0
        self.daily_loss = 0.0
        self.trades_today = []
    
    def reset_weekly(self) -> None:
        """Reset weekly counters (call at start of each trading week)."""
        self.weekly_loss = 0.0
    
    # =========================================================================
    # Reports
    # =========================================================================
    
    def get_risk_report(self) -> Dict[str, Any]:
        """Generate current risk status report."""
        can_trade, reason = self.can_trade_today()
        
        return {
            "pilot_capital": self.rules.pilot_capital,
            "max_loss_per_trade": self.rules.max_loss_per_trade,
            "max_daily_loss": self.rules.max_daily_loss,
            "max_weekly_loss": self.rules.max_weekly_loss,
            "daily_loss_used": self.daily_loss,
            "daily_loss_remaining": self.rules.max_daily_loss - self.daily_loss,
            "weekly_loss_used": self.weekly_loss,
            "weekly_loss_remaining": self.rules.max_weekly_loss - self.weekly_loss,
            "daily_trades_count": self.daily_trades_count,
            "max_trades_per_day": self.rules.max_trades_per_day,
            "current_positions": len(self.current_positions),
            "max_positions": self.rules.max_positions,
            "cash_buffer_pct": self.rules.cash_buffer_pct,
            "can_trade_today": can_trade,
            "trade_blocked_reason": reason if not can_trade else "",
            "kill_switch_active": False,  # Integrated with KillSwitch class
        }
    
    def validate_order(self,
                      symbol: str,
                      entry_price: float,
                      stop_loss: float,
                      target: Optional[float] = None,
                      current_cash: Optional[float] = None) -> tuple[bool, PositionSizingResult]:
        """Validate an order against all risk limits.
        
        Returns (is_valid, sizing_result).
        If invalid, sizing_result explains which limit blocked it.
        """
        can_trade, trade_reason = self.can_trade_today()
        if not can_trade:
            result = PositionSizingResult(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target=target,
                recommended_shares=0,
                is_valid=False,
                validation_errors=[trade_reason],
                deciding_limit="daily_limit",
                limit_reason=trade_reason,
            )
            return False, result
        
        sizing = self.size_position(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            current_cash=current_cash,
            current_positions_count=len(self.current_positions),
        )
        
        return sizing.is_valid, sizing
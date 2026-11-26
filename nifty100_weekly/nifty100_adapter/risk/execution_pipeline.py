"""Order Execution Pipeline for SI-Trader.

Routes orders through broker adapters with full risk checking:
1. Budget/position sizing validation
2. Stop loss & target calculation
3. Kill switch check
4. Compliance gate verification
5. Broker adapter execution
6. Trade recording & audit trail

BRD Section 14 compliance:
- Paper trading default mode
- Manual approval for first live order
- All 5 compliance gates must pass
- Kill switch blocks all orders when active
- Algo-ID assigned to every order
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import uuid

# SI-Trader imports
try:
    from ..broker._init_ import (
        BrokerConfig,
        OrderRequest,
        OrderResponse,
        OrderSide,
        OrderType,
        ProductType,
        OrderStatus,
        BrokerPlatform,
        BrokerAdapter,
        Position,
    )
    BROKER_ADAPTERS_AVAILABLE = True
except ImportError:
    BROKER_ADAPTERS_AVAILABLE = False
    # Define minimal stubs
    from dataclasses import dataclass
    from enum import Enum
    OrderRequest = dict
    OrderResponse = dict
    
    class OrderSide(Enum):
        BUY = "BUY"
        SELL = "SELL"
    
    class OrderType(Enum):
        MARKET = "MARKET"
        LIMIT = "LIMIT"
    
    class ProductType(Enum):
        CNC = "CNC"
    
    class OrderStatus(Enum):
        OPEN = "OPEN"
        FILLED = "FILLED"
    
    class BrokerPlatform(Enum):
        ZERODHA_KITE = "zerodha_kite"
    
    class BrokerAdapter:
        def __init__(self, config=None):
            self.config = config
            self._connected = False
        def is_connected(self):
            return self._connected
    
    class OrderRequest:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    
    class OrderResponse:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    
    class BrokerConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    
    class Position:
        pass

# Sibling risk modules (always available; they have no optional deps)
from .budget_manager import (
    BudgetManager, BudgetRules, PositionSizingResult,
)
from .stop_target_engine import (
    StopTargetEngine, StopTargetConfig, StopTargetResult,
)
from .kill_switch import ComplianceGateEnforcer, KillSwitchManager

logger = logging.getLogger(__name__)


# =============================================================================
# Execution Result
# =============================================================================

@dataclass
class ExecutionResult:
    """Complete result of an order execution attempt."""
    symbol: str
    action: OrderSide
    entry_price: float
    stop_loss: float
    target: Optional[float] = None
    
    # Sizing
    shares: int = 0
    position_value: float = 0.0
    deciding_limit: str = ""
    
    # Risk
    risk_per_share: float = 0.0
    total_risk: float = 0.0
    reward_risk_ratio: float = 0.0
    
    # Order result
    order_response: Optional[OrderResponse] = None
    order_placed: bool = False
    
    # Validation
    is_valid: bool = False
    rejection_reason: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Audit
    algo_id: Optional[str] = None
    executed_at: Optional[str] = None
    broker_platform: Optional[str] = None
    mode: str = "PAPER"
    
    # Costs
    estimated_brokerage: float = 0.0
    estimated_stt: float = 0.0
    estimated_net_pnl_at_target: float = 0.0
    estimated_net_pnl_at_stop: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "shares": self.shares,
            "position_value": self.position_value,
            "deciding_limit": self.deciding_limit,
            "risk_per_share": self.risk_per_share,
            "total_risk": self.total_risk,
            "reward_risk_ratio": self.reward_risk_ratio,
            "order_placed": self.order_placed,
            "order_id": self.order_response.order_id if self.order_response else None,
            "algo_id": self.algo_id,
            "executed_at": self.executed_at,
            "broker_platform": self.broker_platform,
            "mode": self.mode,
            "is_valid": self.is_valid,
            "rejection_reason": self.rejection_reason,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "estimated_brokerage": self.estimated_brokerage,
            "estimated_stt": self.estimated_stt,
            "estimated_net_pnl_at_target": self.estimated_net_pnl_at_target,
            "estimated_net_pnl_at_stop": self.estimated_net_pnl_at_stop,
        }


# =============================================================================
# Order Execution Pipeline
# =============================================================================

class OrderExecutionPipeline:
    """Complete order execution pipeline with risk checking.
    
    Pipeline steps:
    1. Kill switch check - blocked if active
    2. Daily/weekly limit check - blocked if exceeded
    3. Stop loss & target calculation - validated
    4. Position sizing - budget manager determines shares
    5. Order placement - routed through broker adapter
    6. Trade recording - audit trail updated
    
    Dual-mode:
    - PAPER: Orders simulated, no market impact
    - REAL_MONEY: Orders sent to broker (requires all gates + manual approval)
    
    Usage:
        pipeline = OrderExecutionPipeline(broker_adapter, budget_manager, stop_target_engine, gate_enforcer, kill_switch)
        result = pipeline.execute_order(
            symbol="RELIANCE",
            action=OrderSide.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target=2600.0,
        )
    """
    
    def __init__(self,
                 broker_adapter: Optional[BrokerAdapter] = None,
                 budget_manager: Optional[BudgetManager] = None,
                 stop_target_engine: Optional[StopTargetEngine] = None,
                 gate_enforcer: Optional[ComplianceGateEnforcer] = None,
                 kill_switch: Optional[KillSwitchManager] = None,
                 trading_mode: str = "PAPER"):
        self.broker_adapter = broker_adapter
        self.budget_manager = budget_manager or BudgetManager()
        self.stop_target_engine = stop_target_engine or StopTargetEngine()
        self.gate_enforcer = gate_enforcer or ComplianceGateEnforcer()
        self.kill_switch = kill_switch or KillSwitchManager()
        self.trading_mode = trading_mode  # "PAPER" or "REAL_MONEY"
        
        # Execution tracking
        self.execution_history: List[ExecutionResult] = []
        self.daily_executions: List[ExecutionResult] = []
        self.live_order_approved = False  # First live order approval flag
        
        print(f"OrderExecutionPipeline initialized:")
        print(f"  Mode: {self.trading_mode}")
        print(f"  Broker adapter: {broker_adapter is not None}")
        print(f"  Budget manager: {budget_manager is not None}")
        print(f"  Stop/target engine: {stop_target_engine is not None}")
        print(f"  Gate enforcer: {gate_enforcer is not None}")
        print(f"  Kill switch: {kill_switch is not None}")
    
    # =========================================================================
    # Main Execution Entry Point
    # =========================================================================
    
    def execute_order(self,
                      symbol: str,
                      action: OrderSide = OrderSide.BUY,
                      entry_price: float = 0.0,
                      stop_loss: Optional[float] = None,
                      target: Optional[float] = None,
                      stop_config: Optional[StopTargetConfig] = None,
                      budget_rules: Optional[BudgetRules] = None,
                      current_cash: Optional[float] = None,
                      auto_calculate_stop: bool = True,
                      auto_calculate_target: bool = True) -> ExecutionResult:
        """Execute a complete order through the full pipeline.
        
        Args:
            symbol: Stock symbol
            action: BUY or SELL
            entry_price: Entry price per share
            stop_loss: Stop loss price (calculated if not provided)
            target: Target price (calculated if not provided)
            stop_config: Stop/target configuration override
            budget_rules: Budget rules override
            current_cash: Current available cash
            auto_calculate_stop: Auto-calculate stop if not provided
            auto_calculate_target: Auto-calculate target if not provided
            
        Returns:
            ExecutionResult with full details
        """
        result = ExecutionResult(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss or 0.0,
            target=target,
            algo_id=f"ALGO-{uuid.uuid4().hex[:8].upper()}",
            executed_at=datetime.now().isoformat(),
            broker_platform=self.broker_adapter.config.platform.value if self.broker_adapter else "PAPER",
            mode=self.trading_mode,
        )
        
        # Step 1: Kill switch check
        can_order, block_reason = self.kill_switch.can_place_order()
        if not can_order:
            result.is_valid = False
            result.rejection_reason = block_reason
            result.validation_errors.append(block_reason)
            logger.warning(f"Order blocked: {block_reason}")
            self.execution_history.append(result)
            return result
        
        # Step 2: Daily/weekly limit check
        can_trade, trade_reason = self.budget_manager.can_trade_today()
        if not can_trade:
            result.is_valid = False
            result.rejection_reason = trade_reason
            result.validation_errors.append(trade_reason)
            logger.warning(f"Order blocked: {trade_reason}")
            self.execution_history.append(result)
            return result
        
        # Step 3: Stop loss & target calculation
        if auto_calculate_stop and stop_loss is None:
            stop_result = self.stop_target_engine.calculate(
                entry_price=entry_price,
                config=stop_config,
                shares=0,
            )
            if not stop_result.is_valid:
                result.is_valid = False
                result.rejection_reason = stop_result.rejection_reason
                result.validation_errors.extend(stop_result.validation_errors)
                result.warnings.extend(stop_result.warnings)
                logger.warning(f"Stop/target calculation failed: {stop_result.rejection_reason}")
                self.execution_history.append(result)
                return result
            
            result.stop_loss = stop_result.stop_loss
            result.target = stop_result.target if auto_calculate_target else target
            result.risk_per_share = stop_result.risk_per_share
            result.reward_risk_ratio = stop_result.reward_risk_ratio
            result.warnings.extend(stop_result.warnings)
        else:
            # Use provided stop/target
            result.stop_loss = stop_loss or entry_price * 0.95  # Default 5% stop
            if auto_calculate_target and target is None:
                risk = entry_price - result.stop_loss
                result.target = entry_price + (2.0 * risk)  # 2R default
                result.reward_risk_ratio = 2.0
            else:
                result.target = target
                result.risk_per_share = entry_price - result.stop_loss
                if result.risk_per_share > 0 and result.target:
                    result.reward_risk_ratio = (result.target - entry_price) / result.risk_per_share
        
        # Validate stop/target
        if result.stop_loss >= entry_price:
            result.is_valid = False
            result.rejection_reason = "Stop loss at or above entry price"
            result.validation_errors.append(result.rejection_reason)
            self.execution_history.append(result)
            return result
        
        if result.target and result.target <= entry_price:
            result.is_valid = False
            result.rejection_reason = "Target at or below entry price"
            result.validation_errors.append(result.rejection_reason)
            self.execution_history.append(result)
            return result
        
        # Step 4: Position sizing
        sizing = self.budget_manager.size_position(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=result.stop_loss,
            target=result.target,
            current_cash=current_cash,
            current_positions_count=0,  # Will be enhanced with position tracker
        )
        
        result.shares = sizing.recommended_shares
        result.position_value = sizing.position_value
        result.position_pct_of_capital = sizing.position_pct_of_capital
        result.deciding_limit = sizing.deciding_limit
        result.total_risk = sizing.total_risk_at_stop
        result.estimated_brokerage = sizing.estimated_brokerage
        result.estimated_stt = sizing.estimated_stt
        result.estimated_net_pnl_at_target = sizing.estimated_net_pnl_at_target
        result.estimated_net_pnl_at_stop = sizing.estimated_net_pnl_at_stop
        result.warnings.extend(sizing.validation_errors)  # These are warnings, not errors
        
        if not sizing.is_valid:
            result.is_valid = False
            result.rejection_reason = sizing.limit_reason
            result.validation_errors.append(sizing.limit_reason)
            logger.warning(f"Position sizing failed: {sizing.limit_reason}")
            self.execution_history.append(result)
            return result
        
        # Step 5: Check if shares > 0
        if result.shares <= 0:
            result.is_valid = False
            result.rejection_reason = "Position size reduced to zero by risk limits"
            result.validation_errors.append(result.rejection_reason)
            self.execution_history.append(result)
            return result
        
        # Step 6: Check compliance gates for REAL_MONEY
        if self.trading_mode == "REAL_MONEY":
            gate_result = self.gate_enforcer.check_all_gates()
            if not gate_result.all_passed:
                missing = ", ".join(gate_result.missing_gates)
                result.is_valid = False
                result.rejection_reason = f"Compliance gates not passed: {missing}"
                result.validation_errors.append(result.rejection_reason)
                logger.warning(f"Order blocked: compliance gates not passed: {missing}")
                self.execution_history.append(result)
                return result
            
            # Check first live order approval
            if not self.live_order_approved:
                result.is_valid = False
                result.rejection_reason = "First live order requires manual approval"
                result.validation_errors.append(result.rejection_reason)
                logger.warning("Order blocked: first live order approval required")
                self.execution_history.append(result)
                return result
        
        # Step 7: Place order through broker adapter
        order_request = OrderRequest(
            symbol=symbol,
            action=action,
            quantity=result.shares,
            price=entry_price,
            order_type=OrderType.MARKET,
            product=ProductType.CNC,  # Delivery default for weekly strategy
            validity="DAY",
            tag=f"SI-Trader-{result.algo_id}",
            strategy_id=result.algo_id,
            stop_loss=result.stop_loss,
            target=result.target,
        )
        
        if self.broker_adapter and self.broker_adapter.is_connected():
            # Real broker execution
            order_response = self.broker_adapter.place_order(order_request)
            if order_response:
                result.order_response = order_response
                result.order_placed = True
                result.algo_id = order_response.algo_id
                logger.info(f"Order placed: {order_response.order_id} ({order_response.algo_id})")
            else:
                result.is_valid = False
                result.rejection_reason = "Broker adapter rejected order"
                result.validation_errors.append(result.rejection_reason)
                logger.error("Broker adapter rejected order")
        else:
            # Paper trading mode - simulate order
            result.order_placed = True
            result.order_response = OrderResponse(
                order_id=f"PAPER-{result.algo_id}",
                algo_id=result.algo_id,
                status=OrderStatus.OPEN,
                filled_quantity=result.shares,
                average_price=entry_price,
                brokerage=result.estimated_brokerage,
                exchange="NSE",
                timestamp=result.executed_at,
            )
            logger.info(f"Paper order placed: {result.algo_id} ({result.shares} shares @ ₹{entry_price:.2f})")
        
        # Step 7: Mark as valid
        result.is_valid = True
        
        # Record execution
        self.execution_history.append(result)
        self.daily_executions.append(result)
        
        # Update budget manager
        self.budget_manager.open_position(symbol, result.shares, entry_price)
        
        logger.info(f"✅ Order executed: {symbol} {action.value} {result.shares} @ ₹{entry_price:.2f}")
        target_str = f"₹{result.target:.2f}" if result.target else "N/A"
        logger.info(f"   Stop: ₹{result.stop_loss:.2f} | Target: {target_str}")
        logger.info(f"   Risk: ₹{result.total_risk:.2f} | R:R {result.reward_risk_ratio:.2f}:1 | Limit: {result.deciding_limit}")
        
        return result
    
    # =========================================================================
    # Order Management
    # =========================================================================
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        if not self.broker_adapter or not self.broker_adapter.is_connected():
            logger.warning("No broker adapter connected for cancellation")
            return False
        
        if self.kill_switch.is_active():
            logger.warning("Kill switch active - cancellations blocked")
            return False
        
        return self.broker_adapter.cancel_order(order_id)
    
    def approve_first_live_order(self) -> bool:
        """Manual approval for first live order per BRD Section 14."""
        if self.trading_mode != "PAPER":
            logger.warning("Not in PAPER mode - approval not needed")
            return True
        
        # Check all gates first
        gate_result = self.gate_enforcer.check_all_gates()
        if not gate_result.all_passed:
            missing = ", ".join(gate_result.missing_gates)
            logger.warning(f"Cannot approve live order: gates not passed: {missing}")
            return False
        
        print("\n" + "=" * 60)
        print("📋 FIRST LIVE ORDER MANUAL APPROVAL")
        print("=" * 60)
        print("BRD Section 14 Requirement:")
        print("  - Previous version must pass compliance checks")
        print("  - Maximum 2 version promotions per calendar month")
        print()
        print(f"   Pilot capital: ₹{self.budget_manager.rules.pilot_capital:,.2f}")
        print(f"   Max weekly loss: ₹{self.budget_manager.rules.max_weekly_loss:,.2f}")
        print(f"   Max loss per trade: ₹{self.budget_manager.rules.max_loss_per_trade:,.2f}")
        print()
        print("   Type 'APPROVE' to execute first live order, or anything else to cancel:")
        
        try:
            approval = input().strip()
        except EOFError:
            print("❌ No input - order approval cancelled")
            return False
        
        if approval == "APPROVE":
            self.live_order_approved = True
            print("\n✅ First live order approved")
            print("   Mode: REAL_MONEY")
            print("   ⚠️  START SMALL - first order position size ≤ 5% of capital")
            return True
        else:
            print("❌ Order approval cancelled")
            return False
    
    # =========================================================================
    # Reporting
    # =========================================================================
    
    def get_execution_report(self) -> Dict[str, Any]:
        """Generate execution pipeline status report."""
        total_executions = len(self.execution_history)
        successful = sum(1 for e in self.execution_history if e.order_placed)
        rejected = total_executions - successful
        
        total_risk = sum(e.total_risk for e in self.execution_history if e.order_placed)
        total_value = sum(e.position_value for e in self.execution_history if e.order_placed)
        
        return {
            "trading_mode": self.trading_mode,
            "total_executions": total_executions,
            "successful_orders": successful,
            "rejected_orders": rejected,
            "total_position_value": total_value,
            "total_risk_at_stops": total_risk,
            "live_order_approved": self.live_order_approved,
            "kill_switch_active": self.kill_switch.is_active(),
            "broker_connected": self.broker_adapter.is_connected() if self.broker_adapter else False,
            "budget_report": self.budget_manager.get_risk_report(),
            "gate_status": {
                name: g.passed for name, g in self.gate_enforcer.gates.items()
            },
            "recent_executions": [
                e.to_dict() for e in self.execution_history[-10:]
            ],
        }
    
    def get_daily_executions(self) -> List[ExecutionResult]:
        """Get today's executions."""
        return list(self.daily_executions)
    
    def reset_daily(self) -> None:
        """Reset daily counters."""
        self.daily_executions = []
        self.budget_manager.reset_daily()
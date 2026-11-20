"""Kill Switch & Compliance Gate Enforcer for SI-Trader.

Implements BRD Section 14 compliance gates and emergency kill switch:

5 Compliance Gates (all must pass before REAL_MONEY):
1. Backtest gate - Strategy edge validated on history
2. Paper trading gate - 3+ months paper with positive net returns
3. Compliance gate - SEBI algo rules (2FA, audit trails, Algo-ID)
4. Risk gate - Position limits, kill switch, max weekly loss
5. Capital gate - ₹25,000 pilot capital confirmed

Kill Switch:
- Emergency exit that stops all trading immediately
- Triggered by: weekly loss limit, daily loss limit, manual trigger, system error
- Once triggered: no new orders, existing positions closed (paper mode)
- Requires manual reset after emergency conditions resolved
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger(__name__)

# =============================================================================
# Compliance Gate Status
# =============================================================================

@dataclass
class ComplianceGate:
    """Individual compliance gate status."""
    name: str
    description: str
    required: bool = True
    passed: bool = False
    evidence: Optional[str] = None
    checked_at: Optional[str] = None
    checked_by: Optional[str] = None
    
    def mark_passed(self, evidence: Optional[str] = None, checked_by: Optional[str] = None) -> None:
        self.passed = True
        self.evidence = evidence
        self.checked_at = datetime.now().isoformat()
        self.checked_by = checked_by
    
    def mark_failed(self, reason: Optional[str] = None) -> None:
        self.passed = False
        self.evidence = reason
        self.checked_at = datetime.now().isoformat()


@dataclass
class GateCheckResult:
    """Result of checking all compliance gates."""
    all_passed: bool
    gates: Dict[str, ComplianceGate]
    missing_gates: List[str]
    failed_gates: List[str]
    can_transition_to_real_money: bool
    
    def __post_init__(self):
        self.missing_gates = [name for name, g in self.gates.items() if not g.passed and g.required]
        self.failed_gates = [name for name, g in self.gates.items() if not g.passed]
        self.can_transition_to_real_money = self.all_passed and len(self.missing_gates) == 0


# =============================================================================
# Kill Switch
# =============================================================================

@dataclass
class KillSwitchEvent:
    """Record of a kill switch activation."""
    timestamp: str
    reason: str
    triggered_by: str  # "system", "manual", "weekly_loss", "daily_loss", "error"
    positions_closed: int
    daily_loss_at_trigger: float
    weekly_loss_at_trigger: float
    resolved: bool = False
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


# =============================================================================
# Compliance Gate Enforcer
# =============================================================================

class ComplianceGateEnforcer:
    """Enforces BRD Section 14 compliance gates.
    
    Manages 5 gates that must all pass before transitioning to REAL_MONEY:
    1. Backtest - strategy edge validated
    2. Paper trading - 3+ months with positive returns
    3. Compliance - SEBI algo rules, 2FA, audit trails
    4. Risk - position limits, kill switch, max loss
    5. Capital - pilot capital confirmed
    """
    
    GATE_NAMES = ["backtest", "paper_trading", "compliance", "risk", "capital"]
    
    def __init__(self, pilot_capital: float = 25000.0):
        self.pilot_capital = pilot_capital
        
        # Initialize all gates
        self.gates: Dict[str, ComplianceGate] = {}
        for name in self.GATE_NAMES:
            self.gates[name] = ComplianceGate(
                name=name,
                description=self._get_gate_description(name),
                required=True,
            )
        
        # Gate-specific requirements
        self.gate_requirements = {
            "backtest": {
                "min_years": 3,
                "min_edge_pct": 0.3,
            },
            "paper_trading": {
                "min_weeks": 16,  # ~4 months
                "min_net_return_pct": 0.0,
            },
            "compliance": {
                "require_2fa": True,
                "require_audit_trail": True,
                "require_algo_id": True,
                "require_static_ip": True,
            },
            "risk": {
                "max_weekly_loss_pct": 20.0,
                "max_position_pct": 10.0,
                "kill_switch_required": True,
            },
            "capital": {
                "min_pilot_capital": 25000.0,
            },
        }
    
    def _get_gate_description(self, name: str) -> str:
        descriptions = {
            "backtest": "Strategy edge validated on 3+ years of historical data",
            "paper_trading": "16 weeks paper trading with positive net returns",
            "compliance": "SEBI algo rules: 2FA, audit trails, Algo-ID, static IP",
            "risk": "Position limits, kill switch, max weekly loss (20% of capital)",
            "capital": "Pilot capital ₹25,000 confirmed and available",
        }
        return descriptions.get(name, "")
    
    def verify_gate(self, gate_name: str, passed: bool, 
                   evidence: Optional[str] = None,
                   checked_by: Optional[str] = None) -> bool:
        """Mark a gate as passed or failed."""
        if gate_name not in self.gates:
            logger.error(f"Unknown gate: {gate_name}")
            return False
        
        gate = self.gates[gate_name]
        if passed:
            gate.mark_passed(evidence, checked_by)
            logger.info(f"✅ Gate '{gate_name}' PASSED: {evidence or 'no evidence'}")
        else:
            gate.mark_failed(evidence)
            logger.warning(f"❌ Gate '{gate_name}' FAILED: {evidence or 'no evidence'}")
        
        return gate.passed
    
    def check_all_gates(self) -> GateCheckResult:
        """Check all compliance gates and return detailed result."""
        all_passed = all(g.passed for g in self.gates.values() if g.required)
        
        result = GateCheckResult(
            all_passed=all_passed,
            gates=dict(self.gates),
            missing_gates=[],
            failed_gates=[],
            can_transition_to_real_money=False,
        )
        
        return result
    
    def can_transition_to_real_money(self) -> tuple[bool, List[str]]:
        """Check if all gates pass for REAL_MONEY transition.
        
        Returns (can_transition, list_of_blocking_reasons).
        """
        result = self.check_all_gates()
        blocking = []
        
        if not result.all_passed:
            for name in result.missing_gates:
                gate = self.gates[name]
                blocking.append(f"{name}: {gate.description} (not passed)")
        
        return result.can_transition_to_real_money, blocking
    
    def get_gate_status(self, gate_name: str) -> Optional[ComplianceGate]:
        """Get status of a specific gate."""
        return self.gates.get(gate_name)
    
    def reset_all_gates(self) -> None:
        """Reset all gates to not-passed state."""
        for gate in self.gates.values():
            gate.passed = False
            gate.evidence = None
            gate.checked_at = None
            gate.checked_by = None
        logger.info("All compliance gates reset")


# =============================================================================
# Kill Switch Manager
# =============================================================================

class KillSwitchManager:
    """Emergency kill switch manager.
    
    Stops all trading immediately when triggered. Can be activated by:
    - Weekly loss limit breached
    - Daily loss limit breached
    - Manual trigger (trader or admin)
    - System error or disconnect
    
    Once triggered:
    - No new orders accepted
    - Existing positions flagged for exit (paper mode)
    - Requires manual reset after conditions resolved
    """
    
    def __init__(self, pilot_capital: float = 25000.0):
        self.pilot_capital = pilot_capital
        self.active = False
        self.trigger_reason: Optional[str] = None
        self.triggered_at: Optional[str] = None
        self.triggered_by: Optional[str] = None
        self.events: List[KillSwitchEvent] = []
        self.positions_closed_count = 0
        
        # Thresholds
        self.weekly_loss_limit = 5000.0  # 20% of ₹25,000
        self.daily_loss_limit = 1000.0   # 4% of ₹25,000
    
    def is_active(self) -> bool:
        """Check if kill switch is currently active."""
        return self.active
    
    def trigger(self, reason: str, triggered_by: str = "system",
               daily_loss: float = 0.0, weekly_loss: float = 0.0,
               positions_closed: int = 0) -> bool:
        """Trigger the kill switch.
        
        Args:
            reason: Human-readable reason for triggering
            triggered_by: Who/what triggered it ("system", "manual", "weekly_loss", etc.)
            daily_loss: Current daily loss at time of trigger
            weekly_loss: Current weekly loss at time of trigger
            positions_closed: Number of positions closed due to trigger
            
        Returns:
            True if kill switch was triggered (wasn't already active)
        """
        if self.active:
            logger.warning("Kill switch already active")
            return False
        
        self.active = True
        self.trigger_reason = reason
        self.triggered_at = datetime.now().isoformat()
        self.triggered_by = triggered_by
        self.positions_closed_count = positions_closed
        
        event = KillSwitchEvent(
            timestamp=self.triggered_at,
            reason=reason,
            triggered_by=triggered_by,
            positions_closed=positions_closed,
            daily_loss_at_trigger=daily_loss,
            weekly_loss_at_trigger=weekly_loss,
        )
        self.events.append(event)
        
        logger.error(f"🚨 KILL SWITCH TRIGGERED: {reason}")
        logger.error(f"   Triggered by: {triggered_by}")
        logger.error(f"   Daily loss: ₹{daily_loss:.2f}")
        logger.error(f"   Weekly loss: ₹{weekly_loss:.2f}")
        logger.error(f"   Positions closed: {positions_closed}")
        
        return True
    
    def reset(self, resolved_by: str) -> bool:
        """Reset the kill switch after emergency conditions resolved.
        
        Requires manual confirmation - cannot auto-reset.
        """
        if not self.active:
            logger.warning("Kill switch not active")
            return False
        
        self.active = False
        
        # Mark last event as resolved
        if self.events:
            self.events[-1].resolved = True
            self.events[-1].resolved_at = datetime.now().isoformat()
            self.events[-1].resolved_by = resolved_by
        
        self.trigger_reason = None
        self.triggered_at = None
        self.triggered_by = None
        
        logger.info(f"✅ Kill switch reset by {resolved_by}")
        return True
    
    def check_weekly_loss(self, current_weekly_loss: float) -> bool:
        """Check if weekly loss limit breached and trigger if so."""
        if current_weekly_loss >= self.weekly_loss_limit:
            return self.trigger(
                reason=f"Weekly loss limit breached: ₹{current_weekly_loss:.2f} ≥ ₹{self.weekly_loss_limit:.2f}",
                triggered_by="weekly_loss",
                weekly_loss=current_weekly_loss,
            )
        return False
    
    def check_daily_loss(self, current_daily_loss: float) -> bool:
        """Check if daily loss limit breached and trigger if so."""
        if current_daily_loss >= self.daily_loss_limit:
            return self.trigger(
                reason=f"Daily loss limit breached: ₹{current_daily_loss:.2f} ≥ ₹{self.daily_loss_limit:.2f}",
                triggered_by="daily_loss",
                daily_loss=current_daily_loss,
            )
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get kill switch status report."""
        return {
            "active": self.active,
            "trigger_reason": self.trigger_reason,
            "triggered_at": self.triggered_at,
            "triggered_by": self.triggered_by,
            "positions_closed": self.positions_closed_count,
            "total_events": len(self.events),
            "weekly_loss_limit": self.weekly_loss_limit,
            "daily_loss_limit": self.daily_loss_limit,
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "reason": e.reason,
                    "triggered_by": e.triggered_by,
                    "resolved": e.resolved,
                }
                for e in self.events[-5:]  # Last 5 events
            ],
        }
    
    def can_place_order(self) -> tuple[bool, Optional[str]]:
        """Check if order placement is allowed (kill switch not active).
        
        Returns (allowed, reason_if_blocked).
        """
        if self.active:
            return False, f"Kill switch active: {self.trigger_reason}"
        return True, None
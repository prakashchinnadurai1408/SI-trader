"""SI-Trader Risk Module - Risk Management & Compliance.

Provides risk management infrastructure for the Nifty 100 weekly delivery
auto-investing platform:

- BudgetManager: Position sizing based on max loss per trade, position cap,
  max order size, cash buffer, and daily loss limits (four-limit framework)
- StopTargetEngine: Stop loss and target calculation (opening range, ATR,
  percent, fixed price; 2R, 1R, custom targets)
- ComplianceGateEnforcer: BRD Section 14 compliance gates (backtest,
  paper trading, compliance, risk, capital)
- KillSwitchManager: Emergency kill switch for weekly/daily loss limits
- ExecutionPipeline: Complete order execution pipeline with risk checking
- DailyChecklist: 14-item pre-market checklist per BRD Section 20
- PortfolioOptimizer: Portfolio-level strategy allocation & risk management

BRD Compliance:
- Section 14: Paper trading default, kill switch, compliance gates
- Section 14: 3+ month paper trading before REAL_MONEY
- Cost model: STT 0.1% both sides, STCG 20%, brokerage 0.05%
- Weekly delivery: CNC product type
"""

from .budget_manager import BudgetManager, BudgetRules, PositionSizingResult
from .stop_target_engine import StopTargetEngine, StopTargetConfig, StopTargetResult
from .kill_switch import ComplianceGateEnforcer, KillSwitchManager, ComplianceGate, KillSwitchEvent
from .execution_pipeline import OrderExecutionPipeline, ExecutionResult
from .daily_checklist import DailyChecklist, ChecklistItem
from .portfolio_optimizer import PortfolioOptimizer, PortfolioOptimizationResult, StrategyAllocation

__all__ = [
    # Budget Manager
    "BudgetManager",
    "BudgetRules",
    "PositionSizingResult",
    
    # Stop/Target Engine
    "StopTargetEngine",
    "StopTargetConfig",
    "StopTargetResult",
    
    # Kill Switch & Compliance
    "ComplianceGateEnforcer",
    "KillSwitchManager",
    "ComplianceGate",
    "KillSwitchEvent",
    
    # Execution Pipeline
    "OrderExecutionPipeline",
    "ExecutionResult",
    
    # Daily Checklist
    "DailyChecklist",
    "ChecklistItem",
    
    # Portfolio Optimization
    "PortfolioOptimizer",
    "PortfolioOptimizationResult",
    "StrategyAllocation",
]
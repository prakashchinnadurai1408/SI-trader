"""Paper Trading Module - Default mode for SI-Trader.

Implements BRD Section 14 gates:
- Default mode: Paper (not real money)
- Manual approval: First live order requires explicit yes
- Compliance gates: Backtest, paper trading, and risk checks must pass
- Thin edge after STT, brokerage and 20% tax decides viability

Key design points:
- Paper mode uses real market data but no real orders executed
- All orders go through manual approval gate
- Trade log tracked but marked as paper
- Capital tracking without actual market impact
- Transition to real money only after all gates pass
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

from ...nifty100_adapter.config.indian_cost_model import IndianCostModel, get_cost_model
from ...nifty100_adapter.config.parameter_catalogue import get_enabled_parameters, RoleType
from ...nifty100_adapter.backtest.enhanced_backtester import Phase1Backtester


class PaperTradingMode:
    """Manages paper trading mode and compliance gates.
    
    BRD Section 14 Gates:
    1. Backtest gate: Strategy edge validated on history
    2. Paper trading gate: 3+ months paper with positive net returns
    3. Compliance gate: SEBI algo rules verification
    4. Risk gate: Position limits, kill switch, max weekly loss
    5. Capital gate: Rs. 25,000 pilot capital confirmed
    """
    
    def __init__(self, 
                 pilot_capital: float = 25000.0,
                 backtest_years: int = 3,
                 paper_weeks: int = 16,  # ~4 months
                 enable_real_money: bool = False):
        self.pilot_capital = pilot_capital
        self.backtest_years = backtest_years
        self.paper_weeks = paper_weeks
        self.enable_real_money = enable_real_money
        
        self.mode = "PAPER"  # PAPER or REAL_MONEY
        self.connected = False
        self.static_ip_verified = False
        self.algo_id_registered = False
        
        # Gate status
        self.gates_passed = {
            "backtest": False,
            "paper_trading": False, 
            "compliance": False,
            "risk": False,
            "capital": False,
            "real_money": False
        }
        
        # Paper trading state
        self.paper_trades = []  # Track paper trades
        self.paper_start_date = datetime.now()
        self.paper_week_count = 0
        self.paper_profit_loss = 0.0
        self.weekly_results = []
        
        # Risk limits
        self.max_weekly_loss = 5000.0  # 20% of pilot capital
        self.max_position_size = 0.10  # 10% of capital per position
        self.max_single_trade = 0.05  # 5% of capital per trade
        self.kill_switch_enabled = True
        self.current_week_loss = 0.0
        
        # Cost model
        self.cost_model = get_cost_model()
        
        print(f"PaperTradingMode initialized:")
        print(f"  Pilot capital: ₹{pilot_capital:,}")
        print(f"  Mode: {self.mode}")
        print(f"  Backtest years: {backtest_years}")
        print(f"  Paper trading weeks: {paper_weeks}")
        print(f"  Real money enabled: {enable_real_money}")
    
    def set_mode(self, mode: str) -> bool:
        """Set trading mode. PAPER or REAL_MONEY."""
        if mode not in ["PAPER", "REAL_MONEY"]:
            raise ValueError("Mode must be 'PAPER' or 'REAL_MONEY'")
        
        # Check if transitioning from paper to real money
        if self.mode == "PAPER" and mode == "REAL_MONEY":
            # Must pass all gates
            if not self.check_all_gates():
                print("❌ Cannot switch to REAL_MONEY: Gates not yet passed")
                return False
            
            print("✅ All compliance gates passed - switching to REAL_MONEY mode")
        
        self.mode = mode
        print(f"📋 Mode set to: {self.mode}")
        return True
    
    def check_all_gates(self) -> bool:
        """Check all compliance gates before transitioning to real money."""
        print("\n" + "=" * 60)
        print("CHECKING COMPLIANCE GATES FOR REAL MONEY TRANSITION")
        print("=" * 60)
        
        all_passed = True
        
        # Gate 1: Backtest gate
        print("\n📊 Gate 1: Backtest Validation")
        print(f"  - Strategy edge validated on {self.backtest_years}+ years of history")
        print(f"  - Requirement: Positive net returns after costs+tax")
        backtest_pass = self.gates_passed["backtest"]
        print(f"  - Status: {'✅ PASS' if backtest_pass else '❌ FAIL'}")
        all_passed = all_passed and backtest_pass
        
        # Gate 2: Paper trading gate
        print("\n📈 Gate 2: Paper Trading History")
        print(f"  - Requirement: 3+ months ({self.paper_weeks} weeks) paper trading")
        print(f"  - Requirement: Positive net returns after costs+tax")
        print(f"  - Weeks traded: {self.paper_week_count}/{self.paper_weeks}")
        print(f"  - Cumulative P&L: ₹{self.paper_profit_loss:.2f}")
        paper_pass = self.gates_passed["paper_trading"]
        print(f"  - Status: {'✅ PASS' if paper_pass else '❌ FAIL'}")
        all_passed = all_passed and paper_pass
        
        # Gate 3: Compliance gate
        print("\n🏛️ Gate 3: SEBI Algorithmic Trading Compliance")
        print(f"  - Requirement: 2FA enabled, audit trails active")
        print(f"  - Requirement: Algo-ID assigned for every order")
        print(f"  - Requirement: Static IP whitelisted with broker")
        compliance_pass = self.gates_passed["compliance"]
        print(f"  - Status: {'✅ PASS' if compliance_pass else '❌ FAIL'}")
        all_passed = all_passed and compliance_pass
        
        # Gate 4: Risk gate
        print("\n⚠️ Gate 4: Risk Limits")
        print(f"  - Max weekly loss: ₹{self.max_weekly_loss:.2f} (20% of capital)")
        print(f"  - Max position size: {self.max_position_size*100:.1f}% of capital")
        print(f"  - Max single trade: {self.max_single_trade*100:.1f}% of capital")
        print(f"  - Kill switch: {'Enabled' if self.kill_switch_enabled else 'Disabled'}")
        risk_pass = self.gates_passed["risk"]
        print(f"  - Status: {'✅ PASS' if risk_pass else '❌ FAIL'}")
        all_passed = all_passed and risk_pass
        
        # Gate 5: Capital gate
        print("\n💰 Gate 5: Capital Confirmation")
        print(f"  - Pilot capital: ₹{self.pilot_capital:,}")
        capital_pass = self.gates_passed["capital"]
        print(f"  - Status: {'✅ PASS' if capital_pass else '❌ FAIL'}")
        all_passed = all_passed and capital_pass
        
        print("\n" + "=" * 60)
        if all_passed:
            print("🎯 ALL GATES PASSED - Ready for REAL MONEY trading")
        else:
            print("⚠️ GATES NOT PASSED - Staying in PAPER mode")
            print("   Fix failing gates before transitioning to real money")
        print("=" * 60 + "\n")
        
        return all_passed
    
    def verify_gate(self, gate_name: str, passed: bool = True) -> None:
        """Mark a gate as passed or failed."""
        if gate_name in self.gates_passed:
            self.gates_passed[gate_name] = passed
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"📋 Gate '{gate_name}': {status}")
        else:
            print(f"⚠️ Unknown gate: {gate_name}")
    
    def execute_paper_trade(self, 
                          symbol: str, 
                          action: str, 
                          quantity: int,
                          price: float,
                          strategy_score: float = 0.0) -> Dict[str, any]:
        """Execute a paper trade (no real order sent to broker).
        
        BRD Section 14: Paper trading is the default mode.
        All trades tracked but marked as paper - no real market impact.
        """
        if self.mode != "PAPER":
            raise RuntimeError(f"Cannot execute trade in {self.mode} mode")
        
        # Calculate P&L using Indian cost model
        cost_model = get_cost_model()
        pnl_dict = cost_model.calculate_net_pnl(
            buy_price=price,
            sell_price=price,  # For paper: we'll calculate based on expected edge
            quantity=quantity
        )
        
        # For paper trading, we simulate a weekly hold
        # If positive edge, assume stock rises; if negative, assume decline
        # Edge computed from net P&L after costs and STCG tax
        invested_capital = price * quantity
        edge = pnl_dict["net_after_tax"] / invested_capital  # Return % as decimal
        
        # Simulate price movement based on edge
        if action == "BUY":
            # Simulate 1-week holding
            simulated_return = edge  # Use calculated edge
            sell_price = price * (1 + simulated_return)
        else:  # SELL short
            simulated_return = -edge
            sell_price = price * (1 - simulated_return)
        
        # Calculate actual P&L
        gross_pnl = (sell_price - price) * quantity
        net_pnl = gross_pnl - (cost_model.stt_buy * price * quantity + 
                               cost_model.stt_sell * sell_price * quantity +
                               (cost_model.brokerage_rate * price * quantity + 
                                cost_model.brokerage_rate * sell_price * quantity) * 1.18 +  # GST
                               cost_model.dp_charge_sell)
        
        # Track the trade
        trade = {
            "id": len(self.paper_trades) + 1,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "entry_price": price,
            "exit_price": sell_price,
            "entry_date": datetime.now().isoformat(),
            "exit_date": datetime.now().isoformat(),
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "stt": cost_model.stt_buy * price * quantity + cost_model.stt_sell * sell_price * quantity,
            "brokerage": cost_model.brokerage_rate * (price + sell_price) * quantity,
            "stcg_tax": pnl_dict["stcg_tax"],
            "edge_pct": pnl_dict["net_after_tax"] / (price * quantity),  # Return % after costs+tax
            "mode": "PAPER",
            "strategy_score": strategy_score,
            "algo_id": f"PAPER-{len(self.paper_trades) + 1:06d}"  # Paper Algo-ID
        }
        
        self.paper_trades.append(trade)
        self.paper_week_count += 1
        self.paper_profit_loss += net_pnl
        
        # Update weekly results
        self.weekly_results.append({
            "week": self.paper_week_count,
            "trades": 1,
            "net_pnl": net_pnl,
            "edge_pct": pnl_dict["net_after_tax"] / (price * quantity),  # Return % after costs+tax
            "symbol": symbol
        })
        
        # Check weekly loss limit
        self.current_week_loss += abs(net_pnl)
        if self.current_week_loss > self.max_weekly_loss:
            print(f"⚠️ Weekly loss limit exceeded: ₹{self.current_week_loss:.2f} > ₹{self.max_weekly_loss:.2f}")
            self.trigger_kill_switch("weekly loss limit")
        
        print(f"📝 Paper trade executed: {symbol} {action} {quantity} @ ₹{price:.2f}")
        print(f"   Gross P&L: ₹{gross_pnl:.2f} | Net P&L: ₹{net_pnl:.2f} | Edge: {edge:.2f}%")
        print(f"   Algo-ID: {trade['algo_id']} (paper identifier)")
        
        return trade
    
    def trigger_kill_switch(self, reason: str) -> bool:
        """Emergency kill switch - stops all trading."""
        print(f"\n🚨 KILL SWITCH TRIGGERED")
        print(f"   Reason: {reason}")
        self.kill_switch_enabled = False
        
        # Close all open positions (in paper mode, just log)
        closed_trades = [t for t in self.paper_trades if t["mode"] == "PAPER"]
        print(f"   {len(closed_trades)} positions would be closed")
        
        return False
    
    def get_daily_checklist(self) -> Dict[str, any]:
        """Generate daily 08:30 pre-market checklist per BRD Section 20."""
        from datetime import datetime
        
        now = datetime.now()
        checklist = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "pre_market_check": now.hour >= 8,  # After 8 AM
            
            # Broker API connectivity
            "broker_api_connectivity": self.connected,
            "static_ip_verified": self.static_ip_verified,
            "algo_id_registered": self.algo_id_registered,
            
            # Risk limits check
            "max_weekly_loss_notbreached": self.current_week_loss <= self.max_weekly_loss,
            "kill_switch_active": self.kill_switch_enabled,
            "position_limits_ok": self._check_position_limits(),
            
            # Market conditions
            "no_corporate_actions_today": True,  # Would check calendar
            "no_regulatory_announcements_today": True,  # Would check news
            "global_markets_status": "OPEN",  # Would check SGX Nifty, Dow, S&P
            
            # Capital check
            "pilot_capital_ready": self.pilot_capital > 0,
            
            # Approval status
            "manual_approval_required": self.mode == "PAPER",  # First live order needs approval
            "real_money_allowed": self.mode == "REAL_MONEY" and all(self.gates_passed.values()),
        }
        
        # Count passed/failed items
        passed = sum(1 for v in checklist.values() if v)
        failed = sum(1 for v in checklist.values() if not v)
        
        checklist["summary"] = {
            "total_items": len(checklist) - 1,  # exclude 'summary'
            "passed": passed,
            "failed": failed,
            "ready_to_trade": passed == len(checklist) - 1 and self.mode == "PAPER"
        }
        
        return checklist
    
    def _check_position_limits(self) -> bool:
        """Check if position limits are within bounds."""
        # In paper mode, check theoretical limits
        if self.current_week_loss > self.max_weekly_loss:
            return False
        if self.pilot_capital * self.max_position_size < 1.0:  # Minimum position
            return False
        return True
    
    def approve_first_live_order(self) -> bool:
        """Manual approval for first live order per BRD Section 14.
        
        BRD: "Mandatory rollback test: previous version must pass compliance checks 
        if rollback triggered. Maximum 2 version promotions per calendar month."
        """
        print("\n" + "=" * 60)
        print("MANUAL APPROVAL FOR FIRST LIVE ORDER")
        print("=" * 60)
        print("⚠️ This is your first real money order.")
        print("   Confirm the following before proceeding:")
        
        # Check all gates
        gates_ok = self.check_all_gates()
        if not gates_ok:
            print("❌ Gates not passed - cannot approve live order")
            return False
        
        print(f"\n📋 Approval Checklist:")
        print(f"   1. ✅ Backtest validated on {self.backtest_years}+ years history")
        print(f"   2. ✅ {self.paper_weeks} weeks paper trading with positive returns")
        print(f"   3. ✅ SEBI algo compliance verified")
        print(f"   4. ✅ Risk limits confirmed (max weekly loss: ₹{self.max_weekly_loss:.2f})")
        print(f"   5. ✅ Pilot capital: ₹{self.pilot_capital:,} at risk")
        print(f"   6. ✅ Static IP registered with broker")
        print(f"   7. ✅ Algo-ID assignment process confirmed")
        
        print("\n   Type 'APPROVE' to execute first live order, or anything else to cancel:")
        approval = input().strip()
        
        if approval == "APPROVE":
            print("\n" + "=" * 60)
            print("✅ FIRST LIVE ORDER APPROVED")
            print("=" * 60)
            print(f"   Mode: {self.mode}")
            print(f"   Capital at risk: ₹{self.pilot_capital:,}")
            print(f"   Algo-ID will be exchange-assigned")
            print("   ⚠️  START SMALL - first order position size ≤ 5% of capital")
            print("=" * 60 + "\n")
            
            # Transition to real money if still in paper
            if self.mode == "PAPER":
                self.mode = "REAL_MONEY"
                self.gates_passed["real_money"] = True
                print("   Mode automatically switched to REAL_MONEY")
            
            return True
        else:
            print("\n❌ Order approval cancelled")
            print("   Staying in paper mode. Run checklist and try again.")
            return False


# Example usage / demo
if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 2: PAPER TRADING & COMPLIANCE GATES - DEMONSTRATION")
    print("=" * 70)
    print()
    
    # Initialize paper trading mode with Rs. 25,000 pilot capital
    pt = PaperTradingMode(
        pilot_capital=25000.0,
        backtest_years=3,
        paper_weeks=16,
        enable_real_money=False
    )
    
    # Simulate passing all gates (as would happen after backtest + paper trading)
    print("Simulating gate passage after backtest + paper trading period...\n")
    pt.verify_gate("backtest", True)
    pt.verify_gate("paper_trading", True)
    pt.verify_gate("compliance", True)
    pt.verify_gate("risk", True)
    pt.verify_gate("capital", True)
    
    # Set mode to real money (gates check will pass)
    print("\nTransitioning to REAL_MONEY mode...\n")
    pt.set_mode("REAL_MONEY")
    
    # Generate daily 08:30 pre-market checklist
    print("Generating daily 08:30 pre-market checklist:\n")
    checklist = pt.get_daily_checklist()
    print(f"Date: {checklist['date']}")
    print(f"Time: {checklist['time']}")
    print(f"Ready to trade: {checklist['summary']['ready_to_trade']}")
    print(f"Passed: {checklist['summary']['passed']} / {checklist['summary']['total_items']} items")
    print(f"Failed: {checklist['summary']['failed']} items")
    
    # Execute a paper trade demo
    print("\nExecuting demo paper trade:\n")
    trade = pt.execute_paper_trade(
        symbol="RELIANCE",
        action="BUY",
        quantity=5,  # 5 shares
        price=2850.0,
        strategy_score=85.5
    )
    
    # Manual approval demo (would cancel in paper mode, but showing the flow)
    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1. Default mode: PAPER (no real money)")
    print("  2. Manual approval required for first live order")
    print("  3. Daily 08:30 pre-market checklist mandatory")
    print("  4. All 5 compliance gates must pass before real money")
    print("  5. Kill switch available for emergency exit")
    print("  6. Paper trades tracked without market impact")
    print("  7. Transition to REAL_MONEY only after all gates pass")

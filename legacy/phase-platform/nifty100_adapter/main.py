"""SI-Trader Main Entry Point"""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def main():
    """Main entry point for SI-Trader platform."""
    print("=" * 60)
    print("SI-TRADER - Nifty 100 Weekly Delivery Platform")
    print("=" * 60)
    print()
    print("Available commands:")
    print("  1.  Test Phase 1  - Universe, parameters, cost model")
    print("  2.  Test Phase 2  - Paper trading & compliance gates")
    print("  3.  Demo Platform - Quick functionality demo")
    print("  4.  Run Backtest  - Historical backtest simulation")
    print()
    print("Type 'python -m nifty100_weekly.nifty100_adapter.tests' for full test suite")
    print()
    print("For documentation, see the BRD (BRD Nifty 100 Weekly Delivery Platform)")
    print("=" * 60)

if __name__ == "__main__":
    main()
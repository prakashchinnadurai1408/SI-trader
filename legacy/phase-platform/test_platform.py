"""Test script for the Nifty 100 weekly delivery platform."""

import sys
import os
import pandas as pd
import numpy as np

# Add platform to path
sys.path.insert(0, os.path.dirname(__file__))

from platform.config.indian_cost_model import IndianCostModel, get_cost_model
from platform.config.parameter_catalogue import validate_weight_total, get_enabled_parameters
from platform.backtest.weekly_backtester import WeeklyBacktester


def test_cost_model():
    """Test Indian cost model calculations."""
    print("=" * 60)
    print("TEST 1: Indian Cost Model")
    print("=" * 60)
    
    cost = get_cost_model()
    
    # Test roundtrip cost calculation
    buy_price = 1000.0
    sell_price = 1050.0  # 5% gain
    quantity = 1
    
    pnl = cost.calculate_net_pnl(buy_price, sell_price, quantity)
    
    print(f"Buy price: ₹{buy_price}")
    print(f"Sell price: ₹{sell_price}")
    print(f"Gross P&L: ₹{pnl['gross_pnl']:.2f}")
    print(f"Total costs: ₹{pnl['total_costs']:.2f}")
    print(f"Pre-tax P&L: ₹{pnl['pre_tax_pnl']:.2f}")
    print(f"STCG tax (20%): ₹{pnl['stcg_tax']:.2f}")
    print(f"Net after tax: ₹{pnl['net_after_tax']:.2f}")
    print(f"Costs breakdown: {pnl['breakdown']}")
    print(f"Gross return %: {pnl['gross_return_pct']:.2f}%")
    print(f"Net return %: {pnl['net_return_pct']:.2f}%")
    print(f"Edge (net return): {'PASS' if pnl['edge_passes'] else 'VERIFY'}")
    print()
    
    # Test with loss
    sell_price_low = 970.0  # 3% loss
    pnl2 = cost.calculate_net_pnl(buy_price, sell_price_low, quantity)
    print(f"--- With 3% loss ---")
    print(f"Sell price: ₹{sell_price_low}")
    print(f"Net after tax: ₹{pnl2['net_after_tax']:.2f}")
    edge_status = 'PASS' if pnl2['edge_passes'] else 'VERIFY (loss accepted for offset)'
    print(f"Edge: {edge_status}")
    print()


def test_parameter_catalogue():
    """Test parameter catalogue weight validation."""
    print("=" * 60)
    print("TEST 2: Parameter Catalogue")
    print("=" * 60)
    
    valid = validate_weight_total()
    print(f"Parameter weight total valid: {valid}")
    assert valid, "Weight total should be 100"
    
    enabled = get_enabled_parameters()
    print(f"Enabled parameters count: {len(enabled)}")
    
    # Check total weight
    total_w = sum(p.weight for p in enabled)
    print(f"Sum of enabled weights: {total_w}")
    print()
    
    # Display parameter roles distribution
    from platform.config.parameter_catalogue import RoleType
    for role in RoleType:
        role_params = [p for p in enabled if p.role_type == role]
        if role_params:
            print(f"  {role.value:15s}: {len(role_params)} params, "
                  f"total weight: {sum(p.weight for p in role_params)}")
    print()


def test_backtester():
    """Test weekly backtester pipeline."""
    print("=" * 60)
    print("TEST 3: Weekly Backtester Pipeline")
    print("=" * 60)
    
    # Create test universe
    uni_df = pd.DataFrame({
        'symbol': ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 
                   'SBIN', 'BHARTIARTL', 'MARUTI', 'HCLTECH', 'ITC'],
        'close': [2850.0, 3850.0, 1520.0, 1520.0, 925.0,
                  635.0, 825.0, 985.0, 1130.0, 415.0],
        'daily_turnover_crore': [120.5, 85.3, 45.2, 65.8, 38.7,
                                  72.1, 45.6, 32.8, 55.3, 28.4],
        'pe_ratio_vs_sector': [1.05, 0.98, 1.12, 1.03, 0.95,
                                1.18, 1.08, 0.92, 0.88, 0.75],
        'debt_equity_ratio': [0.35, 0.12, 0.45, 0.21, 0.28,
                               0.85, 0.15, 0.10, 0.22, 0.65],
        'roe_trend': [18.5, 22.1, 15.3, 19.7, 16.8,
                       14.2, 17.5, 21.3, 18.1, 12.4],
        'price_momentum_weekly': [1.2, -0.5, 2.1, 0.8, -1.3,
                                  0.5, 1.8, -0.3, 2.5, -0.8],
        'promoter_pledging_pct': [15.2, 5.8, 8.5, 12.3, 18.9,
                                  22.1, 6.5, 3.2, 10.8, 15.5],
    })
    
    # Instantiate backtester with Rs. 25,000 pilot capital context
    bt = WeeklyBacktester(
        universe=uni_df,
        top_n=5,
        min_liquidity_crore=25.0
    )
    
    result = bt.run_weekly_pipeline()
    
    print(f"Stocks considered: {result['total_considered']}")
    print(f"After liquidity filter: {result['filter_stats']['after_liquidity']}")
    print(f"After veto rules: {result['filter_stats']['after_veto']}")
    print(f"Edge passes: {result['filter_stats']['edge_passes']}")
    print(f"Edge fails: {result['filter_stats']['edge_fails']}")
    print(f"Selected top {result['filter_stats']['selected_top_n']}:")
    
    for s in result['selection']:
        print(f"  - {s['symbol']:12s}: Score={s['score']:5.1f}, "
              f"Edge={s['edge_pct']:6.2f}%, Costs={s['costs_pct']:6.2f}%")
    
    print()
    print(f"Cost model used:")
    cm = result['cost_model_used']
    print(f"  STT buy: {cm['stt_buy']*100:.2f}%")
    print(f"  STT sell: {cm['stt_sell']*100:.2f}%")
    print(f"  Brokerage rate: {cm['brokerage_rate']*100:.3f}%")
    print(f"  STCG tax rate: {cm['stcg_tax_rate']*100:.0f}%")
    print(f"  Roundtrip cost: {cm['total_roundtrip_cost_pct']:.2f}%")
    print()
    
    print(f"Parameter weight total: {result['parameter_weight_total']}")
    print()


def test_pilot_capital():
    """Test with Rs. 25,000 pilot capital scenario."""
    print("=" * 60)
    print("TEST 4: Pilot Capital Allocation (Rs. 25,000)")
    print("=" * 60)
    
    cost = get_cost_model()
    
    # Example: If strategy selects 5 stocks with positive edge
    # Equal weight allocation: ₹5,000 per stock
    capital = 25000
    top_n = 5
    allocation_per_stock = capital / top_n
    
    print(f"Pilot capital: ₹{capital:,}")
    print(f"Top N selection: {top_n}")
    print(f"Allocation per stock: ₹{allocation_per_stock:,}")
    print()
    
    # Calculate how many shares per stock at approximate prices
    # Using average of test universe prices
    avg_price = 1200  # rough average
    shares_per_stock = allocation_per_stock / avg_price
    print(f"Approx. price per stock: ₹{avg_price:,}")
    print(f"Shares per stock (round lot): {shares_per_stock:.1f}")
    print(f"Capital used: ₹{shares_per_stock * avg_price * top_n:,.0f}")
    print()
    
    # Show cost impact on weekly gain/loss
    print("Weekly P&L scenarios after costs+tax:")
    scenarios = [
        ("1% gain", 1.0),
        ("2% gain", 2.0),
        ("5% gain", 5.0),
        ("1% loss", -1.0),
        ("2% loss", -2.0),
    ]
    
    for name, pct in scenarios:
        # Buy at ₹1200, sell at 1200*(1+pct/100)
        sell = avg_price * (1 + pct / 100)
        pnl_dict = cost.calculate_net_pnl(avg_price, sell, 1)  # 1 share
        total_investment = avg_price
        net_return = pnl_dict['net_after_tax']
        
        # Annualise (rough: 52 weeks)
        # Only if positive edge
        print(f"  {name:8s}: Gross {pnl_dict['gross_return_pct']:5.1f}% "
              f"→ Net {pnl_dict['net_return_pct']:6.2f}% "
              f"(₹{net_return:8.2f} per share)")
    print()


def main():
    """Run all tests."""
    print("\nNIFTY 100 WEEKLY DELIVERY PLATFORM - MODULE TESTS")
    print("=" * 60)
    print(f"Pilot capital: Rs. 25,000 (user decision)")
    print(f"Broker: Configurable (adapter pattern)")
    print(f"Usage: Own use first, then commercial product")
    print("=" * 60 + "\n")
    
    try:
        test_cost_model()
        test_parameter_catalogue()
        test_backtester()
        test_pilot_capital()
        
        print("=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Confirm HDFC Securities API access (or choose alternative broker)")
        print("2. Run backtest on historical Nifty 100 data (2+ years)")
        print("3. Validate strategy edge after costs+tax")
        print("4. Paper trade for 3+ months before real money")
        print("5. Then consider commercial product launch (with SEBI legal review)")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
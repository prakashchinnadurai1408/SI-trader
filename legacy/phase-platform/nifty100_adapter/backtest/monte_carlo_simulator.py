"""Monte Carlo Edge Simulator for SI-Trader Platform.

Performs 10,000+ simulations to determine the probability that a strategy's
edge exceeds the BRD threshold of ~0.3% roundtrip + 20% STCG cost.

BRD Reference: Section 27.5 edge validation; Phase 3 advanced analytics.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np
from datetime import datetime


class MonteCarloSimulator:
    """Simulates strategy performance across random market scenarios."""
    
    def __init__(self, cost_model, n_simulations: int = 10000, 
                 n_positions: int = 5, holding_weeks: int = 1):
        self.cost_model = cost_model
        self.n_simulations = n_simulations
        self.n_positions = n_positions
        self.holding_weeks = holding_weeks
        
    def simulate(self, expected_weekly_edge: float, 
                 weekly_volatility: float = 0.0,
                 risk_free_rate: float = 0.0) -> Dict[str, float]:
        """
        Run Monte Carlo simulation.
        
        Args:
            expected_weekly_edge: Expected edge per week after costs (e.g., 0.15%)
            weekly_volatility: Weekly return volatility (e.g., 0.02 = 2%)
            risk_free_rate: Risk-free weekly rate (e.g., 0.001 = 0.1%)
            
        Returns:
            Simulation results dictionary
        """
        results = []
        
        for _ in range(self.n_simulations):
            # Simulate weekly returns with expected edge + random noise
            weekly_returns = []
            
            for _ in range(self.holding_weeks):
                # Random component: normally distributed volatility
                noise = np.random.normal(0, weekly_volatility)
                # Expected edge component
                edge_component = expected_weekly_edge
                # Total weekly P&L % (gross before costs)
                weekly_pnl = edge_component + noise
                weekly_returns.append(weekly_pnl)
            
            # Calculate gross return over holding period
            gross_return = np.prod(1 + np.array(weekly_returns)) - 1
            
            # Calculate total costs and tax
            # Approximate: each week has roundtrip cost + STCG on positive P&L
            total_costs = 0.0
            total_stcg = 0.0
            
            for r in weekly_returns:
                # Costs per week (0.38% roundtrip approx)
                total_costs += abs(r) * 0.0038  # approximate cost proportional to return
                # STCG: 20% of positive P&L
                if r > 0:
                    total_stcg += r * 0.20
            
            net_return = gross_return - total_costs - total_stcg
            
            # Annualize (assuming 52 weeks)
            annual_return = (1 + net_return) ** 52 - 1 if net_return > -1 else -100
            
            results.append({
                "gross_return": gross_return,
                "net_return": net_return,
                "annualized_return": annual_return,
                "total_costs": total_costs,
                "total_stcg": total_stcg,
                "edge_exceeded": net_return > 0.003  # 0.3% BRD threshold
            })
        
        # Aggregate statistics
        edge_passes = sum(1 for r in results if r["edge_exceeded"])
        net_returns = [r["net_return"] for r in results]
        annual_returns = [r["annualized_return"] for r in results]
        
        return {
            "n_simulations": self.n_simulations,
            "probability_edge_exceeds_threshold": edge_passes / self.n_simulations,
            "probability_profitable": sum(1 for r in results if r["net_return"] > 0) / self.n_simulations,
            "probability_annual_positive": sum(1 for r in results if r["annualized_return"] > 0) / self.n_simulations,
            "mean_net_return": np.mean(net_returns),
            "median_net_return": np.median(net_returns),
            "std_net_return": np.std(net_returns),
            "mean_annual_return": np.mean(annual_returns),
            "median_annual_return": np.median(annual_returns),
            "worst_5pct_annual": np.percentile(annual_returns, 5),
            "best_5pct_annual": np.percentile(annual_returns, 95),
            "sharpe_ratio": np.mean(annual_returns) / np.std(annual_returns) if np.std(annual_returns) > 0 else 0,
            "results": results
        }
    
    def analyze_edge_sensitivity(self, 
                                expected_edges: List[float],
                                volatility: float = 0.02,
                                risk_free: float = 0.0) -> Dict[float, Dict]:
        """
        Analyze how probability of edge changes with different expected edges.
        
        Args:
            expected_edges: List of expected weekly edges to test
            volatility: Weekly return volatility
            risk_free: Risk-free rate
            
        Returns:
            Dictionary mapping expected edge to simulation results
        """
        results = {}
        for edge in expected_edges:
            sim = self.simulate(expected_weekly_edge=edge, 
                              weekly_volatility=volatility,
                              risk_free_rate=risk_free)
            results[edge] = {
                "probability_edge_exceeds_threshold": sim["probability_edge_exceeds_threshold"],
                "probability_profitable": sim["probability_profitable"],
                "mean_net_return": sim["mean_net_return"],
            }
        return results


# Default simulator instance for BRD validation
default_simulator = MonteCarloSimulator(
    cost_model=None,  # Will use IndianCostModel when needed
    n_simulations=10000,
    n_positions=5,
    holding_weeks=1
)


def quick_edge_probability(expected_edge: float, n_trials: int = 1000) -> Dict:
    """
    Quick edge probability check without full 10K simulation.
    Used for fast feedback in backtester pipeline.
    """
    edge_passes = 0
    profitable_trades = 0
    
    for _ in range(n_trials):
        # Simulate single week return
        noise = np.random.normal(0, 0.02)  # 2% volatility
        weekly_pnl = expected_edge + noise
        
        # Apply costs (0.38% roundtrip + 20% STCG on positive)
        total_costs = abs(weekly_pnl) * 0.0038
        stcg = weekly_pnl * 0.20 if weekly_pnl > 0 else 0
        net_pnl = weekly_pnl - total_costs - stcg
        
        if net_pnl > 0.003:  # BRD threshold
            edge_passes += 1
        if net_pnl > 0:
            profitable_trades += 1
    
    return {
        "probability_edge_exceeds_threshold": edge_passes / n_trials,
        "probability_profitable": profitable_trades / n_trials,
        "expected_edge": expected_edge
    }


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("MONTE CARLO EDGE SIMULATION - BRD COMPLIANCE TEST")
    print("=" * 60)
    print()
    
    # Test with 0.15% expected edge (current platform average)
    results = default_simulator.simulate(expected_weekly_edge=0.15, weekly_volatility=0.02)
    
    print(f"Expected weekly edge: {0.15:.2f}%")
    print(f"Probability edge > 0.3% threshold: {results['probability_edge_exceeds_threshold']*100:.1f}%")
    print(f"Probability profitable: {results['probability_profitable']*100:.1f}%")
    print(f"Mean net return: {results['mean_net_return']*100:.2f}%")
    print(f"Mean annual return: {results['mean_annual_return']*100:.1f}%")
    print(f"Worst 5% annual: {results['worst_5pct_annual']*100:.1f}%")
    print(f"Best 5% annual: {results['best_5pct_annual']*100:.1f}%")
    print(f"Sharpe ratio: {results['sharpe_ratio']:.2f}")
    print()
    
    # Sensitivity analysis
    print("SENSITIVITY ANALYSIS:")
    print("-" * 40)
    edges_to_test = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
    sensitivity = default_simulator.analyze_edge_sensitivity(edges_to_test)
    
    for edge, stats in sensitivity.items():
        print(f"  Edge {edge:.1f}% → P(>0.3% threshold): {stats['probability_edge_exceeds_threshold']*100:.1f}%")
    
    print()
    print("=" * 60)
    print("CONCLUSION:")
    if results['probability_edge_exceeds_threshold'] > 0.5:
        print("✅ Strategy has >50% probability of exceeding BRD 0.3% edge threshold")
    else:
        print("⚠️ Strategy edge below BRD threshold; consider parameter optimization")
    print("=" * 60)
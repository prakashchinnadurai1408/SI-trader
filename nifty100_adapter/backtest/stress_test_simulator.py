"""Scenario/Stress Testing Simulator for SI-Trader Platform.

BRD Reference: Section 24 risk management; Phase 3 advanced risk validation.
Tests strategy performance under specific stressed market conditions
to evaluate tail risk and compliance with risk limits.

Key Capabilities:
- Multiple stress scenarios (crash, high volatility, liquidity freeze)
- Adjustable severity parameters
- BRD-compliant risk metric calculation
- Production readiness impact assessment
"""

from typing import List, Dict, Optional, Tuple
from enum import Enum
import numpy as np
from datetime import datetime


class StressTestSimulator:
    """
    Scenario/Stress Testing simulator for strategy risk validation.

    Tests strategy performance under predefined stressed market conditions
    to ensure compliance with risk limits and identify tail risk.

    Supported Scenarios:
    - 'crash': Sudden market decline (-10% to -30% in 1-4 weeks)
    - 'high_vol': Volatility spike (2x-5x normal volatility)
    - 'liquidity_freeze': Reduced liquidity (wider spreads, lower returns)
    - 'simultaneous': Combination of multiple stresses
    """

    class ScenarioType(Enum):
        """Available stress scenario types."""
        CRASH = "crash"
        HIGH_VOL = "high_vol"
        LIQUIDITY_FREEZE = "liquidity_freeze"
        SIMULTANEOUS = "simultaneous"

    def __init__(self, base_returns: np.ndarray, base_volatility: Optional[float] = None):
        """Initialize stress test simulator."""
        self.base_returns = np.asarray(base_returns)
        self.base_volatility = base_volatility or np.std(base_returns) if len(base_returns) > 1 else 0.02
        self.scenario_results: Dict = {}

    def run_scenario(self, scenario_type: ScenarioType, severity: float = 1.0,
                     n_weeks: int = 4) -> Dict:
        """Run a single stress scenario test."""
        returns = self.base_returns.copy()
        vol = self.base_volatility

        weekly_returns = []
        cumulative_return = 0.0
        max_drawdown = 0.0
        weeks_losing = 0

        for week in range(n_weeks):
            if scenario_type == self.ScenarioType.CRASH:
                crash_magnitude = np.random.normal(-severity * 0.05, severity * 0.01)
                weekly_return = crash_magnitude
            elif scenario_type == self.ScenarioType.HIGH_VOL:
                vol_multiplier = 1.0 + severity * 0.5
                student_t_scale = severity * 0.02
                weekly_return = np.random.normal(0, vol_multiplier * self.base_volatility)
                if np.random.random() < 0.1 * severity:
                    weekly_return += np.random.normal(0, severity * 0.05)
            elif scenario_type == self.ScenarioType.LIQUIDITY_FREEZE:
                liquidity_factor = 1.0 - severity * 0.3
                weekly_return = np.random.normal(0, self.base_volatility * (1.0 + severity * 0.5))
                weekly_return *= liquidity_factor
            elif scenario_type == self.ScenarioType.SIMULTANEOUS:
                crash = np.random.normal(-severity * 0.04, severity * 0.01)
                vol_stress = self.base_volatility * (1.0 + severity * 0.5)
                liquidity_factor = 1.0 - severity * 0.3
                weekly_return = crash * vol_stress / self.base_volatility * liquidity_factor
            else:
                weekly_return = 0.0

            weekly_returns.append(weekly_return)
            cumulative_return += weekly_return

            if cumulative_return < max_drawdown:
                max_drawdown = cumulative_return
            if weekly_return < 0:
                weeks_losing += 1

        total_stress_return = cumulative_return
        avg_weekly_return = cumulative_return / n_weeks if n_weeks > 0 else 0
        probability_losing = weeks_losing / n_weeks if n_weeks > 0 else 0

        exceeds_brd_threshold = total_stress_return < -0.003
        high_drawdown = max_drawdown < -0.10

        return {
            "scenario_type": scenario_type.value,
            "severity": severity,
            "n_weeks": n_weeks,
            "total_stress_return": total_stress_return,
            "avg_weekly_return": avg_weekly_return,
            "probability_losing": probability_losing,
            "max_drawdown": max_drawdown,
            "weeks_losing": weeks_losing,
            "exceeds_brd_threshold": exceeds_brd_threshold,
            "high_drawdown": high_drawdown,
            "scenario_passes": not exceeds_brd_threshold and not high_drawdown,
        }

    def run_all_scenarios(self, severities: List[float] = None,
                          n_weeks: int = 4) -> Dict:
        """Run all scenario types at specified severities."""
        if severities is None:
            severities = [1.0, 2.0, 3.0]

        all_results = {}
        for scenario_type in self.ScenarioType:
            all_results[scenario_type.value] = {}
            for severity in severities:
                result = self.run_scenario(scenario_type, severity, n_weeks)
                all_results[scenario_type.value][severity] = result

        return {
            "scenarios_tested": len(self.ScenarioType),
            "severities_tested": len(severities),
            "results": all_results,
            "is_production_ready": self._check_production_readiness(all_results),
        }

    def _check_production_readiness(self, all_results: dict) -> bool:
        """Check if strategy passes stress testing for production readiness."""
        for scenario_name, severities in all_results.items():
            for sev, result in severities.items():
                if sev == 1.0:
                    if result["exceeds_brd_threshold"] or result["high_drawdown"]:
                        return False
        for scenario_name, severities in all_results.items():
            for sev, result in severities.items():
                if sev == 2.0 and result["max_drawdown"] < -0.20:
                    return False
        return True


# Default simulator instance
default_stress_test = StressTestSimulator(np.array([]))


def quick_stress_test(base_returns: np.ndarray, severities: List[float] = None,
                      n_weeks: int = 4) -> Dict:
    """Quick stress test without initializing full simulator."""
    simulator = StressTestSimulator(base_returns)
    return simulator.run_all_scenarios(severities=severities, n_weeks=n_weeks)


# Export for web app integration
__all__ = [
    'StressTestSimulator', 'default_stress_test', 'ScenarioType',
    'quick_stress_test'
]
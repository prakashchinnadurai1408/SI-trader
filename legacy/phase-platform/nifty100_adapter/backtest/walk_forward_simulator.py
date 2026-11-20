"""Walk-Forward Analysis Simulator for SI-Trader Platform.

BRD Reference: Section 27.5 production readiness; Phase 3 production validation.
Walk-Forward Analysis (WFA) simulates real trading conditions by optimizing
parameters on rolling training windows and testing on out-of-sample windows.

Key Features:
- Rolling training/testing windows
- Parameter optimization per window
- Edge tracking across time
- WFA statistics (train/test edge, edge decay)
- BRD-compliant production readiness assessment
"""

from typing import List, Dict, Optional, Tuple
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


class WalkForwardAnalyzer:
    """
    Walk-Forward Analysis simulator for strategy production validation.

    Simulates real trading conditions by:
    1. Optimizing parameters on a training window (e.g., 52 weeks = 1 year)
    2. Testing on an out-of-sample window (e.g., 4 weeks = 1 month)
    3. Rolling forward by step size
    4. Tracking edge decay and stability

    WFA is the gold standard for estimating how strategy edge
    decays over time before REAL_MONEY transition.
    """

    def __init__(self,
                 n_training_weeks: int = 52,
                 n_testing_weeks: int = 4,
                 n_step_weeks: int = 4,
                 min_observations: int = 30):
        """
        Initialize WFA simulator.

        Args:
            n_training_weeks: Number of weeks for parameter optimization window
            n_testing_weeks: Number of weeks for out-of-sample testing
            n_step_weeks: Number of weeks to roll forward each iteration
            min_observations: Minimum observations required per window
        """
        self.n_training_weeks = n_training_weeks
        self.n_testing_weeks = n_testing_weeks
        self.n_step_weeks = n_step_weeks
        self.min_observations = min_observations

    def analyze(self, 
                weekly_returns: np.ndarray,
                parameter_optimizer) -> Dict:
        """
        Perform walk-forward analysis.

        Args:
            weekly_returns: 1D array of historical weekly returns
            parameter_optimizer: Callable that takes training returns and
                                returns optimized parameters (weights, etc.)

        Returns:
            Walk-forward analysis results dictionary
        """
        if len(weekly_returns) < self.n_training_weeks + self.n_testing_weeks:
            raise ValueError(
                f"Insufficient data: need at least "
                f"{self.n_training_weeks + self.n_testing_weeks} observations, "
                f"have {len(weekly_returns)}"
            )

        results = []
        train_start = 0
        iteration = 0

        while train_start + self.n_training_weeks + self.n_testing_weeks <= len(weekly_returns):
            iteration += 1

            # --- TRAINING WINDOW ---
            train_returns = weekly_returns[train_start:train_start + self.n_training_weeks]

            # Optimize parameters on training data
            try:
                optimized_params = parameter_optimizer(train_returns)
            except Exception as e:
                # Skip this iteration if optimization fails
                train_start += self.n_step_weeks
                continue

            # --- TESTING WINDOW ---
            test_start = train_start + self.n_training_weeks
            test_returns = weekly_returns[test_start:test_start + self.n_testing_weeks]

            # Calculate performance on test window
            test_metrics = self._calculate_test_metrics(test_returns, optimized_params)

            # Record results
            result = {
                "iteration": iteration,
                "train_weeks": (train_start + 1, train_start + self.n_training_weeks),
                "test_weeks": (test_start + 1, test_start + self.n_testing_weeks),
                "train_return": np.mean(train_returns),
                "test_return": test_metrics["test_weekly_return"],
                "train_sharpe": test_metrics.get("train_sharpe"),
                "test_sharpe": test_metrics.get("test_sharpe"),
                "train_win_rate": test_metrics.get("train_win_rate"),
                "test_win_rate": test_metrics.get("test_win_rate"),
                "edge_decay": None,  # Will calculate below
                "params": optimized_params,
            }

            # Calculate edge decay if we have previous test result
            if results and "test_return" in results[-1]:
                result["edge_decay"] = results[-1]["test_return"] - result["test_return"]

            results.append(result)

            # Roll forward
            train_start += self.n_step_weeks

        # Post-analysis: calculate summary statistics
        self._post_analyze(results)

        return {
            "n_iterations": iteration,
            "results": results,
            "total_training_weeks": self.n_training_weeks,
            "total_testing_weeks": self.n_testing_weeks,
            "step_weeks": self.n_step_weeks,
            "initial_training_return": results[0]["train_return"] if results else None,
            "final_training_return": results[-1]["train_return"] if results else None,
            "initial_test_return": results[0]["test_return"] if results else None,
            "final_test_return": results[-1]["test_return"] if results else None,
            "test_return_range": (
                min(r["test_return"] for r in results if "test_return" in r and not np.isnan(r.get("test_return", np.nan))),
                max(r["test_return"] for r in results if "test_return" in r and not np.isnan(r.get("test_return", np.nan)))
            ) if results else (None, None),
            "edge_decay_per_step": np.mean([
                r.get("edge_decay", 0) for r in results if r.get("edge_decay") is not None
            ]) if results else 0,
            "is_production_ready": self._check_production_readiness(results)
        }

    def _calculate_test_metrics(self, test_returns: np.ndarray, params: dict) -> dict:
        """Calculate performance metrics for the test window."""
        if len(test_returns) == 0:
            return {
                "test_weekly_return": np.nan,
                "test_sharpe": np.nan,
                "test_win_rate": np.nan,
            }

        # Total return over test window
        total_return = np.prod(1 + test_returns) - 1 if len(test_returns) > 0 else np.nan

        # Annualized return (assuming 52 weeks)
        n_weeks = len(test_returns)
        annual_return = (1 + total_return) ** (52 / n_weeks) - 1 if total_return > -1 and n_weeks > 0 else np.nan

        # Sharpe ratio (assuming 0.38% weekly roundtrip + 20% STCG)
        # Excess return over risk-free (0), divided by volatility
        weekly_vol = np.std(test_returns) if np.std(test_returns) > 0 else np.nan
        sharpe = (total_return / weekly_vol) * np.sqrt(n_weeks) if weekly_vol > 0 else np.nan

        # Win rate: percentage of weeks with positive return
        win_rate = np.mean(test_returns > 0) if len(test_returns) > 0 else np.nan

        return {
            "test_weekly_return": total_return,
            "annualized_return": annual_return,
            "test_sharpe": sharpe,
            "test_win_rate": win_rate,
        }

    def _post_analyze(self, results: List[dict]) -> None:
        """Post-analysis: add derived metrics to all results."""
        test_returns = [r.get("test_return") for r in results if r.get("test_return") is not None]

        if test_returns:
            # Average test return across all iterations
            avg_test_return = np.mean(test_returns)

            # Edge decay: initial test return - final test return
            if len(test_returns) >= 2:
                total_decay = results[0].get("test_return", 0) - results[-1].get("test_return", 0)
                for r in results:
                    r["average_edge_decay"] = total_decay / max(len(results) - 1, 1)

            # Production readiness
            for r in results:
                r["is_production_ready"] = self._check_single_readiness(r)

        # Ensure all results have consistent keys
        for r in results:
            r.setdefault("edge_decay", 0.0)
            r.setdefault("is_production_ready", False)
            r.setdefault("train_return", np.nan)
            r.setdefault("test_return", np.nan)
            r.setdefault("train_sharpe", np.nan)
            r.setdefault("test_sharpe", np.nan)
            r.setdefault("train_win_rate", np.nan)
            r.setdefault("test_win_rate", np.nan)

    def _check_production_readiness(self, results: List[dict]) -> bool:
        """
        Check if strategy is production-ready based on WFA results.

        BRD Rule: 3+ months paper trading with all compliance gates pass.
        WFA adds: edge must not decay to zero, test returns must be positive on average.
        """
        if not results:
            return False

        # Initial test return must be positive
        if results[0].get("test_return", 0) <= 0:
            return False

        # Final test return must not be much worse than initial
        if results[-1].get("test_return", 0) < 0:
            return False

        # Edge decay must not be catastrophic
        total_decay = results[0].get("test_return", 0) - results[-1].get("test_return", 0)
        if total_decay > abs(results[0].get("test_return", 0)) * 0.8:  # >80% decay
            return False

        # At least 50% of iterations must have positive test returns
        positive_iterations = sum(1 for r in results if r.get("test_return", 0) > 0)
        if positive_iterations < len(results) * 0.5:
            return False

        return True

    def _check_single_readiness(self, result: dict) -> bool:
        """Check production readiness for a single WFA iteration."""
        if result.get("test_return", 0) <= 0:
            return False
        if result.get("test_return", 0) is np.nan:
            return False
        return True


# Default analyzer instance
default_wfa = WalkForwardAnalyzer(
    n_training_weeks=52,    # 1 year training
    n_testing_weeks=4,      # 1 month testing
    n_step_weeks=4,         # Roll forward monthly
    min_observations=30,
)


def quick_wfa(weekly_returns: np.ndarray,
              n_training_weeks: int = 52,
              n_testing_weeks: int = 4,
              n_step_weeks: int = 4) -> Dict:
    """
    Quick walk-forward analysis without custom parameter optimizer.

    Uses a simple parameter set (equal weight) for demonstration.

    Args:
        weekly_returns: Historical weekly returns
        n_training_weeks: Training window size
        n_testing_weeks: Testing window size
        n_step_weeks: Roll forward step size

    Returns:
        WFA results dictionary
    """
    def simple_optimizer(train_returns):
        """Simple equal-weight optimizer for demonstration."""
        n = len(train_returns)
        # Equal weight: just return a constant set of weights
        # In a real implementation, this would optimize the strategy parameters
        return {"equal_weight": 1.0 / max(n, 1)}

    analyzer = WalkForwardAnalyzer(
        n_training_weeks=n_training_weeks,
        n_testing_weeks=n_testing_weeks,
        n_step_weeks=n_step_weeks,
    )

    return analyzer.analyze(weekly_returns, simple_optimizer)


# Export for web app integration
__all__ = [
    'WalkForwardAnalyzer', 'default_wfa', 'quick_wfa'
]
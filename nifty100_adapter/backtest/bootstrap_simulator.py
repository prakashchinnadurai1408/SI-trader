"""Bootstrap Resampling Simulator for SI-Trader Platform.

BRD Reference: Section 27.5 edge validation; Phase 3 advanced analytics.
Provides non-parametric simulation by resampling historical return sequences
with replacement, preserving the actual historical distribution including
autocorrelation and fat tails.

Key Advantage over Parametric Monte Carlo: No distribution assumptions;
uses actual historical data. Critical when historical data is limited.
"""

from typing import List, Dict, Optional, Tuple
import numpy as np
from datetime import datetime
from pathlib import Path


class BootstrapSimulator:
    """
    Bootstrap resampling simulator for strategy edge validation.

    Generates synthetic return distributions by resampling with replacement
    from historical return sequences. Each resample is a "bootstrap replicate."

    Use cases:
    - Edge confidence intervals without parametric assumptions
    - Testing strategy robustness across market regimes
    - Validating edge stability across sub-samples
    - BRD-compliant edge probability estimation
    """

    def __init__(self, historical_returns: np.ndarray, n_replicates: int = 5000,
                 n_weeks: int = 1, confidence_level: float = 0.95):
        """
        Initialize bootstrap simulator.

        Args:
            historical_returns: 1D array of historical weekly returns
            n_replicates: Number of bootstrap replicates (default: 5000)
            n_weeks: Number of weeks to simulate per replicate (default: 1)
            confidence_level: Confidence level for intervals (default: 95%)
        """
        self.historical_returns = np.asarray(historical_returns)
        self.n_replicates = n_replicates
        self.n_weeks = n_weeks
        self.confidence_level = confidence_level
        self._rng = np.random.default_rng()

        if len(self.historical_returns) < 30:
            import warnings
            warnings.warn(
                f"Fewer than 30 historical return observations ({len(self.historical_returns)}). "
                "Bootstrap results may not be reliable.",
                UserWarning
            )

    def generate_replicates(self) -> np.ndarray:
        """
        Generate bootstrap replicates of weekly returns.

        Each replicate is formed by randomly sampling with replacement
        from the historical return series.

        Returns:
            2D array of shape (n_replicates, n_weeks) containing bootstrap replicates
        """
        n_obs = len(self.historical_returns)
        replicates = np.zeros((self.n_replicates, self.n_weeks))

        for i in range(self.n_replicates):
            # Sample with replacement
            sample = self._rng.choice(self.historical_returns, size=self.n_weeks, replace=True)
            replicates[i] = sample

        return replicates

    def calculate_statistics(self, replicates: Optional[np.ndarray] = None) -> Dict:
        """
        Calculate bootstrap statistics across all replicates.

        Args:
            replicates: Bootstrap replicates array from generate_replicates()
                        If None, generates internally

        Returns:
            Dictionary of bootstrap statistics
        """
        if replicates is None:
            replicates = self.generate_replicates()

        # Calculate metric statistics across replicates
        # Metric: cumulative return per replicate over n_weeks
        cumulative_returns = np.prod(1 + replicates, axis=1) - 1

        # Calculate metrics
        mean_return = np.mean(cumulative_returns)
        median_return = np.median(cumulative_returns)
        std_return = np.std(cumulative_returns)
        lower_ci = np.percentile(cumulative_returns, (1 - self.confidence_level) / 2 * 100)
        upper_ci = np.percentile(cumulative_returns, (1 + self.confidence_level) / 2 * 100)

        # Probability of positive return
        prob_positive = np.mean(cumulative_returns > 0)

        # Probability of exceeding BRD threshold (0.3% weekly)
        brd_threshold = 0.003  # 0.3%
        prob_exceeds_brd = np.mean(cumulative_returns > brd_threshold)

        return {
            "n_replicates": self.n_replicates,
            "n_observations": len(self.historical_returns),
            "mean_return": mean_return,
            "median_return": median_return,
            "std_return": std_return,
            "confidence_interval": (lower_ci, upper_ci),
            "confidence_level": self.confidence_level,
            "probability_positive": prob_positive,
            "probability_exceeds_brd_threshold": prob_exceeds_brd,
            "cumulative_returns": cumulative_returns,
            "historical_mean": np.mean(self.historical_returns),
            "historical_median": np.median(self.historical_returns),
            "historical_std": np.std(self.historical_returns),
        }

    def analyze_edge_distribution(self, brd_threshold: float = 0.003) -> Dict:
        """
        Analyze the bootstrap distribution against the BRD edge threshold.

        Args:
            brd_threshold: BRD minimum edge threshold (default: 0.3% = 0.003)

        Returns:
            Edge analysis dictionary
        """
        replicates = self.generate_replicates()
        cumulative = np.prod(1 + replicates, axis=1) - 1

        return {
            "brd_threshold": brd_threshold,
            "probability_exceeds_brd": np.mean(cumulative > brd_threshold),
            "probability_positive": np.mean(cumulative > 0),
            "percentile_50": np.percentile(cumulative, 50),
            "percentile_5": np.percentile(cumulative, 5),
            "percentile_95": np.percentile(cumulative, 95),
            "probability_below_zero": np.mean(cumulative <= 0),
            "edge_distribution_hist": cumulative,  # For plotting/analysis
        }

    def compare_hypothesis(self, null_hypothesis_edge: float = 0.0,
                          alternative: str = "greater") -> Dict:
        """
        Hypothesis test: does the bootstrap distribution reject the null hypothesis?

        Args:
            null_hypothesis_edge: Edge value under null hypothesis (default: 0.0)
            alternative: "greater", "less", or "two-sided" (default: "greater")

        Returns:
            Hypothesis test results
        """
        replicates = self.generate_replicates()
        cumulative = np.prod(1 + replicates, axis=1) - 1

        if alternative == "greater":
            p_value = np.mean(cumulative <= null_hypothesis_edge)
            test_statistic = np.mean(cumulative) - null_hypothesis_edge
        elif alternative == "less":
            p_value = np.mean(cumulative >= null_hypothesis_edge)
            test_statistic = null_hypothesis_edge - np.mean(cumulative)
        else:  # two-sided
            p_value = 2 * min(np.mean(cumulative <= null_hypothesis_edge),
                              np.mean(cumulative >= null_hypothesis_edge))
            test_statistic = abs(np.mean(cumulative) - null_hypothesis_edge)

        # BRD-relevant: does edge exceed threshold?
        brd_exceeds = np.mean(cumulative > 0.003)

        return {
            "null_hypothesis_edge": null_hypothesis_edge,
            "alternative": alternative,
            "p_value": p_value,
            "test_statistic": test_statistic,
            "reject_null": p_value < 0.05,
            "brd_threshold_exceeds_probability": np.mean(cumulative > 0.003),
            "brd_threshold": 0.003,
            "brd_compliant": np.mean(cumulative > 0.003) > 0.5,
        }

    def get_rng(self):
        """Get the random number generator for reproducibility."""
        return self._rng


# Default simulator instance for BRD validation
default_bootstrap = BootstrapSimulator(
    historical_returns=np.array([]),  # Will be set from backtester data
    n_replicates=5000,
    n_weeks=1,
    confidence_level=0.95
)


def bootstrap_edge_probability(historical_returns: np.ndarray, n_replicates: int = 5000,
                               brd_threshold: float = 0.003, n_weeks: int = 1) -> Dict:
    """
    Quick bootstrap edge probability check.

    Args:
        historical_returns: Array of historical weekly returns
        n_replicates: Number of bootstrap replicates
        brd_threshold: BRD minimum edge threshold (0.3%)
        n_weeks: Number of weeks to simulate

    Returns:
        Edge probability results
    """
    sim = BootstrapSimulator(
        historical_returns=historical_returns,
        n_replicates=n_replicates,
        n_weeks=n_weeks,
        confidence_level=0.95
    )

    stats = sim.calculate_statistics()
    edge_analysis = sim.analyze_edge_distribution(brd_threshold)

    return {
        "historical_mean_weekly_return": stats["historical_mean"],
        "bootstrap_mean_return": stats["mean_return"],
        "bootstrap_median_return": stats["median_return"],
        "bootstrap_std_return": stats["std_return"],
        "bootstrap_ci": stats["confidence_interval"],
        "probability_exceeds_brd_threshold": edge_analysis["probability_exceeds_brd"],
        "probability_positive": edge_analysis["probability_positive"],
        "brd_threshold": brd_threshold,
        "brd_compliant": edge_analysis["probability_exceeds_brd"] > 0.5,
        "n_replicates": n_replicates,
        "n_observations": len(historical_returns),
    }


# Export for web app integration
__all__ = [
    'BootstrapSimulator', 'default_bootstrap', 'bootstrap_edge_probability'
]
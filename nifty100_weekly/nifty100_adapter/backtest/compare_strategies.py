"""Compare an AI challenger to the frozen monthly baseline on identical data."""

import argparse
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from .gate_g1 import gate_g1
from .monthly_backtester import WEIGHTS
from .monthly_inputs import INPUTS
from ..strategy_builder import validate_weights


def load_report(folder, strategy):
    report = json.loads((folder / "report.json").read_text(encoding="utf-8-sig"))
    if report.get("strategy") != strategy:
        raise ValueError(f"Expected a {strategy} report.")
    weights = report["factor_weights"]
    if strategy == "monthly_baseline" and weights != WEIGHTS:
        raise ValueError("Baseline weights differ from the frozen scorecard.")
    if strategy == "monthly_challenger":
        validate_weights(weights)
    hashes = report["input_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != set(INPUTS) or any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()
    ):
        raise ValueError("Re-run the backtest to produce a complete input fingerprint.")
    equity = pd.read_csv(folder / "daily_equity.csv", index_col="date", parse_dates=["date"])[["equity", "benchmark"]]
    equity = equity.apply(pd.to_numeric, errors="raise")
    if (
        not isinstance(equity.index, pd.DatetimeIndex) or len(equity) < 2 or equity.index.hasnans
        or not equity.index.is_unique or not equity.index.is_monotonic_increasing
        or not np.isfinite(equity.to_numpy()).all() or not equity.gt(0).all().all()
        or equity["equity"].iloc[0] != report["starting_capital"]
    ):
        raise ValueError(f"{strategy} daily equity file is invalid.")
    return report, equity


def compare_runs(baseline_dir, challenger_dir):
    baseline, left = load_report(baseline_dir, "monthly_baseline")
    challenger, right = load_report(challenger_dir, "monthly_challenger")
    matched_fields = ("input_sha256", "start_month", "end_month", "starting_capital", "transaction_cost_model")
    if (
        any(baseline[key] != challenger[key] for key in matched_fields)
        or not left.index.equals(right.index)
        or not left["benchmark"].equals(right["benchmark"])
    ):
        raise ValueError("Use identical input files, holdout dates, benchmark, starting capital and cost assumptions.")
    months = pd.period_range(baseline["start_month"], baseline["end_month"], freq="M")
    if not len(months) or not left.index.to_period("M").unique().equals(months.insert(0, months[0] - 1)):
        raise ValueError("Daily equity dates do not match the declared holdout.")
    if left.groupby(left.index.to_period("M")).size().iloc[1:].lt(10).any():
        raise ValueError("Daily equity files must cover every test month.")
    base_roi = float(left["equity"].iloc[-1] / left["equity"].iloc[0] - 1)
    challenger_roi = float(right["equity"].iloc[-1] / right["equity"].iloc[0] - 1)
    relative = (challenger_roi - base_roi) / base_roi if base_roi > 1e-12 else None
    base_metrics = gate_g1(left, months, False)
    challenger_metrics = gate_g1(right, months, False)
    paired = gate_g1(pd.DataFrame({"equity": right["equity"], "benchmark": left["equity"]}), months, False)
    research = all(
        report["data_manifest"]["mode"] == "research"
        and report["data_manifest"].get("rules_frozen_before_test") is True
        for report in (baseline, challenger)
    )
    return {
        "status": "research_comparison" if research and len(months) >= 60 else "inconclusive",
        "months": len(months), "baseline_weights": WEIGHTS, "challenger_weights": challenger["factor_weights"],
        "baseline_total_roi_pct": base_roi * 100, "challenger_total_roi_pct": challenger_roi * 100,
        "roi_difference_pp": (challenger_roi - base_roi) * 100,
        "relative_roi_improvement_pct": relative * 100 if relative is not None else None,
        "doubled_baseline_roi_in_this_sample": relative >= 1 if relative is not None and research and len(months) >= 60 else None,
        "benchmark_total_roi_pct": float(left["benchmark"].iloc[-1] / left["benchmark"].iloc[0] - 1) * 100,
        "baseline_net_cagr_pct": base_metrics["net_cagr"] * 100,
        "challenger_net_cagr_pct": challenger_metrics["net_cagr"] * 100,
        "baseline_max_drawdown_pct": base_metrics["maximum_daily_drawdown"] * 100,
        "challenger_max_drawdown_pct": challenger_metrics["maximum_daily_drawdown"] * 100,
        "challenger_vs_baseline_36m_wins": paired["rolling_36m_wins"],
        "rolling_36m_windows": paired["rolling_36m_windows"],
        "warning": "A comparison is historical. The challenger cannot approve a pilot or live orders.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--challenger", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(compare_runs(args.baseline, args.challenger), indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Strategy comparison: {error}\n")


if __name__ == "__main__":
    main()

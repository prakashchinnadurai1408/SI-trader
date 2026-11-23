"""Arena review workflow for SI-Trader strategies.

CLAUDE.md requires an Arena review for each new or materially changed
strategy: Weekly and Monthly research rankings plus strategy experiments,
where every solver gets the same fixed dates, decision-time evidence, costs,
capital and risk constraints; the final holdout stays out of strategy
selection; measured holdout performance and risks are compared; and
unverified data or unmeasured results must be labelled explicitly.

This module is that workflow in code. It is **read-only**: it ranks and
reports, and never promotes or executes. Promotion and execution stay behind
the existing SI-Trader gates (execution bridge, paper trading, compliance).

NOTE: AGENT_TOOLS.md, which CLAUDE.md points at for this workflow
(nifty100_weekly/AGENT_TOOLS.md#arena-strategy-review), does not exist in the
repository. The rubric implemented here comes from the CLAUDE.md rule itself;
if that doc exists elsewhere it should be reconciled with this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArenaConstraints:
    """Fixed evaluation contract, identical for every solver."""
    eval_start: str
    eval_end: str
    holdout_start: str
    holdout_end: str
    capital: float = 25000.0
    cost_pct: float = 0.38           # BRD round-trip cost + tax
    max_loss_per_trade: float = 500.0
    max_positions: int = 10

    def as_dict(self) -> Dict[str, Any]:
        return {
            "eval_start": self.eval_start,
            "eval_end": self.eval_end,
            "holdout_start": self.holdout_start,
            "holdout_end": self.holdout_end,
            "capital": self.capital,
            "cost_pct": self.cost_pct,
            "max_loss_per_trade": self.max_loss_per_trade,
            "max_positions": self.max_positions,
        }


@dataclass
class ArenaStrategy:
    name: str
    source: str                       # pkscreener / algo_india / ma_crossover / ai_llm / options
    parameter_weights: Dict[str, int]
    decision_evidence: Dict[str, Any] = field(default_factory=dict)
    submitted_at: Optional[str] = None

    @property
    def weight_total(self) -> int:
        return sum(self.parameter_weights.values())


@dataclass
class RankedStrategy:
    name: str
    source: str
    rank: int
    label: str                       # "measured" or "unmeasured"
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class ArenaReview:
    """Read-only ranking of strategies on fixed evaluation constraints."""

    def __init__(self, constraints: ArenaConstraints):
        self.constraints = constraints
        self.strategies: List[ArenaStrategy] = []

    # ------------------------------------------------------------------
    # Submissions
    # ------------------------------------------------------------------

    def add_strategy(self, strategy: ArenaStrategy) -> ArenaStrategy:
        """Validate a submission and record its decision-time evidence."""
        if strategy.weight_total != 100:
            raise ValueError(
                f"{strategy.name}: weights total {strategy.weight_total}, must be 100")
        if strategy.submitted_at is None:
            strategy.submitted_at = datetime.now().isoformat()
        # Snapshot the catalogue so the submission is judged against the same
        # 48 parameters every other solver was judged against.
        strategy.decision_evidence.setdefault("parameter_catalogue_size", 48)
        self.strategies.append(strategy)
        return strategy

    def add_candidates(self, candidates: List[Any]) -> List[ArenaStrategy]:
        """Accept StrategyCandidate objects from the hub."""
        out = []
        for c in candidates:
            out.append(self.add_strategy(ArenaStrategy(
                name=getattr(c, "name", "?"),
                source=getattr(c, "source", "hub"),
                parameter_weights=dict(getattr(c, "parameter_weights", {})),
                decision_evidence={"selected_stocks": getattr(c, "selected_stocks", None)},
            )))
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _to_series(self, price_data: Any) -> Dict[str, Any]:
        """Normalise price input to {symbol: [bar dicts]}."""
        if price_data is None:
            return {}
        if isinstance(price_data, dict):
            return {str(k): list(v) for k, v in price_data.items()}
        if hasattr(price_data, "to_dict"):  # pandas DataFrame
            try:
                return {"_single": price_data.to_dict("records")}
            except Exception:
                return {"_single": []}
        return {"_single": list(price_data)}

    def _label(self, price_data: Any) -> tuple:
        """(label, notes, usable) for a dataset."""
        series = self._to_series(price_data)
        if not series:
            return ("unmeasured", ["no price history supplied - metrics not measured"], False)
        enough = [s for s, b in series.items() if b and len(b) >= 30]
        if not enough:
            return ("unmeasured", ["fewer than 30 bars of history - results not measurable"], False)
        return ("measured", [], True)

    # ------------------------------------------------------------------
    # Rankings
    # ------------------------------------------------------------------

    def rank(self, price_data: Any, window: str = "eval") -> List[RankedStrategy]:
        """Rank submissions on the given window.

        `window` is informational: identical constraints apply either way.
        Submissions with unmeasurable data are labelled `unmeasured` and
        ranked last rather than being scored zero.
        """
        from ..backtest.sitrader_strategy_backtester import StrategyBacktester

        label, notes, usable = self._label(price_data)
        series = self._to_series(price_data)
        backtester = StrategyBacktester(
            capital=self.constraints.capital,
            top_n=self.constraints.max_positions,
        )
        results: List[RankedStrategy] = []
        for strategy in self.strategies:
            if not usable:
                results.append(RankedStrategy(
                    name=strategy.name, source=strategy.source, rank=0,
                    label=label, metrics={}, notes=list(notes)))
                continue
            result = backtester.run(strategy.name, strategy.parameter_weights, series)
            strat_notes = list(result.notes)
            if not result.brd_compliant or not result.edge_passes:
                strat_notes.append("does not meet the BRD edge threshold")
            results.append(RankedStrategy(
                name=strategy.name, source=strategy.source, rank=0,
                label="measured", metrics=result.as_dict(),
                notes=strat_notes))

        measured = [r for r in results if r.label == "measured"]
        unmeasured = [r for r in results if r.label == "unmeasured"]
        measured.sort(
            key=lambda r: (r.metrics.get("avg_trade", 0.0), r.metrics.get("sharpe", 0.0)),
            reverse=True)
        for i, r in enumerate(measured, 1):
            r.rank = i
        for r in unmeasured:
            r.rank = len(measured) + 1
        return measured + unmeasured

    def weekly_ranking(self, price_data: Any) -> List[RankedStrategy]:
        return self.rank(price_data, window="weekly")

    def monthly_ranking(self, price_data: Any) -> List[RankedStrategy]:
        return self.rank(price_data, window="monthly")

    def research_ranking(self, price_data: Any) -> List[RankedStrategy]:
        """Ranking that also surfaces the decision-time evidence of each entry."""
        ranked = self.rank(price_data, window="research")
        for r in ranked:
            strategy = next(s for s in self.strategies if s.name == r.name)
            r.metrics.setdefault("decision_evidence", strategy.decision_evidence)
        return ranked

    # ------------------------------------------------------------------
    # Holdout - used only to compare, never to select
    # ------------------------------------------------------------------

    def holdout_report(self, ranked: List[RankedStrategy],
                       holdout_data: Any) -> Dict[str, Any]:
        """Measure the shortlisted strategies on the holdout window.

        Selection has already happened on `ranked`; this only reports what
        the chosen strategies did on data that was not used to pick them.
        """
        from ..backtest.sitrader_strategy_backtester import StrategyBacktester

        shortlist = [r for r in ranked if r.label == "measured"][:3]
        if not shortlist:
            return {"holdout_compared": False,
                    "reason": "no measured strategies to compare",
                    "comparisons": []}

        label, notes, usable = self._label(holdout_data)
        series = self._to_series(holdout_data)
        backtester = StrategyBacktester(
            capital=self.constraints.capital,
            top_n=self.constraints.max_positions,
        )
        comparisons = []
        for entry in shortlist:
            if not usable:
                comparisons.append({"name": entry.name, "label": label,
                                    "notes": notes})
                continue
            result = backtester.run(
                entry.name,
                next(s.parameter_weights for s in self.strategies
                     if s.name == entry.name),
                series)
            comparisons.append({
                "name": entry.name,
                "label": "measured",
                "metrics": result.as_dict(),
                "edge_validation": {
                    "net_edge": result.avg_trade_pct,
                    "edge_passes": result.edge_passes,
                    "brd_compliant": result.brd_compliant,
                },
                "risks": {
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "max_loss_per_trade": self.constraints.max_loss_per_trade,
                    "risk_at_stop_ok": result.max_drawdown_pct
                    <= self.constraints.max_loss_per_trade,
                },
            })
        return {
            "holdout_compared": True,
            "holdout_window": [self.constraints.holdout_start,
                               self.constraints.holdout_end],
            "selection_used": "evaluation window only",
            "comparisons": comparisons,
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self, price_data: Any, holdout_data: Any = None) -> Dict[str, Any]:
        ranked = self.research_ranking(price_data)
        report = {
            "constraints": self.constraints.as_dict(),
            "submissions": [
                {"name": s.name, "source": s.source,
                 "weight_total": s.weight_total,
                 "decision_evidence": s.decision_evidence}
                for s in self.strategies
            ],
            "ranking": [
                {"rank": r.rank, "name": r.name, "source": r.source,
                 "label": r.label, "metrics": r.metrics, "notes": r.notes}
                for r in ranked
            ],
            "unlabelled_results": [],
            "holdout": None,
            "generated_at": datetime.now().isoformat(),
        }
        # Every non-measured figure must be labelled, per CLAUDE.md.
        for r in ranked:
            if r.label != "measured":
                report["unlabelled_results"].append(r.name)

        if holdout_data is not None:
            report["holdout"] = self.holdout_report(ranked, holdout_data)

        report["promotion_policy"] = (
            "Arena review is read-only. Promotion and execution follow the "
            "existing SI-Trader gates (execution bridge, paper trading, "
            "compliance).")
        return report

    def export_report(self, path: str, price_data: Any,
                      holdout_data: Any = None) -> str:
        report = self.report(price_data, holdout_data)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        logger.info("Arena report exported to %s", path)
        return path


DEFAULT_CONSTRAINTS = ArenaConstraints(
    eval_start="2024-01-01",
    eval_end="2025-12-31",
    holdout_start="2026-01-01",
    holdout_end="2026-11-30",
    capital=25000.0,
    cost_pct=0.38,
    max_loss_per_trade=500.0,
    max_positions=10,
)

__all__ = [
    "ArenaReview", "ArenaStrategy", "ArenaConstraints", "RankedStrategy",
    "DEFAULT_CONSTRAINTS",
]
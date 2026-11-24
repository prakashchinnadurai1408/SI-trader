"""Durable, auditable run reports for SI-Trader.

Every evaluation, review, plan or execution this platform performs should
leave behind a machine-readable artefact rather than existing only as
output on a console. This module provides that:

    RunReport - the stable schema of one run (inputs, constraints, metrics,
                labels, holdout outcome, errors, started/finished times)
    ReportWriter - writes one JSON file per run under a records directory
                and appends a single-line index so runs are enumerable
                without scanning the directory

Design rules:
    - Reports are append-only. Nothing here mutates or deletes a prior run,
      so the record of what was measured, when, and under what constraints
      stays intact.
    - Unmeasured and unverified results are recorded as such in `labels`;
      a report never silently turns missing data into a number.
    - A report records the constraints it ran under, so two runs measured
      under different constraints are not comparable and say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import os
import uuid

import logging

logger = logging.getLogger(__name__)


@dataclass
class RunReport:
    """One durable record of a run."""
    run_id: str
    kind: str                       # arena / weekly / monthly / backtest / plan / execute
    started_at: str
    finished_at: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, Any] = field(default_factory=dict)
    holdout: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "constraints": self.constraints,
            "inputs": self.inputs,
            "metrics": self.metrics,
            "labels": self.labels,
            "holdout": self.holdout,
            "errors": self.errors,
            "artifacts": self.artifacts,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class ReportWriter:
    """Writes one JSON report per run and keeps an index.

    Directory layout:
        <records_dir>/<kind>/<run_id>.json     - the full report
        <records_dir>/<kind>/index.jsonl       - one summary line per run
    """

    INDEX_NAME = "index.jsonl"

    def __init__(self, records_dir: str = "reports"):
        self.records_dir = records_dir
        os.makedirs(self.records_dir, exist_ok=True)

    def _dir_for(self, kind: str) -> str:
        path = os.path.join(self.records_dir, kind)
        os.makedirs(path, exist_ok=True)
        return path

    def _index_path(self, kind: str) -> str:
        return os.path.join(self._dir_for(kind), self.INDEX_NAME)

    def emit(self, kind: str, payload: Dict[str, Any]) -> str:
        """Write a report and return the path written.

        `payload` may be either a RunReport.to_dict() or any dict; when it is
        a plain dict the writer fills the required envelope fields so every
        artefact on disk has the same shape.
        """
        run_id = payload.get("run_id") or uuid.uuid4().hex[:12]
        report = RunReport(
            run_id=run_id,
            kind=kind,
            started_at=payload.get("started_at") or datetime.now().isoformat(),
            finished_at=payload.get("finished_at") or datetime.now().isoformat(),
            constraints=payload.get("constraints", {}),
            inputs=payload.get("inputs", {}),
            metrics=payload.get("metrics", {}),
            labels=payload.get("labels", {}),
            holdout=payload.get("holdout"),
            errors=payload.get("errors", []),
            artifacts=payload.get("artifacts", []),
        )
        return self._write(report)

    def _write(self, report: RunReport) -> str:
        path = os.path.join(self._dir_for(report.kind), f"{report.run_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report.to_json())

        index = {
            "run_id": report.run_id,
            "kind": report.kind,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "labels": report.labels,
            "errors": len(report.errors),
            "artifacts": report.artifacts,
        }
        with open(self._index_path(report.kind), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(index, default=str) + "\n")

        return path

    def list_reports(self, kind: Optional[str] = None,
                     limit: int = 50) -> List[Dict[str, Any]]:
        """Enumerate runs from the index, newest last, without scanning files."""
        kinds = [kind] if kind else self._kinds()
        out: List[Dict[str, Any]] = []
        for k in kinds:
            index_path = self._index_path(k)
            if not os.path.exists(index_path):
                continue
            with open(index_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out[-limit:]

    def load_report(self, run_id: str, kind: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self._dir_for(kind), f"{run_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def _kinds(self) -> List[str]:
        try:
            return [d for d in os.listdir(self.records_dir)
                    if os.path.isdir(os.path.join(self.records_dir, d))]
        except OSError:
            return []


def write_run_report(kind: str, payload: Dict[str, Any],
                     records_dir: str = "reports") -> str:
    """Convenience helper: write one run report and return its path."""
    return ReportWriter(records_dir=records_dir).emit(kind, payload)


__all__ = [
    "RunReport", "ReportWriter", "write_run_report",
]
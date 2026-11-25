"""Observability for SI-Trader: durable, auditable run reports.

Every evaluation, review, plan or execution this platform performs should
leave behind a machine-readable artefact rather than existing only as
output on a console.

Design rules:
    - Reports are append-only. Nothing here mutates or deletes a prior run,
      so the record of what was measured, when, and under what constraints
      stays intact.
    - Unmeasured and unverified results are recorded as such in `labels`;
      a report never silently turns missing data into a number.
    - A report records the constraints it ran under, so two runs measured
      under different constraints are not comparable and say so.
"""

from .report_writer import RunReport, ReportWriter, write_run_report

__all__ = [
    "RunReport", "ReportWriter", "write_run_report",
]
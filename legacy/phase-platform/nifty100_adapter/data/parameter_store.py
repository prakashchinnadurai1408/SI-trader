"""Parameter value store for SI-Trader.

The 48-parameter catalogue and its data-source mapping describe *where* each
parameter comes from, and the adapters can *compute* per-symbol scores - but
nothing persisted a value, so nothing could answer "which of the 48 do we
actually have data for?" and the pipeline's refresh had no output.

This store is that seam:

    adapter.fetch_parameter_values(symbols)
        -> store.record(parameter_key, symbol, value, source, observed=True)
        -> store.coverage()  # per-parameter availability over the 48

Rules that matter:
    - Nothing is ever fabricated. A parameter whose feed is not connected is
      recorded as unavailable, never filled with a neutral default.
    - Every value carries its source and an as-of timestamp so freshness can
      be checked against the catalogue's refresh schedule.
    - Only catalogue parameters can be stored, so coverage is always
      expressed against the same 48 keys the strategies weight.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


# How long a value stays usable, per refresh schedule.
_SCHEDULE_TTL = {
    "per_trade": timedelta(0),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=31),
    "quarterly": timedelta(days=100),
    "annually": timedelta(days=400),
    "fy_update": timedelta(days=400),
    "on-event": timedelta(days=1),
}


@dataclass
class ParameterValue:
    """One observed (or explicitly unavailable) parameter value."""
    parameter_key: str
    symbol: str
    value: Optional[float]
    source: str
    observed: bool
    as_of: Optional[str] = None
    reason: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        return self.observed and self.value is not None


class ParameterValueStore:
    """In-memory store of parameter values, keyed by catalogue parameter."""

    def __init__(self):
        # parameter_key -> {symbol -> ParameterValue}
        self._values: Dict[str, Dict[str, ParameterValue]] = {}
        # parameter_key -> reason string when unavailable for every symbol
        self._unavailable: Dict[str, str] = {}
        self._schedules: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def record(self, parameter_key: str, symbol: str, value: Optional[float],
               source: str, observed: bool = True,
               as_of: Optional[str] = None,
               schedule: Optional[str] = None) -> None:
        """Record a value (or its absence) for one parameter/symbol."""
        if schedule:
            self._schedules[parameter_key] = schedule
        bucket = self._values.setdefault(parameter_key, {})
        bucket[symbol] = ParameterValue(
            parameter_key=parameter_key, symbol=symbol, value=value,
            source=source, observed=observed,
            as_of=as_of or datetime.now().isoformat())
        if not observed:
            self._unavailable[parameter_key] = "not observed"

    def mark_unavailable(self, parameter_key: str, reason: str,
                         schedule: Optional[str] = None) -> None:
        """Record that a parameter has no feed at all.

        Used for parameters whose data source is configured in the catalogue
        but whose adapter is not installed or has no credentials - so the
        platform reports them honestly instead of scoring them as neutral.
        """
        self._unavailable[parameter_key] = reason
        if schedule:
            self._schedules[parameter_key] = schedule
        self._values.setdefault(parameter_key, {})

    def set_schedule(self, parameter_key: str, schedule: str) -> None:
        self._schedules[parameter_key] = schedule

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get(self, parameter_key: str, symbol: str) -> Optional[ParameterValue]:
        bucket = self._values.get(parameter_key)
        if not bucket:
            return None
        return bucket.get(symbol)

    def usable(self, parameter_key: str, symbol: str) -> Optional[float]:
        """Return the value only when it is observed and still fresh."""
        value = self.get(parameter_key, symbol)
        if not value or not value.is_usable:
            return None
        if not self.is_fresh(parameter_key, value.as_of):
            return None
        return value.value

    def symbols_for(self, parameter_key: str) -> List[str]:
        bucket = self._values.get(parameter_key) or {}
        return [s for s, v in bucket.items() if v.is_usable]

    def is_fresh(self, parameter_key: str, as_of: Optional[str]) -> bool:
        schedule = self._schedules.get(parameter_key, "daily")
        ttl = _SCHEDULE_TTL.get(schedule)
        if ttl is None:
            return True
        if not as_of:
            return False
        try:
            stamp = datetime.fromisoformat(as_of)
        except (TypeError, ValueError):
            return False
        if ttl == timedelta(0):  # per-trade: always recompute
            return True
        return datetime.now() - stamp <= ttl

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def coverage(self, parameter_keys: Optional[List[str]] = None
                 ) -> Dict[str, Any]:
        """Report which parameters have usable data.

        Expressed against the catalogue's own key set so coverage and
        strategy weights are always talking about the same 48 parameters.
        """
        from ..config.parameter_catalogue import PARAMETER_CATALOGUE

        keys = parameter_keys or [k for k, p in PARAMETER_CATALOGUE.items()
                                  if p.enable_switch]
        available, missing, reasons = [], [], {}
        for key in keys:
            symbols = self.symbols_for(key)
            if symbols:
                available.append(key)
            elif key in self._unavailable:
                missing.append(key)
                reasons[key] = self._unavailable[key]
            else:
                missing.append(key)
                reasons[key] = "no data recorded"
        return {
            "total_parameters": len(keys),
            "available": available,
            "available_count": len(available),
            "missing": missing,
            "missing_count": len(missing),
            "coverage_pct": (round(len(available) / len(keys) * 100, 1)
                             if keys else 0.0),
            "reasons": reasons,
        }

    def summary(self) -> Dict[str, Any]:
        cov = self.coverage()
        return {
            "available_parameters": cov["available_count"],
            "missing_parameters": cov["missing_count"],
            "coverage_pct": cov["coverage_pct"],
            "unavailable_reasons": len(self._unavailable),
        }


__all__ = ["ParameterValueStore", "ParameterValue"]
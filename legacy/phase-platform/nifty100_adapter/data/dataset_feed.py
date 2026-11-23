"""Dataset feed: map caller-supplied datasets onto catalogue parameters.

The pipeline can derive 6 parameters from price history. The remaining 42 need
configured feeds (annual-report extracts, shareholding CSVs, court and rating
feeds, research notes). Those providers are not bundled - but the platform
must not be limited to the 6 it can derive, and must never invent the rest.

This adapter is the honest bridge: callers supply values keyed by the
catalogue's own parameter keys, and the feed records exactly what was given
with provenance. Anything not supplied is reported unavailable, so coverage
stays truthful.

    datasets = {
        "RELIANCE": {"f_score": 8, "altman_z_score": 3.4,
                    "promoter_holding_pct": 50.1},
        ...
    }

No field-name guessing happens here: an unrecognised key is ignored rather
than silently mapped onto a different parameter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


class DatasetFeed:
    """Adapter that exposes caller-supplied values as catalogue parameters."""

    SOURCE_NAME = "Caller-supplied dataset"

    def __init__(self, catalogue_keys: Optional[List[str]] = None):
        from ..config.parameter_catalogue import PARAMETER_CATALOGUE
        self.catalogue_keys = catalogue_keys or [
            k for k, p in PARAMETER_CATALOGUE.items() if p.enable_switch]
        # Per-parameter refresh schedule from the catalogue, so stored values
        # expire at the right cadence.
        self._schedules = {
            k: PARAMETER_CATALOGUE[k].refresh_schedule
            for k in self.catalogue_keys}

    def fetch_parameter_values(self, symbols: List[str],
                               datasets: Optional[Dict[str, Any]] = None,
                               **_: Any) -> Dict[str, Any]:
        """Return catalogue-keyed values from `datasets`.

        Args:
            symbols: symbols of interest (used only to report availability)
            datasets: {symbol: {parameter_key: value}}

        Returns the standard fetcher shape: parameters/observed/unavailable.
        """
        result: Dict[str, Any] = {
            "parameters": {},
            "source": self.SOURCE_NAME,
            "observed": [],
            "unavailable": [],
            "schedules": self._schedules,
        }

        datasets = datasets or {}
        supplied: Dict[str, Dict[str, float]] = {}

        for symbol in symbols or list(datasets):
            row = datasets.get(symbol) or {}
            for key, value in row.items():
                if key not in self._schedules:
                    logger.debug("dataset key not in catalogue: %s", key)
                    continue
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    logger.debug("non-numeric dataset value for %s/%s", symbol, key)
                    continue
                supplied.setdefault(key, {})[symbol] = numeric

        for key in self.catalogue_keys:
            per_symbol = supplied.get(key)
            if per_symbol:
                result["parameters"][key] = per_symbol
                result["observed"].append(key)
            else:
                result["unavailable"].append(key)

        return result

    __all__ = ["DatasetFeed"]
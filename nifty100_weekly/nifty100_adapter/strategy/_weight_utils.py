"""Shared weight-normalisation utilities for strategy adapters.

All strategy adapters express a strategy as parameter weights that MUST total
exactly 100 (BRD requirement). These helpers make that guarantee deterministic
regardless of rounding.
"""

from __future__ import annotations

from typing import Dict


def normalize_weights(weights: Dict[str, int], target: int = 100) -> Dict[str, int]:
    """Normalise a weight dict to exactly ``target`` using largest-remainder.

    Guarantees every key keeps at least weight 1 and the total equals target.
    """
    if not weights:
        raise ValueError("weights must not be empty")

    total = float(sum(weights.values()))
    if total <= 0:
        raise ValueError("weights must sum to a positive value")

    raw = {k: (v * target) / total for k, v in weights.items()}
    floors = {k: max(1, int(v)) for k, v in raw.items()}

    remainder = target - sum(floors.values())

    if remainder > 0:
        order = sorted(raw, key=lambda k: (raw[k] - int(raw[k]), raw[k]), reverse=True)
        i = 0
        while remainder > 0:
            floors[order[i % len(order)]] += 1
            remainder -= 1
            i += 1
    elif remainder < 0:
        while remainder < 0:
            biggest = max(floors, key=lambda k: floors[k])
            if floors[biggest] <= 1:
                break
            floors[biggest] -= 1
            remainder += 1

    if sum(floors.values()) != target:
        raise ValueError(
            f"normalize_weights failed to reach {target} "
            f"(got {sum(floors.values())})"
        )

    return floors


def apply_adjustments(
    base_weights: Dict[str, int],
    adjustments: Dict[str, int],
    target: int = 100,
) -> Dict[str, int]:
    """Apply signed adjustments to base weights, then normalise to target."""
    weights = dict(base_weights)
    for key, delta in adjustments.items():
        if key in weights:
            weights[key] = max(1, weights[key] + delta)
    return normalize_weights(weights, target)
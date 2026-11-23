"""Research package for SI-Trader.

Currently exposes the Arena review workflow required by CLAUDE.md.
"""

from .arena import (
    ArenaReview,
    ArenaStrategy,
    ArenaConstraints,
    RankedStrategy,
    DEFAULT_CONSTRAINTS,
)

__all__ = [
    "ArenaReview",
    "ArenaStrategy",
    "ArenaConstraints",
    "RankedStrategy",
    "DEFAULT_CONSTRAINTS",
]
"""Mozilla-style frecency ranking for history entries.

"Frecency" blends how *often* a page was visited with how *recently*, so the
address bar surfaces the handful of pages someone actually returns to instead
of whatever they happened to open last. The weighting is bucketed rather than
continuous: a page visited yesterday and one visited three days ago rank the
same, which keeps the suggestion list stable instead of reshuffling hourly.

This lives outside main.py so the bucket boundaries — the part that is easy to
get subtly wrong and impossible to notice — can be tested directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


__all__ = [
    "DEFAULT_WEIGHT",
    "RECENCY_BUCKETS",
    "frecency",
    "rank_entries",
]


SECONDS_PER_DAY = 86400.0

#: ``(maximum age in days, weight)`` pairs, applied in order. The first bucket
#: whose bound the entry's age falls within wins.
RECENCY_BUCKETS: tuple[tuple[float, int], ...] = (
    (4.0, 100),
    (14.0, 70),
    (31.0, 50),
    (90.0, 30),
)

#: Weight for anything older than the last bucket.
DEFAULT_WEIGHT = 10


def _coerce_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    # A NaN timestamp would poison every comparison it takes part in.
    return number if number == number else 0.0


def _coerce_visits(value: Any) -> int:
    try:
        visits = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, visits)


def recency_weight(age_days: float) -> int:
    """Return the bucket weight for an entry ``age_days`` old."""
    for bound, weight in RECENCY_BUCKETS:
        if age_days <= bound:
            return weight
    return DEFAULT_WEIGHT


def frecency(entry: dict[str, Any], now: float) -> float:
    """Score one history entry. Higher is more likely to be wanted.

    Missing, malformed, and future-dated timestamps are all treated as "just
    visited" rather than raising — history rows come off disk and one bad row
    must not break the address bar.
    """
    age_days = max(0.0, _coerce_float(now) - _coerce_float(entry.get("last_visit")))
    age_days /= SECONDS_PER_DAY
    return float(_coerce_visits(entry.get("visits")) * recency_weight(age_days))


def rank_entries(
    entries: Iterable[dict[str, Any]],
    now: float,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return ``entries`` best-first.

    Ties break on URL so an unchanged history always produces an identical
    suggestion list — otherwise the completer reorders itself under the user's
    cursor between two equal-scoring entries.
    """
    ordered = sorted(
        entries,
        key=lambda entry: (-frecency(entry, now), str(entry.get("url") or "")),
    )
    if limit is not None and limit >= 0:
        return ordered[:limit]
    return ordered

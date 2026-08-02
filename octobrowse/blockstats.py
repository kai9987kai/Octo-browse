"""Thread-safe counters for blocked requests and HTTPS upgrades.

Qt WebEngine calls ``interceptRequest`` on Chromium's IO thread while the Qt UI
thread reads the same counters to paint the status bar and the Site Trust
Center.  Plain ``dict``/``Counter`` objects cannot be iterated on one thread
while another mutates them: ``sum(d.values())`` or ``Counter.most_common()``
raises ``RuntimeError: dictionary changed size during iteration``.  Because the
UI reads happen inside Qt slots, and PyQt6 treats an unhandled exception in a
slot as fatal, that race can abort the whole browser.

Every accessor here takes a lock and returns a private copy, so callers can
never observe or alias live state.
"""

from __future__ import annotations

import threading
from collections import Counter


__all__ = ["BlockStats"]


class BlockStats:
    """Lock-guarded blocked-request tallies shared across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_domain: Counter[str] = Counter()
        self._by_first_party: dict[str, Counter[str]] = {}
        self._https_upgrades = 0

    def record(self, first_party_host: str, blocked_host: str) -> None:
        """Count one blocked request, optionally attributed to its first party."""

        blocked_host = (blocked_host or "").lower()
        if not blocked_host:
            return
        first_party_host = (first_party_host or "").lower()
        with self._lock:
            self._by_domain[blocked_host] += 1
            if first_party_host:
                site = self._by_first_party.get(first_party_host)
                if site is None:
                    site = Counter()
                    self._by_first_party[first_party_host] = site
                site[blocked_host] += 1

    def record_https_upgrade(self) -> None:
        with self._lock:
            self._https_upgrades += 1

    @property
    def https_upgrades(self) -> int:
        with self._lock:
            return self._https_upgrades

    def total(self) -> int:
        """Total blocked requests across every first party."""

        with self._lock:
            return sum(self._by_domain.values())

    def top_domains(self, limit: int = 8) -> list[tuple[str, int]]:
        """Return the busiest blocked hosts overall, highest count first."""

        if limit <= 0:
            return []
        with self._lock:
            snapshot = list(self._by_domain.items())
        snapshot.sort(key=lambda item: (-item[1], item[0]))
        return snapshot[:limit]

    def for_site(self, host: str) -> int:
        """Blocked requests attributed to ``host`` as the first party."""

        key = (host or "").lower()
        with self._lock:
            site = self._by_first_party.get(key)
            return sum(site.values()) if site is not None else 0

    def top_for_site(self, host: str, limit: int = 5) -> list[tuple[str, int]]:
        """Return the busiest blocked hosts for ``host``, highest count first.

        Ties break on hostname so the Trust Center does not reshuffle rows
        between two reads of identical data.
        """

        key = (host or "").lower()
        if limit <= 0:
            return []
        with self._lock:
            site = self._by_first_party.get(key)
            snapshot = list(site.items()) if site is not None else []
        snapshot.sort(key=lambda item: (-item[1], item[0]))
        return snapshot[:limit]

    def reset(self) -> None:
        with self._lock:
            self._by_domain.clear()
            self._by_first_party.clear()
            self._https_upgrades = 0

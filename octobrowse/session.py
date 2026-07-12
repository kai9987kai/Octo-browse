"""Pure helpers for versioned, backward-compatible browser sessions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


MAX_SESSION_TABS = 50
SESSION_VERSION = 2


def _clean_tabs(values: Any) -> list[tuple[int, dict[str, Any]]]:
    """Normalize persisted tab records and retain their source positions."""
    if not isinstance(values, list):
        return []

    tabs: list[tuple[int, dict[str, Any]]] = []
    for source_index, value in enumerate(values):
        if len(tabs) >= MAX_SESSION_TABS:
            break
        if isinstance(value, str):
            url = value.strip()
            title = ""
            pinned = False
        elif isinstance(value, dict):
            raw_url = value.get("url")
            if not isinstance(raw_url, str):
                continue
            url = raw_url.strip()
            raw_title = value.get("title", "")
            title = raw_title.strip() if isinstance(raw_title, str) else ""
            pinned = value.get("pinned") is True
        else:
            continue
        if not url:
            continue
        tabs.append((source_index, {"url": url, "title": title, "pinned": pinned}))
    return tabs


def _active_index(value: Any, tab_count: int) -> int:
    if not tab_count:
        return 0
    try:
        index = int(value)
    except (TypeError, ValueError, OverflowError):
        index = 0
    return min(max(0, index), tab_count - 1)


def _normalize_tabs(values: Any, active_index: Any) -> tuple[list[dict[str, Any]], int]:
    """Clean records and map the active source position onto the clean list."""
    if not isinstance(values, list):
        return [], 0
    source_active = _active_index(active_index, len(values))
    indexed_tabs = _clean_tabs(values)
    tabs = [tab for _source_index, tab in indexed_tabs]
    if not tabs:
        return [], 0
    mapped_active = 0
    for clean_index, (source_index, _tab) in enumerate(indexed_tabs):
        if source_index <= source_active:
            mapped_active = clean_index
        else:
            break
    return tabs, mapped_active


def make_session_snapshot(
    tabs: Iterable[str | dict[str, Any]], active_index: int = 0
) -> dict[str, Any]:
    """Create a normalized v2 snapshot from the current ordinary tabs."""
    if isinstance(tabs, (str, bytes, dict)):
        values: list[Any] = []
    else:
        try:
            values = list(tabs)
        except TypeError:
            values = []
    clean_tabs, clean_active = _normalize_tabs(values, active_index)
    return {
        "version": SESSION_VERSION,
        "tabs": clean_tabs,
        "active_index": clean_active,
    }


def normalize_session_snapshot(value: Any) -> dict[str, Any]:
    """Normalize legacy tab lists or a versioned snapshot to the v2 schema."""
    if isinstance(value, list):
        tabs = value
        active_index: Any = 0
    elif isinstance(value, dict):
        tabs = value.get("tabs", [])
        active_index = value.get("active_index", 0)
    else:
        tabs = []
        active_index = 0

    clean_tabs, clean_active = _normalize_tabs(tabs, active_index)
    return {
        "version": SESSION_VERSION,
        "tabs": clean_tabs,
        "active_index": clean_active,
    }


__all__ = ["MAX_SESSION_TABS", "make_session_snapshot", "normalize_session_snapshot"]

"""Versioned named-workspace records for OctoBrowse research sessions."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Iterable


MAX_WORKSPACES = 40
MAX_WORKSPACE_TABS = 50


def _clean_tabs(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    tabs: list[dict[str, str]] = []
    for value in values[:MAX_WORKSPACE_TABS]:
        if isinstance(value, str):
            url, title = value.strip(), ""
        elif isinstance(value, dict):
            url = str(value.get("url", "")).strip()
            title = str(value.get("title", "")).strip()
        else:
            continue
        if not url:
            continue
        tabs.append(
            {
                "url": url,
                "title": title[:240],
                "pinned": bool(value.get("pinned", False)) if isinstance(value, dict) else False,
            }
        )
    return tabs


def _identifier(name: str, created_at: float) -> str:
    digest = hashlib.sha256(f"{name}\0{created_at:.6f}".encode()).hexdigest()[:16]
    return f"workspace-{digest}"


def make_workspace(
    name: str,
    tabs: Iterable[dict[str, Any]],
    active_index: int = 0,
    *,
    now: float | None = None,
    identifier: str | None = None,
) -> dict[str, Any]:
    """Create a normalized, serializable named workspace."""
    clean_name = " ".join(str(name).split())[:80]
    if not clean_name:
        raise ValueError("Workspace name cannot be empty.")
    clean_tabs = _clean_tabs(list(tabs))
    if not clean_tabs:
        raise ValueError("A workspace needs at least one ordinary tab.")
    timestamp = float(time.time() if now is None else now)
    active = min(max(0, int(active_index)), len(clean_tabs) - 1)
    return {
        "version": 1,
        "id": str(identifier or _identifier(clean_name, timestamp)),
        "name": clean_name,
        "tabs": clean_tabs,
        "active_index": active,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def normalize_workspaces(values: Any) -> list[dict[str, Any]]:
    """Coerce persisted workspace data, dropping malformed entries safely."""
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for value in values[-MAX_WORKSPACES:]:
        if not isinstance(value, dict):
            continue
        name = " ".join(str(value.get("name", "")).split())[:80]
        tabs = _clean_tabs(value.get("tabs"))
        if not name or not tabs:
            continue
        try:
            created_at = float(value.get("created_at") or value.get("updated_at") or 0.0)
        except (TypeError, ValueError):
            created_at = 0.0
        try:
            updated_at = float(value.get("updated_at") or created_at)
        except (TypeError, ValueError):
            updated_at = created_at
        try:
            active_index = min(max(0, int(value.get("active_index", 0))), len(tabs) - 1)
        except (TypeError, ValueError):
            active_index = 0
        identifier = str(value.get("id") or _identifier(name, created_at))[:120]
        if identifier in seen_ids:
            identifier = _identifier(name, created_at + len(result) + 1)
        seen_ids.add(identifier)
        result.append(
            {
                "version": 1,
                "id": identifier,
                "name": name,
                "tabs": tabs,
                "active_index": active_index,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
    return result


def workspace_to_markdown(workspace: dict[str, Any]) -> str:
    """Export a workspace as portable Markdown without embedding HTML."""
    normalized = normalize_workspaces([workspace])
    if not normalized:
        raise ValueError("Invalid workspace.")
    item = normalized[0]
    lines = [f"# {item['name']}", "", f"Saved tabs: {len(item['tabs'])}", ""]
    for tab in item["tabs"]:
        title = (tab.get("title") or tab["url"]).replace("[", "\\[").replace("]", "\\]")
        url = tab["url"].replace(">", "%3E")
        lines.append(f"- [{title}](<{url}>)")
    lines.append("")
    return "\n".join(lines)

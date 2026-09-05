"""Versioned named-workspace records for OctoBrowse research sessions."""

from __future__ import annotations

import hashlib
import html
import math
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlsplit


MAX_WORKSPACES = 40
MAX_WORKSPACE_TABS = 50
MAX_WORKSPACE_URL_CHARS = 8_192
MAX_WORKSPACE_TIMESTAMP = 253_402_300_799.0
MAX_WORKSPACE_ID_CHARS = 120


def _single_line(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = "".join(
        "\ufffd" if 0xD800 <= ord(character) <= 0xDFFF else character if ord(character) >= 32 else " "
        for character in value
    )
    return " ".join(text.split())[:limit]


def _clean_tabs(values: Any, active_index: Any = 0) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(values, list):
        return [], 0
    try:
        source_active = min(max(0, int(active_index)), max(0, len(values) - 1))
    except (TypeError, ValueError, OverflowError):
        source_active = 0
    tabs: list[dict[str, Any]] = []
    clean_active = 0
    for source_index, value in enumerate(values):
        if len(tabs) >= MAX_WORKSPACE_TABS:
            break
        if isinstance(value, str):
            url, title = value.strip(), ""
        elif isinstance(value, dict):
            raw_url = value.get("url")
            url = raw_url.strip() if isinstance(raw_url, str) else ""
            title = _single_line(value.get("title"), 240)
        else:
            continue
        # Do not truncate a URL into a different destination or stringify nulls.
        if (
            not url
            or len(url) > MAX_WORKSPACE_URL_CHARS
            or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in url)
        ):
            continue
        if source_index <= source_active:
            clean_active = len(tabs)
        tabs.append(
            {
                "url": url,
                "title": title,
                "pinned": value.get("pinned") is True if isinstance(value, dict) else False,
            }
        )
    return tabs, clean_active


def _timestamp(value: Any, fallback: float) -> float:
    try:
        timestamp = float(value)
        if isinstance(value, bool) or not math.isfinite(timestamp) or not 0 <= timestamp <= MAX_WORKSPACE_TIMESTAMP:
            return fallback
        # The workspace manager uses localtime; its supported range is narrower
        # than datetime's on Windows and also depends on the local UTC offset.
        time.localtime(timestamp)
    except (TypeError, ValueError, OverflowError, OSError):
        return fallback
    return timestamp


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
    clean_name = _single_line(name, 80)
    if not clean_name:
        raise ValueError("Workspace name cannot be empty.")
    try:
        values = [] if isinstance(tabs, (str, bytes, dict)) else list(tabs)
    except TypeError:
        values = []
    clean_tabs, active = _clean_tabs(values, active_index)
    if not clean_tabs:
        raise ValueError("A workspace needs at least one ordinary tab.")
    timestamp = _timestamp(time.time() if now is None else now, -1.0)
    if timestamp < 0:
        raise ValueError("Workspace timestamp is outside the supported range.")
    return {
        "version": 1,
        "id": _single_line(identifier, MAX_WORKSPACE_ID_CHARS) or _identifier(clean_name, timestamp),
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
    retained_values = values[-MAX_WORKSPACES:]
    # Generated repairs must not steal an explicit ID from a later workspace.
    reserved_ids = {
        _single_line(value.get("id"), MAX_WORKSPACE_ID_CHARS)
        for value in retained_values
        if isinstance(value, dict)
    }
    for value in retained_values:
        if not isinstance(value, dict):
            continue
        name = _single_line(value.get("name"), 80)
        tabs, active_index = _clean_tabs(value.get("tabs"), value.get("active_index", 0))
        if not name or not tabs:
            continue
        created_at = _timestamp(value.get("created_at"), _timestamp(value.get("updated_at"), 0.0))
        updated_at = max(created_at, _timestamp(value.get("updated_at"), created_at))
        explicit_id = _single_line(value.get("id"), MAX_WORKSPACE_ID_CHARS)
        identifier = explicit_id or _identifier(name, created_at)
        if identifier in seen_ids or (not explicit_id and identifier in reserved_ids):
            base = identifier
            suffix_number = 2
            while True:
                suffix = f"-{suffix_number}"
                identifier = base[: MAX_WORKSPACE_ID_CHARS - len(suffix)] + suffix
                if identifier not in seen_ids and identifier not in reserved_ids:
                    break
                suffix_number += 1
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


def _escape_markdown(value: str) -> str:
    value = html.escape(value, quote=False).replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]", "!", "#"):
        value = value.replace(character, "\\" + character)
    return value


def _markdown_destination(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() in {"http", "https", "ftp"}:
            if not parsed.hostname:
                return ""
            # Accessing port also rejects invalid numeric ports.
            _ = parsed.port
        elif parsed.scheme.lower() != "file" or not parsed.path:
            return ""
    except ValueError:
        return ""
    return quote(url, safe=":/?#[]@!$&'()*+,;=%-._~").replace("&", "&amp;")


def workspace_to_markdown(workspace: dict[str, Any]) -> str:
    """Export a workspace as portable Markdown without embedding HTML."""
    normalized = normalize_workspaces([workspace])
    if not normalized:
        raise ValueError("Invalid workspace.")
    item = normalized[0]
    lines = [f"# {_escape_markdown(item['name'])}", "", f"Saved tabs: {len(item['tabs'])}", ""]
    for tab in item["tabs"]:
        title = _escape_markdown(tab.get("title") or tab["url"])
        url = _markdown_destination(tab["url"])
        if url:
            lines.append(f"- [{title}](<{url}>)")
        else:
            lines.append(f"- {title} — {_escape_markdown(tab['url'])}")
    lines.append("")
    return "\n".join(lines)

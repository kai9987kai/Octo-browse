"""Versioned research-note normalization and portable Markdown export."""

from __future__ import annotations

import hashlib
import html
import math
import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit


RESEARCH_NOTE_VERSION = 1
MAX_RESEARCH_NOTES = 500
MAX_NOTE_ID_CHARS = 120
MAX_NOTE_URL_CHARS = 4_096
MAX_NOTE_TITLE_CHARS = 500
MAX_NOTE_QUOTE_CHARS = 8_000
MAX_NOTE_BODY_CHARS = 12_000
MAX_NOTE_CONTENT_CHARS = 16_000
MAX_NOTE_KIND_CHARS = 32
MAX_WORKSPACE_TABS = 50
MAX_TIMESTAMP = 253_402_300_799.0

_UNSAFE_ID_RE = re.compile(r"[^A-Za-z0-9._:-]+")
_UNSAFE_KIND_RE = re.compile(r"[^a-z0-9._-]+")


def _single_line(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", " ").split())[:limit]


def _multiline(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    cleaned = "".join(
        character
        if character in {"\n", "\t"} or ord(character) >= 32
        else " "
        for character in value
    )
    return cleaned.strip()[:limit].rstrip()


def _kind(value: Any) -> str:
    cleaned = _single_line(value, MAX_NOTE_KIND_CHARS).casefold()
    cleaned = _UNSAFE_KIND_RE.sub("-", cleaned).strip("-._")
    return cleaned or "page"


def _clean_id(value: Any) -> str:
    cleaned = _single_line(value, MAX_NOTE_ID_CHARS)
    cleaned = _UNSAFE_ID_RE.sub("-", cleaned).strip("-")
    return cleaned[:MAX_NOTE_ID_CHARS]


def _requested_now(now: Any) -> float:
    timestamp = time.time() if now is None else float(now)
    if not math.isfinite(timestamp) or not 0 <= timestamp <= MAX_TIMESTAMP:
        raise ValueError("Research-note timestamp is outside the supported range.")
    return timestamp


def _timestamp(value: Any, fallback: float) -> float:
    try:
        timestamp = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    if not math.isfinite(timestamp) or not 0 <= timestamp <= MAX_TIMESTAMP:
        return fallback
    return timestamp


def _generated_id(
    *,
    url: str,
    title: str,
    quote: str,
    body: str,
    kind: str,
    created_at: float,
    salt: str = "",
) -> str:
    material = "\0".join(
        (url, title, quote, body, kind, f"{created_at:.6f}", salt)
    ).encode("utf-8")
    return "note-" + hashlib.sha256(material).hexdigest()[:20]


def _make_record(
    *,
    url: Any,
    title: Any,
    quote: Any,
    body: Any,
    kind: Any,
    created_at: float,
    updated_at: float,
    note_id: Any,
    id_salt: str = "",
) -> dict[str, Any]:
    clean_url = _single_line(url, MAX_NOTE_URL_CHARS)
    clean_title = _single_line(title, MAX_NOTE_TITLE_CHARS)
    clean_quote = _multiline(
        quote,
        max(0, min(MAX_NOTE_QUOTE_CHARS, MAX_NOTE_CONTENT_CHARS)),
    )
    remaining = max(0, MAX_NOTE_CONTENT_CHARS - len(clean_quote))
    clean_body = _multiline(body, min(MAX_NOTE_BODY_CHARS, remaining))
    if not clean_quote and not clean_body:
        raise ValueError("A research note needs quoted text or a note body.")
    clean_kind = _kind(kind)
    identifier = _clean_id(note_id) or _generated_id(
        url=clean_url,
        title=clean_title,
        quote=clean_quote,
        body=clean_body,
        kind=clean_kind,
        created_at=created_at,
        salt=id_salt,
    )
    return {
        "version": RESEARCH_NOTE_VERSION,
        "id": identifier,
        "url": clean_url,
        "title": clean_title,
        "quote": clean_quote,
        "body": clean_body,
        "kind": clean_kind,
        "created_at": created_at,
        "updated_at": max(created_at, updated_at),
    }


def make_research_note(
    url: str,
    title: str,
    quote: str,
    body: str,
    kind: str = "page",
    now: float | None = None,
    note_id: str | None = None,
) -> dict[str, Any]:
    """Create one bounded v1 research note."""
    timestamp = _requested_now(now)
    return _make_record(
        url=url,
        title=title,
        quote=quote,
        body=body,
        kind=kind,
        created_at=timestamp,
        updated_at=timestamp,
        note_id=note_id,
    )


def normalize_research_notes(
    values: Any, now: float | None = None
) -> list[dict[str, Any]]:
    """Upgrade legacy records and drop malformed entries without mutation."""
    if not isinstance(values, (list, tuple)):
        return []
    fallback_time = _requested_now(now)
    start = max(0, len(values) - MAX_RESEARCH_NOTES)
    result: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for source_index, value in enumerate(values[start:], start=start):
        if isinstance(value, Mapping):
            url = value.get("url", "")
            title = value.get("title", "")
            quote = value.get("quote", "")
            body = value.get("body", "")
            if not _multiline(body, MAX_NOTE_BODY_CHARS):
                body = value.get("note", "")
            kind = value.get("kind", "page")
            created_at = _timestamp(value.get("created_at"), fallback_time)
            updated_at = _timestamp(value.get("updated_at"), created_at)
            note_id = value.get("id", "")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            url, body = value[0], value[1]
            title = quote = note_id = ""
            kind = "page"
            created_at = updated_at = fallback_time
        else:
            continue

        try:
            record = _make_record(
                url=url,
                title=title,
                quote=quote,
                body=body,
                kind=kind,
                created_at=created_at,
                updated_at=updated_at,
                note_id=note_id,
                id_salt=str(source_index),
            )
        except ValueError:
            continue

        if record["id"] in used_ids:
            collision = 1
            while True:
                identifier = _generated_id(
                    url=record["url"],
                    title=record["title"],
                    quote=record["quote"],
                    body=record["body"],
                    kind=record["kind"],
                    created_at=record["created_at"],
                    salt=f"{source_index}:{collision}",
                )
                if identifier not in used_ids:
                    record["id"] = identifier
                    break
                collision += 1
        used_ids.add(record["id"])
        result.append(record)
    return result


def _escape_inline(value: str) -> str:
    value = html.escape(value, quote=False).replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]"):
        value = value.replace(character, "\\" + character)
    return value


def _safe_url(value: str) -> str:
    return (
        value.replace("<", "%3C")
        .replace(">", "%3E")
        .replace('"', "%22")
        .replace(" ", "%20")
    )


def _quote_block(value: str) -> str:
    escaped = html.escape(value, quote=False)
    return "\n".join(f"> {line}" if line else ">" for line in escaped.split("\n"))


def _body_markdown(value: str) -> str:
    # Retain useful Markdown while preventing raw HTML from being embedded.
    return html.escape(value, quote=False)


def _iso_timestamp(value: float) -> str:
    rendered = datetime.fromtimestamp(value, timezone.utc).isoformat(
        timespec="seconds"
    )
    return rendered.replace("+00:00", "Z")


def _render_note(note: Mapping[str, Any], heading_level: int) -> list[str]:
    title = _escape_inline(str(note.get("title") or "Research note"))
    heading = "#" * heading_level
    section = "#" * min(6, heading_level + 1)
    lines = [
        f"{heading} {title}",
        "",
        f"- Type: `{_escape_inline(str(note['kind']))}`",
        f"- Created: {_iso_timestamp(float(note['created_at']))}",
        f"- Updated: {_iso_timestamp(float(note['updated_at']))}",
    ]
    url = str(note.get("url") or "")
    if url:
        lines.append(f"- Source: [{_escape_inline(url)}](<{_safe_url(url)}>)")
    quote = str(note.get("quote") or "")
    if quote:
        lines.extend(
            [
                "",
                f"{section} Quoted text",
                "",
                _quote_block(quote),
            ]
        )
    body = str(note.get("body") or "")
    if body:
        lines.extend(
            [
                "",
                f"{section} Notes",
                "",
                _body_markdown(body),
            ]
        )
    return lines


def research_note_to_markdown(note: Any) -> str:
    """Render a normalized or legacy note as portable, bounded Markdown."""
    normalized = normalize_research_notes([note], now=0.0)
    if not normalized:
        raise ValueError("Invalid research note.")
    return "\n".join(_render_note(normalized[0], 1)) + "\n"


def _canonical_url(value: str) -> str:
    value = _single_line(value, MAX_NOTE_URL_CHARS)
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme:
        return value
    scheme = parsed.scheme.casefold()
    netloc = parsed.netloc.casefold()
    if (scheme == "http" and netloc.endswith(":80")) or (
        scheme == "https" and netloc.endswith(":443")
    ):
        netloc = netloc.rsplit(":", 1)[0]
    path = parsed.path or ("/" if scheme in {"http", "https"} else "")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _workspace_tabs(workspace: Any) -> tuple[str, list[dict[str, str]]]:
    if not isinstance(workspace, Mapping):
        raise ValueError("Invalid workspace.")
    name = _single_line(workspace.get("name"), 80)
    raw_tabs = workspace.get("tabs")
    if not name or not isinstance(raw_tabs, (list, tuple)):
        raise ValueError("Invalid workspace.")
    tabs: list[dict[str, str]] = []
    for value in raw_tabs[:MAX_WORKSPACE_TABS]:
        if not isinstance(value, Mapping):
            continue
        url = _single_line(value.get("url"), MAX_NOTE_URL_CHARS)
        if not url:
            continue
        tabs.append(
            {
                "url": url,
                "title": _single_line(value.get("title"), MAX_NOTE_TITLE_CHARS),
            }
        )
    if not tabs:
        raise ValueError("Invalid workspace.")
    return name, tabs


def workspace_research_to_markdown(workspace: Any, notes: Any) -> str:
    """Export workspace tabs plus research notes whose source URL matches."""
    name, tabs = _workspace_tabs(workspace)
    tab_urls = {_canonical_url(tab["url"]) for tab in tabs}
    matching_notes = [
        note
        for note in normalize_research_notes(notes, now=0.0)
        if note["url"] and _canonical_url(note["url"]) in tab_urls
    ]

    lines = [
        f"# {_escape_inline(name)}",
        "",
        f"Saved tabs: {len(tabs)}",
        "",
        "## Tabs",
        "",
    ]
    for tab in tabs:
        title = _escape_inline(tab["title"] or tab["url"])
        lines.append(f"- [{title}](<{_safe_url(tab['url'])}>)")
    lines.extend(["", "## Research notes", ""])
    if not matching_notes:
        lines.append("_No research notes match this workspace._")
    else:
        for index, note in enumerate(matching_notes):
            if index:
                lines.extend(["", "---", ""])
            lines.extend(_render_note(note, 3))
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MAX_NOTE_BODY_CHARS",
    "MAX_NOTE_CONTENT_CHARS",
    "MAX_NOTE_QUOTE_CHARS",
    "MAX_NOTE_TITLE_CHARS",
    "MAX_NOTE_URL_CHARS",
    "MAX_RESEARCH_NOTES",
    "RESEARCH_NOTE_VERSION",
    "make_research_note",
    "normalize_research_notes",
    "research_note_to_markdown",
    "workspace_research_to_markdown",
]

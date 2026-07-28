"""Pure-Python SQLite index for OctoBrowse's unified library search."""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


MAX_LIBRARY_RECORDS = 5_000
MAX_KIND_CHARS = 32
MAX_TITLE_CHARS = 500
MAX_URL_CHARS = 4_096
MAX_INDEXED_TEXT_CHARS = 12_000
MAX_SOURCE_ID_CHARS = 256
MAX_QUERY_CHARS = 256
MAX_QUERY_TERMS = 16
MAX_QUERY_TERM_CHARS = 64
MAX_SEARCH_RESULTS = 100
MAX_RESULT_SNIPPET_CHARS = 240

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class LibraryRecord:
    """Normalized record accepted by :class:`LibraryIndex`."""

    kind: str
    title: str
    url: str = ""
    snippet: str = ""
    source_id: str = ""

    @property
    def record_type(self) -> str:
        return self.kind


@dataclass(frozen=True, slots=True)
class LibrarySearchResult:
    """Typed result returned to the browser UI."""

    kind: str
    title: str
    url: str
    snippet: str
    source_id: str = ""

    @property
    def record_type(self) -> str:
        return self.kind


def _clean_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", " ").split())[:limit]


def _clean_source_id(value: Any) -> str:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return _clean_text(str(value), MAX_SOURCE_ID_CHARS)
    return ""


def _iter_values(values: Any) -> Iterable[Any]:
    if values is None or isinstance(values, (str, bytes, Mapping)):
        return ()
    try:
        return iter(values)
    except TypeError:
        return ()


def _record(
    kind: str,
    title: Any,
    *,
    url: Any = "",
    snippet: Any = "",
    source_id: Any = "",
) -> LibraryRecord | None:
    clean_kind = _clean_text(kind, MAX_KIND_CHARS)
    clean_url = _clean_text(url, MAX_URL_CHARS)
    clean_title = _clean_text(title, MAX_TITLE_CHARS) or clean_url[:MAX_TITLE_CHARS]
    if not clean_kind or not clean_title:
        return None
    return LibraryRecord(
        kind=clean_kind,
        title=clean_title,
        url=clean_url,
        snippet=_clean_text(snippet, MAX_INDEXED_TEXT_CHARS),
        source_id=_clean_source_id(source_id),
    )


def _mapping_record(value: Mapping[str, Any], fallback_kind: str = "") -> LibraryRecord | None:
    return _record(
        _clean_text(value.get("kind"), MAX_KIND_CHARS) or fallback_kind,
        value.get("title"),
        url=value.get("url"),
        snippet=value.get("snippet", value.get("text", "")),
        source_id=value.get(
            "source_id",
            value.get("workspace_id", value.get("tab_index", "")),
        ),
    )


def _normalize_record(value: Any) -> LibraryRecord | None:
    if isinstance(value, LibraryRecord):
        return _record(
            value.kind,
            value.title,
            url=value.url,
            snippet=value.snippet,
            source_id=value.source_id,
        )
    if isinstance(value, Mapping):
        return _mapping_record(value)
    return None


def build_library_records(
    *,
    tabs: Any = (),
    history: Any = (),
    bookmarks: Any = (),
    reading: Any = (),
    reading_list: Any = (),
    notes: Any = (),
    todos: Any = (),
    workspaces: Any = (),
) -> tuple[LibraryRecord, ...]:
    """Normalize all browser collections into a bounded record sequence."""
    records: list[LibraryRecord] = []

    def append(record: LibraryRecord | None) -> bool:
        if len(records) >= MAX_LIBRARY_RECORDS:
            return False
        if record is not None:
            records.append(record)
        return len(records) < MAX_LIBRARY_RECORDS

    for index, value in enumerate(_iter_values(tabs)):
        if len(records) >= MAX_LIBRARY_RECORDS:
            break
        if not isinstance(value, Mapping):
            continue
        append(
            _record(
                "Tab",
                value.get("title"),
                url=value.get("url"),
                source_id=value.get("tab_index", index),
            )
        )

    for value in _iter_values(history):
        if len(records) >= MAX_LIBRARY_RECORDS:
            break
        if not isinstance(value, Mapping):
            continue
        append(
            _record(
                "History",
                value.get("title"),
                url=value.get("url"),
                source_id=value.get("url"),
            )
        )

    for kind, values in (
        ("Bookmark", bookmarks),
        ("Reading", reading),
        ("Reading", reading_list),
    ):
        for value in _iter_values(values):
            if len(records) >= MAX_LIBRARY_RECORDS:
                break
            if isinstance(value, Mapping):
                append(_mapping_record(value, kind))
            else:
                append(_record(kind, value, url=value, source_id=value))

    for value in _iter_values(notes):
        if len(records) >= MAX_LIBRARY_RECORDS:
            break
        if not isinstance(value, Mapping):
            continue
        note = _clean_text(
            value.get("note", value.get("text", "")),
            MAX_INDEXED_TEXT_CHARS,
        )
        if not note:
            continue
        append(
            _record(
                "Note",
                note,
                url=value.get("url"),
                snippet=note,
                source_id=value.get("id", value.get("url", "")),
            )
        )

    for value in _iter_values(todos):
        if len(records) >= MAX_LIBRARY_RECORDS:
            break
        if isinstance(value, Mapping):
            text = value.get("title", value.get("text", ""))
            append(
                _record(
                    "Task",
                    text,
                    snippet=text,
                    source_id=value.get("id", ""),
                )
            )
        else:
            append(_record("Task", value, snippet=value))

    for value in _iter_values(workspaces):
        if len(records) >= MAX_LIBRARY_RECORDS:
            break
        if not isinstance(value, Mapping):
            continue
        tab_parts: list[str] = []
        for tab in _iter_values(value.get("tabs")):
            if not isinstance(tab, Mapping):
                continue
            title = _clean_text(tab.get("title"), MAX_TITLE_CHARS)
            url = _clean_text(tab.get("url"), MAX_URL_CHARS)
            if title or url:
                tab_parts.append(" ".join(part for part in (title, url) if part))
            if sum(len(part) for part in tab_parts) >= MAX_INDEXED_TEXT_CHARS:
                break
        append(
            _record(
                "Workspace",
                value.get("name"),
                snippet=" | ".join(tab_parts),
                source_id=value.get("id", ""),
            )
        )
    return tuple(records)


def _query_tokens(query: Any) -> tuple[str, tuple[str, ...]]:
    if not isinstance(query, str):
        return "", ()
    clean_query = " ".join(query[:MAX_QUERY_CHARS].split()).casefold()
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(clean_query):
        token = match.group(0)[:MAX_QUERY_TERM_CHARS]
        if token and token not in seen:
            tokens.append(token)
            seen.add(token)
        if len(tokens) >= MAX_QUERY_TERMS:
            break
    return " ".join(tokens), tuple(tokens)


def _fts_expression(tokens: tuple[str, ...]) -> str:
    # Tokens come from _WORD_RE, but quoting keeps this safe if that tokenizer
    # changes later. A trailing star asks FTS5 for word-prefix candidates.
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens)


def _words(value: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _WORD_RE.finditer(value.casefold()))


def _row_matches_tokens(row: sqlite3.Row, tokens: tuple[str, ...]) -> bool:
    words: list[str] = []
    for field in ("kind", "title", "url", "snippet", "source_id"):
        words.extend(_words(str(row[field])))
    return all(any(word.startswith(token) for word in words) for token in tokens)


def _match_quality(
    row: sqlite3.Row, query_phrase: str, tokens: tuple[str, ...]
) -> tuple[int, int]:
    title_phrase = " ".join(_words(str(row["title"])))
    url_phrase = " ".join(_words(str(row["url"])))
    if title_phrase == query_phrase:
        return 0, 0
    if url_phrase == query_phrase:
        return 0, 1
    if title_phrase.startswith(query_phrase):
        return 1, 0
    if url_phrase.startswith(query_phrase):
        return 1, 1

    title_words = _words(str(row["title"]))
    url_words = _words(str(row["url"]))
    if all(any(word.startswith(token) for word in title_words) for token in tokens):
        return 2, 0
    if all(any(word.startswith(token) for word in url_words) for token in tokens):
        return 2, 1
    return 3, 0


def _display_snippet(text: str, tokens: tuple[str, ...]) -> str:
    text = _clean_text(text, MAX_INDEXED_TEXT_CHARS)
    if len(text) <= MAX_RESULT_SNIPPET_CHARS:
        return text
    lowered = text.casefold()
    positions = [lowered.find(token) for token in tokens]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - MAX_RESULT_SNIPPET_CHARS // 3)
    prefix = start > 0
    suffix = True
    marker_chars = (3 if prefix else 0) + (3 if suffix else 0)
    content_budget = max(1, MAX_RESULT_SNIPPET_CHARS - marker_chars)
    end = min(len(text), start + content_budget)
    if end == len(text):
        suffix = False
        marker_chars = 3 if prefix else 0
        content_budget = max(1, MAX_RESULT_SNIPPET_CHARS - marker_chars)
        start = max(0, len(text) - content_budget)
    excerpt = text[start:end].strip()
    return ("..." if prefix else "") + excerpt + ("..." if suffix else "")


class LibraryIndex:
    """Transactional SQLite search index with an automatic LIKE fallback."""

    def __init__(
        self,
        path: str | os.PathLike[str] = ":memory:",
        *,
        enable_fts: bool = True,
    ) -> None:
        self.path = path
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._fts_enabled = False
        self._create_base_schema()
        if enable_fts:
            self._enable_fts()

    @property
    def fts_enabled(self) -> bool:
        return self._fts_enabled

    def _create_base_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS library_records (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                snippet TEXT NOT NULL,
                source_id TEXT NOT NULL,
                sort_order INTEGER NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS library_records_sort "
            "ON library_records(sort_order)"
        )
        self._connection.commit()

    def _enable_fts(self) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS library_records_fts
                    USING fts5(
                        kind,
                        title,
                        url,
                        snippet,
                        source_id,
                        tokenize = 'unicode61 remove_diacritics 2'
                    )
                    """
                )
                # A previous run may deliberately have used LIKE-only mode.
                # Refreshing here prevents a persisted FTS table going stale.
                self._connection.execute("DELETE FROM library_records_fts")
                self._connection.execute(
                    """
                    INSERT INTO library_records_fts(
                        rowid, kind, title, url, snippet, source_id
                    )
                    SELECT id, kind, title, url, snippet, source_id
                    FROM library_records
                    """
                )
        except sqlite3.OperationalError:
            self._connection.rollback()
            self._fts_enabled = False
        else:
            self._fts_enabled = True

    def rebuild(
        self,
        records: Iterable[LibraryRecord | Mapping[str, Any]] | None = None,
        *,
        tabs: Any = (),
        history: Any = (),
        bookmarks: Any = (),
        reading: Any = (),
        reading_list: Any = (),
        notes: Any = (),
        todos: Any = (),
        workspaces: Any = (),
    ) -> int:
        """Atomically replace the index with bounded, normalized records."""
        normalized: list[LibraryRecord] = []
        if records is not None:
            for value in records:
                if len(normalized) >= MAX_LIBRARY_RECORDS:
                    break
                record = _normalize_record(value)
                if record is not None:
                    normalized.append(record)

        if len(normalized) < MAX_LIBRARY_RECORDS:
            source_records = build_library_records(
                tabs=tabs,
                history=history,
                bookmarks=bookmarks,
                reading=reading,
                reading_list=reading_list,
                notes=notes,
                todos=todos,
                workspaces=workspaces,
            )
            normalized.extend(
                source_records[: MAX_LIBRARY_RECORDS - len(normalized)]
            )

        rows = [
            (
                index + 1,
                record.kind,
                record.title,
                record.url,
                record.snippet,
                record.source_id,
                index,
            )
            for index, record in enumerate(normalized)
        ]
        with self._connection:
            if self._fts_enabled:
                self._connection.execute("DELETE FROM library_records_fts")
            self._connection.execute("DELETE FROM library_records")
            self._connection.executemany(
                """
                INSERT INTO library_records(
                    id, kind, title, url, snippet, source_id, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            if self._fts_enabled:
                self._connection.executemany(
                    """
                    INSERT INTO library_records_fts(
                        rowid, kind, title, url, snippet, source_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [row[:6] for row in rows],
                )
        return len(rows)

    def _all_rows(self) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                """
                SELECT id, kind, title, url, snippet, source_id, sort_order
                FROM library_records
                ORDER BY sort_order, id
                """
            )
        )

    def _fts_rows(self, tokens: tuple[str, ...]) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                """
                SELECT r.id, r.kind, r.title, r.url, r.snippet,
                       r.source_id, r.sort_order
                FROM library_records_fts
                JOIN library_records AS r
                  ON r.id = library_records_fts.rowid
                WHERE library_records_fts MATCH ?
                """,
                (_fts_expression(tokens),),
            )
        )

    def _like_rows(self, tokens: tuple[str, ...]) -> list[sqlite3.Row]:
        clauses: list[str] = []
        parameters: list[str] = []
        for token in tokens:
            clauses.append(
                "("
                "kind LIKE ? OR title LIKE ? OR url LIKE ? OR "
                "snippet LIKE ? OR source_id LIKE ?"
                ")"
            )
            pattern = f"%{token}%"
            parameters.extend([pattern] * 5)
        query = (
            "SELECT id, kind, title, url, snippet, source_id, sort_order "
            "FROM library_records WHERE "
            + " AND ".join(clauses)
        )
        return list(self._connection.execute(query, parameters))

    def search(self, query: Any, limit: int = 50) -> tuple[LibrarySearchResult, ...]:
        """Return deterministic exact/prefix-ranked results without raw FTS syntax."""
        try:
            result_limit = int(limit)
        except (TypeError, ValueError, OverflowError):
            result_limit = 50
        if result_limit <= 0:
            return ()
        result_limit = min(result_limit, MAX_SEARCH_RESULTS)

        query_phrase, tokens = _query_tokens(query)
        if not tokens:
            if isinstance(query, str) and query.strip():
                return ()
            rows = self._all_rows()[:result_limit]
        else:
            if self._fts_enabled:
                try:
                    rows = self._fts_rows(tokens)
                except sqlite3.OperationalError:
                    self._fts_enabled = False
                    rows = self._like_rows(tokens)
            else:
                rows = self._like_rows(tokens)
            rows = [row for row in rows if _row_matches_tokens(row, tokens)]
            rows.sort(
                key=lambda row: (
                    _match_quality(row, query_phrase, tokens),
                    int(row["sort_order"]),
                    int(row["id"]),
                )
            )
            rows = rows[:result_limit]

        return tuple(
            LibrarySearchResult(
                kind=str(row["kind"]),
                title=str(row["title"]),
                url=str(row["url"]),
                snippet=_display_snippet(str(row["snippet"]), tokens),
                source_id=str(row["source_id"]),
            )
            for row in rows
        )

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> LibraryIndex:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


__all__ = [
    "LibraryIndex",
    "LibraryRecord",
    "LibrarySearchResult",
    "MAX_INDEXED_TEXT_CHARS",
    "MAX_LIBRARY_RECORDS",
    "MAX_QUERY_CHARS",
    "MAX_QUERY_TERMS",
    "MAX_RESULT_SNIPPET_CHARS",
    "MAX_SEARCH_RESULTS",
    "MAX_TITLE_CHARS",
    "MAX_URL_CHARS",
    "build_library_records",
]

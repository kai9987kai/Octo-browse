"""Bounded checks that saved quotations still occur in extracted source text.

These checks establish text presence only. They do not establish that a source
is accurate, that it supports a claim, or that its contents are unchanged.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .quote_anchor import CONTEXT_CHARS, QuoteAnchor
from .readability import MAX_READABLE_CHARS


MAX_QUOTE_CHARS = 8_000
MAX_SOURCE_URL_CHARS = 8_192
MAX_EXCERPT_CHARS = 480
MAX_QUOTE_CHECKS = 100
_SPACE_RE = re.compile(r"\s+")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True, slots=True)
class QuoteCheck:
    """An observation about a full quote in the supplied page text."""

    status: str
    candidates: int = 0
    excerpt: str = ""
    message: str = ""
    matched_text: str = ""


@dataclass(frozen=True, slots=True)
class _PreparedText:
    text: str
    folded: str
    starts: list[int]
    ends: list[int]


def _fold(value: str) -> str:
    return _SPACE_RE.sub(" ", value)


def _fold_with_spans(text: str) -> tuple[str, list[int], list[int]]:
    """Collapse whitespace while retaining each character's original range."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for index, character in enumerate(text):
        if character.isspace():
            if characters and characters[-1] == " ":
                ends[-1] = index + 1
                continue
            character = " "
        characters.append(character)
        starts.append(index)
        ends.append(index + 1)
    return "".join(characters), starts, ends


def _prepare_text(text: str) -> _PreparedText:
    bounded = text[:MAX_READABLE_CHARS] if isinstance(text, str) else ""
    folded, starts, ends = _fold_with_spans(bounded)
    return _PreparedText(bounded, folded, starts, ends)


def _positions(text: str, quote: str) -> list[int]:
    matches: list[int] = []
    position = text.find(quote)
    while position >= 0:
        matches.append(position)
        position = text.find(quote, position + 1)
    return matches


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 96)
    right = min(len(text), end + 96, left + MAX_EXCERPT_CHARS)
    return ("…" if left else "") + text[left:right] + ("…" if right < len(text) else "")


def check_quote(
    text: str, quote: str, anchor: QuoteAnchor | None = None
) -> QuoteCheck:
    """Check the complete quote, allowing whitespace changes and no others.

    All occurrences, including overlapping and whitespace-equivalent ones,
    count as candidates. Multiple occurrences stay ambiguous unless exactly
    one reproduces every character of the anchor's stored surrounding context.
    The saved position hint never grants a match. Only the first
    ``MAX_READABLE_CHARS`` of the supplied text are inspected.
    """
    return _check_prepared(_prepare_text(text), quote, anchor)


def check_quotes(
    text: str, items: list[tuple[str, QuoteAnchor | None]]
) -> list[QuoteCheck]:
    """Check at most the first 100 quotations, preparing source text once.

    Results preserve input order and the behavior of ``check_quote``. Entries
    after ``MAX_QUOTE_CHECKS`` are not inspected. No prepared text is cached
    outside this call, so checks against another page always use fresh text.
    """
    if not items:
        return []
    prepared = _prepare_text(text)
    return [_check_prepared(prepared, quote, anchor) for quote, anchor in items[:MAX_QUOTE_CHECKS]]


def _check_prepared(
    prepared: _PreparedText, quote: str, anchor: QuoteAnchor | None
) -> QuoteCheck:
    if not isinstance(quote, str) or not quote.strip():
        return QuoteCheck("empty", message="No quoted text is available to check.")
    if len(quote) > MAX_QUOTE_CHARS:
        return QuoteCheck("missing", message="The quote exceeds the 8,000-character check limit.")
    text = prepared.text
    if not text:
        return QuoteCheck("missing", message="The quote was not found in the extracted page text.")
    quote = quote.strip()
    folded, starts, ends = prepared.folded, prepared.starts, prepared.ends
    needle = _fold(quote)
    candidates = _positions(folded, needle)
    count = len(candidates)
    if not count:
        return QuoteCheck("missing", message="The full quote was not found in the extracted page text.")

    eligible = candidates
    if count > 1:
        context_valid = (
            isinstance(anchor, QuoteAnchor)
            and isinstance(anchor.exact, str)
            and len(anchor.exact) <= MAX_QUOTE_CHARS
            and _fold(anchor.exact.strip()) == needle
            and isinstance(anchor.prefix, str)
            and isinstance(anchor.suffix, str)
            and len(anchor.prefix) <= CONTEXT_CHARS
            and len(anchor.suffix) <= CONTEXT_CHARS
        )
        if context_valid and anchor is not None and (anchor.prefix or anchor.suffix):
            prefix, suffix = _fold(anchor.prefix), _fold(anchor.suffix)
            eligible = [
                position
                for position in candidates
                if (not prefix or folded[max(0, position - len(prefix)) : position] == prefix)
                and (
                    not suffix
                    or folded[position + len(needle) : position + len(needle) + len(suffix)] == suffix
                )
            ]
        if len(eligible) != 1:
            return QuoteCheck(
                "ambiguous",
                count,
                message=f"The full quote occurs {count} times; its saved context does not identify one occurrence.",
            )

    position = eligible[0]
    start, end = starts[position], ends[position + len(needle) - 1]
    matched = text[start:end]
    status = "exact" if matched == quote else "normalized"
    detail = (
        "The full quote is present verbatim."
        if status == "exact"
        else "The full quote is present with whitespace changes only."
    )
    if count > 1:
        detail += f" Saved context identifies one of {count} occurrences."
    return QuoteCheck(status, count, _excerpt(text, start, end), detail, matched)


def capture_quote_anchor(text: str, quote: str) -> QuoteAnchor | None:
    """Capture bounded context only when the complete quote occurs once.

    Missing or repeated selections retain their exact text with no location
    hints, so future checks cannot mistake a guessed position for evidence.
    """
    if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE_CHARS:
        return None
    quote = quote.strip()
    fallback = QuoteAnchor(exact=quote)
    if not isinstance(text, str) or not text:
        return fallback
    text = text[:MAX_READABLE_CHARS]
    folded, starts, ends = _fold_with_spans(text)
    needle = _fold(quote)
    positions = _positions(folded, needle)
    if len(positions) != 1:
        return fallback
    position = positions[0]
    start, end = starts[position], ends[position + len(needle) - 1]
    return QuoteAnchor(
        exact=quote,
        prefix=text[max(0, start - CONTEXT_CHARS) : start],
        suffix=text[end : end + CONTEXT_CHARS],
        offset_hint=start,
    )


def _url_identity(value: str) -> tuple[object, ...] | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_SOURCE_URL_CHARS
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value)
        or "\\" in value
        or _BAD_PERCENT_RE.search(value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme
        if scheme not in {"http", "https", "file"}:
            return None
        hostname = parsed.hostname or ""
        port = parsed.port
        if scheme in {"http", "https"} and not hostname:
            return None
        if parsed.path and not parsed.path.startswith("/"):
            return None
        if scheme == "file" and (not parsed.path.startswith("/") or port is not None or "@" in parsed.netloc):
            return None
        if parsed.netloc.count("@") > 1 or parsed.netloc.endswith(":"):
            return None
        if hostname:
            if ":" in hostname:
                ipaddress.IPv6Address(hostname)
            else:
                ascii_host = hostname.encode("idna").decode("ascii")
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", ascii_host) or ascii_host.startswith(".") or ".." in ascii_host:
                    return None
        userinfo = parsed.netloc.rsplit("@", 1)[0] if "@" in parsed.netloc else None
        if (scheme, port) in {("http", 80), ("https", 443)}:
            port = None
        path = parsed.path or ("/" if scheme in {"http", "https"} else "")
        return scheme, hostname.lower(), port, userinfo, path, parsed.query
    except (ValueError, UnicodeError):
        return None


def same_source_url(left: str, right: str) -> bool:
    """Compare source identity, normalizing only an empty HTTP(S) path to `/`."""
    identity = _url_identity(left)
    return identity is not None and identity == _url_identity(right)

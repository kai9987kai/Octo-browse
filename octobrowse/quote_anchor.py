"""Relocatable quote anchors that survive a page changing under them.

A character offset identifies a quote only in the exact text it was taken
from. Reload the page a week later — an inserted paragraph, a reworded intro,
a cookie banner that did not render this time — and the offset points at the
wrong words, silently. That is the failure mode that makes "jump back to what
I highlighted" unreliable in every tool that stores positions.

This module stores a quote the way the W3C Web Annotation model does: the
exact text, plus a short window of the text on either side. Relocation then
proceeds from most to least confident:

1. The exact text appears once — unambiguous, done.
2. It appears several times — pick the occurrence whose surrounding context
   best matches the stored prefix and suffix.
3. It does not appear at all — report failure rather than guess. A wrong
   highlight is worse than an honest "this quote is no longer on the page".

Anchors are plain JSON-safe dicts so they can be persisted next to a research
note and relocated in a future session.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


__all__ = [
    "CONTEXT_CHARS",
    "QuoteAnchor",
    "QuoteMatch",
    "build_anchor",
    "locate_anchor",
]


#: How much text either side of the quote is kept to disambiguate it.
CONTEXT_CHARS = 48
#: Quotes longer than this are anchored on their opening window; a whole
#: paragraph is not more identifying than its first sentence, and storing it
#: twice bloats every note.
MAX_EXACT_CHARS = 512

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class QuoteAnchor:
    """A quote plus enough surrounding text to find it again."""

    exact: str
    prefix: str = ""
    suffix: str = ""
    #: Where the quote was when the anchor was made. A hint for tie-breaking
    #: only — never trusted on its own, because it is exactly what goes stale.
    offset_hint: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact": self.exact,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "offset_hint": self.offset_hint,
        }

    @classmethod
    def from_dict(cls, data: Any) -> QuoteAnchor | None:
        """Rebuild an anchor from stored JSON, failing closed on junk."""
        if not isinstance(data, dict):
            return None
        exact = data.get("exact")
        if not isinstance(exact, str) or not exact.strip():
            return None
        prefix = data.get("prefix")
        suffix = data.get("suffix")
        hint = data.get("offset_hint")
        return cls(
            exact=exact,
            prefix=prefix if isinstance(prefix, str) else "",
            suffix=suffix if isinstance(suffix, str) else "",
            offset_hint=hint if isinstance(hint, int) and hint >= 0 else -1,
        )


@dataclass(frozen=True, slots=True)
class QuoteMatch:
    """Where an anchor was found, and how sure we are."""

    offset: int
    text: str
    #: 1.0 when the quote occurs exactly once. Below that, the share of stored
    #: context that also matched at the chosen occurrence.
    confidence: float
    #: How many places the quote text occurs in the document.
    candidates: int


def _normalize(text: str) -> str:
    """Fold text so trivial rendering differences do not break a match.

    Whitespace runs collapse and compatibility forms are unified, which is
    what makes an anchor survive a page being re-rendered with different line
    wrapping.
    """
    if not isinstance(text, str):
        return ""
    folded = unicodedata.normalize("NFKC", text)
    return _WHITESPACE_RE.sub(" ", folded).strip()


def build_anchor(text: str, offset: int, length: int) -> QuoteAnchor | None:
    """Anchor the slice ``text[offset:offset + length]``.

    Returns ``None`` when the slice is empty or the bounds fall outside the
    text, so a caller cannot accidentally store an anchor to nothing.
    """
    if not isinstance(text, str) or not text:
        return None
    try:
        offset = int(offset)
        length = int(length)
    except (TypeError, ValueError):
        return None
    if offset < 0 or length <= 0 or offset >= len(text):
        return None

    end = min(len(text), offset + length)
    exact = text[offset:end]
    if not exact.strip():
        return None
    if len(exact) > MAX_EXACT_CHARS:
        exact = exact[:MAX_EXACT_CHARS]
        end = offset + MAX_EXACT_CHARS

    return QuoteAnchor(
        exact=exact,
        prefix=text[max(0, offset - CONTEXT_CHARS) : offset],
        suffix=text[end : end + CONTEXT_CHARS],
        offset_hint=offset,
    )


def _shared_suffix_length(left: str, right: str) -> int:
    """Length of the longest common tail of two strings."""
    limit = min(len(left), len(right))
    count = 0
    while count < limit and left[-1 - count] == right[-1 - count]:
        count += 1
    return count


def _shared_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    count = 0
    while count < limit and left[count] == right[count]:
        count += 1
    return count


def _find_all(haystack: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = haystack.find(needle)
    while start != -1:
        positions.append(start)
        start = haystack.find(needle, start + 1)
    return positions


def locate_anchor(text: str, anchor: QuoteAnchor) -> QuoteMatch | None:
    """Find ``anchor`` in ``text``, or return ``None`` if it is gone.

    Matching is attempted on the raw text first so the returned offset indexes
    the caller's own string exactly. Only if that fails does it retry against a
    whitespace-folded copy, which handles a page that re-rendered with
    different wrapping but cannot report an exact offset — in that case the
    offset locates the match in the folded text and ``confidence`` is reduced
    to say so.
    """
    if not isinstance(text, str) or not text or anchor is None:
        return None
    if not anchor.exact:
        return None

    positions = _find_all(text, anchor.exact)
    exact_text = anchor.exact
    folded = False
    if not positions:
        text = _normalize(text)
        exact_text = _normalize(anchor.exact)
        if not exact_text:
            return None
        positions = _find_all(text, exact_text)
        folded = True
    if not positions:
        return None

    if len(positions) == 1:
        return QuoteMatch(
            offset=positions[0],
            text=exact_text,
            confidence=0.8 if folded else 1.0,
            candidates=1,
        )

    # Ambiguous: score each occurrence by how much of the stored context it
    # reproduces, and fall back to the offset hint only to break a real tie.
    prefix = _normalize(anchor.prefix) if folded else anchor.prefix
    suffix = _normalize(anchor.suffix) if folded else anchor.suffix
    context_budget = len(prefix) + len(suffix)

    best_position = positions[0]
    best_score = -1.0
    for position in positions:
        before = text[max(0, position - len(prefix)) : position] if prefix else ""
        after = text[position + len(exact_text) : position + len(exact_text) + len(suffix)]
        matched = _shared_suffix_length(prefix, before) + _shared_prefix_length(
            suffix, after
        )
        score = matched / context_budget if context_budget else 0.0
        if score > best_score or (
            score == best_score
            and anchor.offset_hint >= 0
            and abs(position - anchor.offset_hint)
            < abs(best_position - anchor.offset_hint)
        ):
            best_score, best_position = score, position

    confidence = max(0.0, min(1.0, best_score))
    if folded:
        confidence *= 0.8
    return QuoteMatch(
        offset=best_position,
        text=exact_text,
        confidence=round(confidence, 4),
        candidates=len(positions),
    )

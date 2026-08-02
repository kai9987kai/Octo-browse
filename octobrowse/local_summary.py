"""Deterministic, offline extractive summarization.

Every AI capability in OctoBrowse is gated behind an OpenAI key and a hardcoded
model id, so the browser's headline research features are unavailable to anyone
who declines a cloud account — and stop working for everyone the day that model
is retired.  This module gives those workflows a floor that always holds: it
runs in-process with nothing but the standard library, so it works offline, in
private tabs, with no consent prompt and no data leaving the machine.

Because the output is *extractive* — every bullet is a verbatim sentence copied
out of the page, with the character offset it came from — it cannot hallucinate.
A reader can always check a bullet against the source it points at.

The ranking is TextRank-flavoured: sentences are scored by how much significant
vocabulary they share with the rest of the page (degree centrality over a TF-IDF
similarity graph), adjusted by position and length priors, then selected with
maximal-marginal-relevance so the bullets do not restate one another.

Determinism is a hard requirement — the same text must always yield the same
bullets, so nothing here iterates an unordered set and every tie breaks on an
explicit key.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

from .ai_context import clean_page_text


__all__ = [
    "DEFAULT_MAX_BULLETS",
    "DEFAULT_MAX_CHARS",
    "MAX_SCORED_SENTENCES",
    "LocalSummary",
    "SummarySentence",
    "split_sentences",
    "summarize",
]


DEFAULT_MAX_BULLETS = 7
DEFAULT_MAX_CHARS = 1800
# The similarity graph is O(N^2) in sentences. Real articles sit far below this
# cap; it exists so a pathological 100k-word page cannot stall the UI thread.
MAX_SCORED_SENTENCES = 400

_MIN_SENTENCE_CHARS = 30
_MAX_SENTENCE_CHARS = 400
_REDUNDANCY_LAMBDA = 0.65
# A bullet this similar to one already chosen says nothing new, so it is
# excluded outright rather than merely penalised — a page that repeats one
# sentence must never fill the summary with copies of it.
_MAX_REDUNDANCY = 0.9

_TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n{2,}")

# Latin sentences end with punctuation *and* whitespace — "3.5" must not split.
# Ideographic text is written without spaces, so a CJK terminator ends a
# sentence on its own; requiring whitespace there means never splitting at all.
_LATIN_TERMINATORS = ".!?…"
_CJK_TERMINATORS = "。！？"
_CLOSERS = "\"'”’)]}」』）"
_SENTENCE_BOUNDARY_RE = re.compile(
    rf"(?P<latin>[{re.escape(_LATIN_TERMINATORS)}]+[{re.escape(_CLOSERS)}]*)(?:\s+|$)"
    rf"|(?P<cjk>[{re.escape(_CJK_TERMINATORS)}]+[{re.escape(_CLOSERS)}]*)\s*"
)

# Tokens that take a full stop without ending a sentence.
_ABBREVIATIONS = frozenset(
    {
        "al", "approx", "apr", "aug", "ave", "ca", "cf", "co", "corp", "dec",
        "dept", "dr", "eg", "esp", "est", "et", "etc", "feb", "fig", "figs",
        "gen", "gov", "ie", "inc", "jan", "jr", "jul", "jun", "lt", "ltd",
        "mar", "max", "min", "mr", "mrs", "ms", "mt", "no", "nov", "oct",
        "op", "pp", "prof", "rev", "sep", "sept", "sr", "st", "vol", "vs",
    }
)

# A summarization stop list, deliberately broader than the one ai_context uses
# for prompt relevance: function words that carry no topical signal would
# otherwise dominate the similarity graph and make every sentence look alike.
_STOP_WORDS = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "also",
        "am", "an", "and", "any", "are", "as", "at", "be", "because", "been",
        "before", "being", "below", "between", "both", "but", "by", "can",
        "cannot", "could", "did", "do", "does", "doing", "down", "during",
        "each", "few", "for", "from", "further", "had", "has", "have",
        "having", "he", "her", "here", "hers", "herself", "him", "himself",
        "his", "how", "however", "i", "if", "in", "into", "is", "it", "its",
        "itself", "just", "may", "me", "might", "more", "most", "much",
        "must", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
        "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
        "out", "over", "own", "same", "shall", "she", "should", "so", "some",
        "still", "such", "than", "that", "the", "their", "theirs", "them",
        "themselves", "then", "there", "these", "they", "this", "those",
        "through", "to", "too", "under", "until", "up", "us", "very", "was",
        "we", "were", "what", "when", "where", "whether", "which", "while",
        "who", "whom", "why", "will", "with", "would", "you", "your", "yours",
        "yourself", "yourselves",
    }
)


@dataclass(frozen=True, slots=True)
class SummarySentence:
    """One verbatim sentence lifted out of the page.

    ``offset`` indexes into :attr:`LocalSummary.source_text`, so
    ``source_text[offset:offset + len(text)] == text`` always holds.  That is
    what makes a bullet checkable against — and locatable in — its source.
    """

    text: str
    offset: int
    score: float


@dataclass(frozen=True, slots=True)
class LocalSummary:
    """The result of summarizing one page entirely on-device."""

    bullets: tuple[SummarySentence, ...]
    keywords: tuple[str, ...]
    source_text: str
    method: str
    coverage: float

    def __bool__(self) -> bool:
        return bool(self.bullets)

    def as_text(self) -> str:
        """Render the summary as plain bullet lines."""
        return "\n".join(f"• {bullet.text}" for bullet in self.bullets)


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in (match.group(0).lower() for match in _TOKEN_RE.finditer(text))
        if token not in _STOP_WORDS and not token.isdigit() and len(token) > 1
    ]


def _is_abbreviation(text: str, terminator_start: int) -> bool:
    """Whether the word ending at ``terminator_start`` only looks like an end."""
    start = terminator_start
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "."):
        start -= 1
    word = text[start:terminator_start].strip(".").lower()
    if not word:
        return False
    if word in _ABBREVIATIONS:
        return True
    # A lone initial ("J. Smith") or a dotted acronym ("U.S.").
    return len(word) == 1 and word.isalpha()


def _segment(text: str, base_offset: int) -> list[tuple[str, int]]:
    """Split one paragraph into (sentence, absolute offset) pairs."""
    pieces: list[tuple[str, int]] = []
    start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        group = "latin" if match.group("latin") is not None else "cjk"
        end = match.end(group)
        if _is_abbreviation(text, match.start(group)):
            continue
        candidate = text[start:end].strip()
        if candidate:
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            pieces.append((candidate, base_offset + start + leading))
        start = match.end()
    remainder = text[start:].strip()
    if remainder:
        leading = len(text[start:]) - len(text[start:].lstrip())
        pieces.append((remainder, base_offset + start + leading))
    return pieces


def split_sentences(text: str) -> list[tuple[str, int]]:
    """Return ``(sentence, offset)`` pairs for already-cleaned ``text``.

    Paragraph boundaries always end a sentence, so a heading or list item
    without terminal punctuation is not glued onto the paragraph after it.
    """
    if not text:
        return []
    sentences: list[tuple[str, int]] = []
    cursor = 0
    for paragraph in _PARAGRAPH_SPLIT_RE.split(text):
        offset = text.find(paragraph, cursor) if paragraph else -1
        if offset < 0:
            offset = cursor
        sentences.extend(_segment(paragraph, offset))
        cursor = offset + len(paragraph)
    return sentences


def _term_frequencies(tokens: Iterable[str]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return {term: float(count) for term, count in counts.items()}


def _weight_vectors(
    token_lists: list[list[str]],
) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Build L2-normalized TF-IDF vectors plus the document-wide IDF table."""
    document_count = len(token_lists)
    document_frequency: dict[str, int] = {}
    for tokens in token_lists:
        for term in sorted(set(tokens)):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    idf = {
        term: math.log((document_count + 1) / (frequency + 1)) + 1.0
        for term, frequency in document_frequency.items()
    }

    vectors: list[dict[str, float]] = []
    for tokens in token_lists:
        weights = {
            term: (1.0 + math.log(count)) * idf.get(term, 1.0)
            for term, count in _term_frequencies(tokens).items()
        }
        norm = math.sqrt(sum(value * value for value in weights.values()))
        if norm > 0.0:
            weights = {term: value / norm for term, value in weights.items()}
        vectors.append(weights)
    return vectors, idf


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(term, 0.0) for term, weight in left.items())


def _length_prior(length: int) -> float:
    """Favour sentences long enough to stand alone but short enough to read."""
    if length < _MIN_SENTENCE_CHARS:
        return 0.35
    if length > _MAX_SENTENCE_CHARS:
        return 0.55
    return 1.0


def _position_prior(index: int, total: int) -> float:
    """Lead sentences carry more of an article's thesis than its tail."""
    if total <= 1:
        return 1.0
    return 1.0 + 0.25 * (1.0 - index / (total - 1))


def _select(
    candidates: list[tuple[int, float]],
    vectors: list[dict[str, float]],
    max_bullets: int,
    max_chars: int,
    lengths: list[int],
) -> list[int]:
    """Greedy maximal-marginal-relevance selection over scored sentences."""
    chosen: list[int] = []
    used_chars = 0
    remaining = list(candidates)
    while remaining and len(chosen) < max_bullets:
        surviving: list[tuple[int, float]] = []
        best_position: int | None = None
        best_value = -math.inf
        for index, base_score in remaining:
            redundancy = max(
                (_cosine(vectors[index], vectors[picked]) for picked in chosen),
                default=0.0,
            )
            if redundancy >= _MAX_REDUNDANCY:
                continue
            surviving.append((index, base_score))
            value = _REDUNDANCY_LAMBDA * base_score - (1.0 - _REDUNDANCY_LAMBDA) * redundancy
            # `candidates` arrives score-ordered with ties broken on document
            # position, and `>` keeps the first of any tie, so selection is
            # never arbitrary.
            if value > best_value:
                best_value, best_position = value, len(surviving) - 1
        remaining = surviving
        if best_position is None:
            break
        index, _ = remaining.pop(best_position)
        if used_chars and used_chars + lengths[index] > max_chars:
            continue
        chosen.append(index)
        used_chars += lengths[index]
        if used_chars >= max_chars:
            break
    return chosen


def summarize(
    text: str,
    *,
    max_bullets: int = DEFAULT_MAX_BULLETS,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_keywords: int = 8,
) -> LocalSummary:
    """Summarize ``text`` on-device, returning verbatim source sentences.

    The result is deterministic: identical input always produces identical
    bullets, in document order.
    """

    max_bullets = max(1, int(max_bullets))
    max_chars = max(120, int(max_chars))
    source = clean_page_text(text or "")
    if not source.strip():
        return LocalSummary((), (), source, "empty", 0.0)

    pairs = split_sentences(source)
    if not pairs:
        return LocalSummary((), (), source, "empty", 0.0)

    method = "extractive:textrank"
    if len(pairs) == 1:
        # No usable sentence structure — fall back to paragraph selection so
        # the caller still gets something checkable rather than nothing.
        method = "extractive:paragraph"

    token_lists = [_tokenize(sentence) for sentence, _ in pairs]
    lengths = [len(sentence) for sentence, _ in pairs]

    # Bound the O(N^2) stage: pre-rank on raw significant-term density, keep the
    # densest MAX_SCORED_SENTENCES, and restore document order before scoring.
    if len(pairs) > MAX_SCORED_SENTENCES:
        method = "extractive:textrank-capped"
        density = sorted(
            range(len(pairs)),
            key=lambda index: (-len(set(token_lists[index])), index),
        )
        keep = sorted(density[:MAX_SCORED_SENTENCES])
        pairs = [pairs[index] for index in keep]
        token_lists = [token_lists[index] for index in keep]
        lengths = [lengths[index] for index in keep]

    vectors, idf = _weight_vectors(token_lists)
    total = len(pairs)

    scored: list[tuple[int, float]] = []
    for index in range(total):
        centrality = 0.0
        for other in range(total):
            if other != index:
                centrality += _cosine(vectors[index], vectors[other])
        centrality = centrality / (total - 1) if total > 1 else 1.0
        score = centrality * _length_prior(lengths[index]) * _position_prior(index, total)
        scored.append((index, score))

    # Sort by score, then by document position, so ties are never arbitrary.
    ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
    chosen = _select(ranked, vectors, max_bullets, max_chars, lengths)
    chosen.sort()

    bullets = tuple(
        SummarySentence(text=pairs[index][0], offset=pairs[index][1], score=round(dict(scored)[index], 6))
        for index in chosen
    )

    selected_terms: set[str] = set()
    for index in chosen:
        selected_terms.update(token_lists[index])
    all_terms = {term for tokens in token_lists for term in tokens}
    coverage = len(selected_terms) / len(all_terms) if all_terms else 0.0

    keywords = tuple(
        term
        for term, _ in sorted(
            ((term, idf.get(term, 0.0) * sum(tokens.count(term) for tokens in token_lists))
             for term in sorted(all_terms)),
            key=lambda item: (-item[1], item[0]),
        )[:max_keywords]
    )

    return LocalSummary(
        bullets=bullets,
        keywords=keywords,
        source_text=source,
        method=method,
        coverage=round(coverage, 4),
    )

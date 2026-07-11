"""Reusable, UI-independent helpers for OctoBrowse."""

from .ai_context import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CONTEXT_CHAR_BUDGET,
    MAX_CONTEXT_CHAR_BUDGET,
    ResponsesPrompt,
    SourceChunk,
    build_qa_prompt,
    build_responses_prompt,
    build_summary_prompt,
    clean_page_text,
    delimit_untrusted_content,
    escape_untrusted_content,
    lexical_relevance_score,
    select_context_chunks,
    split_page_text,
)

__all__ = [
    "DEFAULT_CHUNK_CHARS",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CONTEXT_CHAR_BUDGET",
    "MAX_CONTEXT_CHAR_BUDGET",
    "ResponsesPrompt",
    "SourceChunk",
    "build_qa_prompt",
    "build_responses_prompt",
    "build_summary_prompt",
    "clean_page_text",
    "delimit_untrusted_content",
    "escape_untrusted_content",
    "lexical_relevance_score",
    "select_context_chunks",
    "split_page_text",
]

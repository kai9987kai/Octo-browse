from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from octobrowse import evidence
from octobrowse.evidence import (
    MAX_QUOTE_CHECKS,
    MAX_QUOTE_CHARS,
    MAX_READABLE_CHARS,
    capture_quote_anchor,
    check_quote,
    check_quotes,
    same_source_url,
)
from octobrowse.quote_anchor import QuoteAnchor


class QuoteEvidenceTests(unittest.TestCase):
    def test_exact_match_has_original_surroundings_and_immutable_result(self) -> None:
        result = check_quote("Before. A complete sentence. After.", "A complete sentence.")
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.candidates, 1)
        self.assertEqual(result.matched_text, "A complete sentence.")
        self.assertIn("Before.", result.excerpt)
        self.assertIn("After.", result.excerpt)
        with self.assertRaises(FrozenInstanceError):
            result.status = "missing"  # type: ignore[misc]

    def test_full_long_quote_is_required_including_edited_tail(self) -> None:
        quote = "A detailed finding. " * 90 + "The rate is 12 percent."
        anchor = capture_quote_anchor(quote, quote)
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.exact, quote)
        self.assertEqual(check_quote(quote, quote, anchor).status, "exact")
        changed = quote[:-len("12 percent.")] + "30 percent."
        self.assertEqual(check_quote(changed, quote, anchor).status, "missing")

    def test_whitespace_is_normalized_but_not_case_or_unicode_meaning(self) -> None:
        result = check_quote("Intro\nA\tquoted\n\nline. End", "A quoted line.")
        self.assertEqual(result.status, "normalized")
        self.assertEqual(result.matched_text, "A\tquoted\n\nline.")
        self.assertEqual(check_quote("A quoted line.", "a quoted line.").status, "missing")
        self.assertEqual(check_quote("Value: １２", "Value: 12").status, "missing")

    def test_duplicates_include_whitespace_variants_and_overlaps(self) -> None:
        result = check_quote("A claim. A\nclaim.", "A claim.")
        self.assertEqual((result.status, result.candidates), ("ambiguous", 2))
        result = check_quote("aaaa", "aaa")
        self.assertEqual((result.status, result.candidates), ("ambiguous", 2))

    def test_all_context_can_select_one_duplicate_without_using_offset(self) -> None:
        text = "old context: The result. rejected.\nnew context: The result. accepted."
        anchor = QuoteAnchor("The result.", "new context: ", " accepted.", 0)
        result = check_quote(text, "The result.", anchor)
        self.assertEqual((result.status, result.candidates), ("exact", 2))
        self.assertIn("Saved context", result.message)
        mismatch = QuoteAnchor("The result.", "new context: ", " rejected.", 0)
        self.assertEqual(check_quote(text, "The result.", mismatch).status, "ambiguous")

    def test_matching_context_duplicates_and_stale_offsets_remain_ambiguous(self) -> None:
        text = "before quote after. before quote after."
        for anchor in (QuoteAnchor("quote", offset_hint=7), QuoteAnchor("quote", "before ", " after.")):
            self.assertEqual(check_quote(text, "quote", anchor).status, "ambiguous")

    def test_truncated_or_unrelated_anchor_cannot_select_a_full_quote(self) -> None:
        text = "a full quote. wrong. b full quote. correct."
        anchor = QuoteAnchor("full", "b ", " quote. correct.")
        self.assertEqual(check_quote(text, "full quote.", anchor).status, "ambiguous")

    def test_capture_preserves_raw_context_for_whitespace_equivalent_selection(self) -> None:
        text = "Before words. A\nquoted\tline. After words."
        anchor = capture_quote_anchor(text, "A quoted line.")
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.prefix, "Before words. ")
        self.assertEqual(anchor.suffix, " After words.")
        self.assertEqual(anchor.offset_hint, text.index("A\n"))
        self.assertEqual(check_quote(text, anchor.exact, anchor).status, "normalized")

    def test_missing_and_repeated_capture_have_no_guessed_context(self) -> None:
        for text in ("quote appears twice: quote", "another page"):
            self.assertEqual(capture_quote_anchor(text, "quote"), QuoteAnchor("quote"))

    def test_limits_fail_closed_without_checking_only_a_prefix(self) -> None:
        long_quote = "x" * (MAX_QUOTE_CHARS + 1)
        self.assertEqual(check_quote(long_quote, long_quote).status, "missing")
        self.assertIsNone(capture_quote_anchor(long_quote, long_quote))
        self.assertEqual(check_quote("x" * MAX_READABLE_CHARS + "tail", "tail").status, "missing")
        self.assertEqual(check_quote("x" * MAX_QUOTE_CHARS, "x" * MAX_QUOTE_CHARS).status, "exact")
        self.assertEqual(check_quote("page", " \n ").status, "empty")
        self.assertEqual(check_quote(None, "quote").status, "missing")  # type: ignore[arg-type]


class BatchQuoteEvidenceTests(unittest.TestCase):
    def test_batch_retains_all_single_check_results_in_input_order(self) -> None:
        text = "An exact quote. A\nwrapped quote. before repeat after. other repeat tail."
        items = [
            ("An exact quote.", None),
            ("A wrapped quote.", None),
            ("repeat", None),
            ("repeat", QuoteAnchor("repeat", "before ", " after.")),
            ("repeat", QuoteAnchor("repeat", "before ", " tail.")),
            ("gone", None),
            ("\n ", None),
            ("x" * (MAX_QUOTE_CHARS + 1), None),
        ]
        expected = [check_quote(text, quote, anchor) for quote, anchor in items]
        self.assertEqual(check_quotes(text, items), expected)
        self.assertEqual(check_quotes("", items), [check_quote("", quote, anchor) for quote, anchor in items])
        self.assertEqual(check_quotes(text, []), [])

    def test_batch_prepares_source_once_and_does_not_reuse_another_page(self) -> None:
        items = [(f"quote {index}.", None) for index in range(MAX_QUOTE_CHECKS)]
        text = "\n".join(quote for quote, _anchor in items)
        with patch.object(evidence, "_fold_with_spans", wraps=evidence._fold_with_spans) as prepare:
            results = check_quotes(text, items)
            self.assertEqual(prepare.call_count, 1)
        self.assertTrue(all(result.status == "exact" for result in results))
        self.assertTrue(all(result.status == "missing" for result in check_quotes("Different page.", items)))

    def test_batch_caps_entries_and_document_without_inspecting_extra_items(self) -> None:
        items = [("quote", None)] * MAX_QUOTE_CHECKS + [None]
        results = check_quotes("quote", items)  # type: ignore[arg-type]
        self.assertEqual(len(results), MAX_QUOTE_CHECKS)
        self.assertTrue(all(result.status == "exact" for result in results))
        results = check_quotes("x" * MAX_READABLE_CHARS + "tail", [("tail", None)])
        self.assertEqual(results[0].status, "missing")


class SourceIdentityTests(unittest.TestCase):
    def test_only_safe_url_identity_differences_are_ignored(self) -> None:
        for left, right in (
            ("https://EXAMPLE.test:443/article?q=1#old", "https://example.test/article?q=1#new"),
            ("http://example.test:80/article", "http://example.test/article"),
            ("file:///C:/Saved/page.html#one", "file:///C:/Saved/page.html#two"),
            ("https://[::1]:443/path", "https://[::1]/path"),
            ("https://example.test", "https://example.test/"),
            ("http://example.test?query=1#old", "http://example.test/?query=1#new"),
        ):
            with self.subTest(left=left, right=right):
                self.assertTrue(same_source_url(left, right))

    def test_source_path_query_scheme_userinfo_and_nondefault_port_stay_distinct(self) -> None:
        for left, right in (
            ("http://example.test/page", "https://example.test/page"),
            ("https://example.test/Page", "https://example.test/page"),
            ("https://example.test/page?q=1", "https://example.test/page?q=2"),
            ("https://example.test/page?a=1&b=2", "https://example.test/page?b=2&a=1"),
            ("https://User:pass@example.test/page", "https://user:pass@example.test/page"),
            ("https://user@example.test/page", "https://example.test/page"),
            ("https://example.test:444/page", "https://example.test/page"),
            ("https://example.test/%61", "https://example.test/a"),
            ("file:///C:/Saved/Page.html", "file:///C:/Saved/page.html"),
            ("file://localhost/C:/Saved/page.html", "file:///C:/Saved/page.html"),
        ):
            with self.subTest(left=left, right=right):
                self.assertFalse(same_source_url(left, right))

    def test_invalid_and_unsupported_urls_never_identify_a_source(self) -> None:
        for url in (
            "", "example.test/page", "https:///page", "http://", "javascript:alert(1)",
            "about:blank", "data:text/plain,quote", "https://example.test:bad/page",
            "https://example.test:99999/page", "https://[broken]/page", "https://example.test:/page",
            "https://ex ample.test/page", "https://example.test/\npage", "https://example.test/%ZZ",
            "https://example.test\\@evil.test/page", "file:relative.txt", "file://user@host/path",
            "file://host:80/path", "https://example..test/", None,
        ):
            with self.subTest(url=url):
                self.assertFalse(same_source_url(url, url))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

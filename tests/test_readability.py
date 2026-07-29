import unittest

from octobrowse.readability import (
    MAX_READABLE_CHARS,
    READABLE_PAGE_SCRIPT,
    ReadablePage,
    normalize_readable_page,
)


class ReadabilityTests(unittest.TestCase):
    def test_structured_result_is_normalized_and_uses_trusted_source_url(self) -> None:
        page = normalize_readable_page(
            {
                "text": " First line \n\n Second   line ",
                "title": "  Article   title ",
                "byline": "  Ada   Lovelace ",
                "excerpt": " Summary ",
                "site_name": " Example ",
                "language": " en-GB ",
                "method": "semantic:article",
                "url": "https://attacker.test/spoofed",
            },
            fallback_title="Fallback",
            source_url="https://example.test/article",
        )
        self.assertEqual(page.text, "First line\n\nSecond line")
        self.assertEqual(page.title, "Article title")
        self.assertEqual(page.byline, "Ada Lovelace")
        self.assertEqual(page.url, "https://example.test/article")
        self.assertEqual(page.method, "semantic:article")
        self.assertEqual(page.word_count, 4)
        self.assertEqual(page.reading_minutes, 1)

    def test_malformed_fields_are_not_stringified(self) -> None:
        page = normalize_readable_page(
            {
                "text": ["not", "text"],
                "title": {"not": "a title"},
                "byline": 123,
                "method": None,
            },
            fallback_title="Safe fallback",
            source_url=["not", "a URL"],
        )
        self.assertEqual(
            page,
            ReadablePage(
                text="",
                title="Safe fallback",
                url="",
            ),
        )

    def test_text_and_metadata_are_bounded(self) -> None:
        page = normalize_readable_page(
            {
                "text": "x" * (MAX_READABLE_CHARS * 3),
                "title": "t" * 1000,
                "method": "m" * 200,
            },
            source_url="https://example.test/" + "u" * 10_000,
        )
        self.assertEqual(len(page.text), MAX_READABLE_CHARS)
        self.assertEqual(len(page.title), 512)
        self.assertEqual(len(page.url), 8192)
        self.assertEqual(len(page.method), 64)

    def test_extractor_is_bounded_and_never_returns_page_html(self) -> None:
        self.assertIn("MAX_CANDIDATES = 40", READABLE_PAGE_SCRIPT)
        self.assertIn("MAX_BLOCKS = 2500", READABLE_PAGE_SCRIPT)
        self.assertIn("MAX_SCAN = 20000", READABLE_PAGE_SCRIPT)
        self.assertIn("MAX_ANCESTORS = 64", READABLE_PAGE_SCRIPT)
        self.assertIn("MAX_TEXT = 120000", READABLE_PAGE_SCRIPT)
        self.assertIn("CONTENT_BOUNDARY_SELECTOR", READABLE_PAGE_SCRIPT)
        self.assertNotIn("querySelectorAll", READABLE_PAGE_SCRIPT)
        self.assertNotIn(".closest(", READABLE_PAGE_SCRIPT)
        self.assertNotIn("innerHTML", READABLE_PAGE_SCRIPT)
        self.assertNotIn("innerText", READABLE_PAGE_SCRIPT)
        self.assertNotIn("textContent", READABLE_PAGE_SCRIPT)


if __name__ == "__main__":
    unittest.main()

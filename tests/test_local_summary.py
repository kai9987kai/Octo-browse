from __future__ import annotations

import time
import unittest

from octobrowse.local_summary import (
    MAX_SCORED_SENTENCES,
    LocalSummary,
    summarize,
    split_sentences,
)


ARTICLE = """
Tidal Power Comes of Age

Tidal stream turbines have moved from prototype to production in the last five
years. The MeyGen array in the Pentland Firth now delivers electricity to the
Scottish grid on a continuous commercial basis. Unlike wind and solar, tidal
generation is predictable decades in advance because it depends on the orbital
mechanics of the moon rather than the weather.

The engineering problem was never the turbine itself. Salt water destroys
bearings, marine growth fouls blades, and the cost of sending a vessel out to
service a submerged machine dominates the operating budget. Designers therefore
optimised for maintenance intervals rather than peak efficiency.

Grid operators value predictability because it reduces the reserve capacity they
must hold. A tidal array with a published generation schedule can be treated as
firm capacity, which changes its economic value considerably.

Costs remain higher than offshore wind. Most analysts expect tidal to occupy a
complementary niche rather than to displace other renewables outright.
"""


class SentenceSegmentationTests(unittest.TestCase):
    def test_offsets_locate_the_verbatim_sentence(self) -> None:
        text = "First sentence here. Second sentence follows. Third one ends."
        for sentence, offset in split_sentences(text):
            self.assertEqual(text[offset : offset + len(sentence)], sentence)

    def test_abbreviations_do_not_end_a_sentence(self) -> None:
        text = "Dr. Smith met Prof. Jones at 10 a.m. They discussed the results."
        sentences = [sentence for sentence, _ in split_sentences(text)]
        self.assertEqual(len(sentences), 2)
        self.assertTrue(sentences[0].startswith("Dr. Smith"))

    def test_initials_do_not_end_a_sentence(self) -> None:
        text = "The paper by J. R. Baker is short. It was cited widely."
        sentences = [sentence for sentence, _ in split_sentences(text)]
        self.assertEqual(len(sentences), 2)

    def test_paragraph_breaks_always_end_a_sentence(self) -> None:
        text = "A heading with no full stop\n\nThe body starts here."
        sentences = [sentence for sentence, _ in split_sentences(text)]
        self.assertEqual(sentences, ["A heading with no full stop", "The body starts here."])

    def test_cjk_terminators_segment(self) -> None:
        text = "これは最初の文です。これは二番目の文です。"
        self.assertEqual(len(split_sentences(text)), 2)

    def test_empty_input(self) -> None:
        self.assertEqual(split_sentences(""), [])


class SummarizeTests(unittest.TestCase):
    def test_every_bullet_is_verbatim_at_its_stated_offset(self) -> None:
        summary = summarize(ARTICLE)
        self.assertTrue(summary.bullets)
        for bullet in summary.bullets:
            self.assertEqual(
                summary.source_text[bullet.offset : bullet.offset + len(bullet.text)],
                bullet.text,
                f"offset {bullet.offset} does not locate {bullet.text!r}",
            )

    def test_output_is_deterministic(self) -> None:
        first = summarize(ARTICLE)
        second = summarize(ARTICLE)
        self.assertEqual(
            [(b.text, b.offset) for b in first.bullets],
            [(b.text, b.offset) for b in second.bullets],
        )
        self.assertEqual(first.keywords, second.keywords)
        self.assertEqual(first.coverage, second.coverage)

    def test_bullets_are_returned_in_document_order(self) -> None:
        summary = summarize(ARTICLE)
        offsets = [bullet.offset for bullet in summary.bullets]
        self.assertEqual(offsets, sorted(offsets))

    def test_bullet_count_is_respected(self) -> None:
        summary = summarize(ARTICLE, max_bullets=3)
        self.assertLessEqual(len(summary.bullets), 3)

    def test_character_budget_is_respected(self) -> None:
        summary = summarize(ARTICLE, max_bullets=20, max_chars=300)
        total = sum(len(bullet.text) for bullet in summary.bullets)
        # One over-long sentence may exceed the budget on its own; beyond that
        # the budget must hold.
        self.assertLessEqual(total - max(len(b.text) for b in summary.bullets), 300)

    def test_a_single_long_sentence_still_produces_a_bullet(self) -> None:
        text = "x" * 50 + " and this is one very long single clause without any terminator"
        summary = summarize(text, max_chars=120)
        self.assertEqual(len(summary.bullets), 1)

    def test_near_duplicates_are_suppressed(self) -> None:
        repeated = (
            "Tidal turbines generate predictable renewable electricity for the grid. "
        )
        unique = (
            "Grid operators reduce their reserve capacity when generation is firm. "
        )
        summary = summarize(repeated * 6 + unique, max_bullets=3)
        texts = [bullet.text for bullet in summary.bullets]
        self.assertEqual(len(texts), len(set(texts)))

    def test_empty_and_whitespace_input(self) -> None:
        for value in ("", "   ", "\n\n\t\n"):
            with self.subTest(value=repr(value)):
                summary = summarize(value)
                self.assertEqual(summary.bullets, ())
                self.assertEqual(summary.method, "empty")
                self.assertFalse(summary)

    def test_single_sentence_input_uses_the_paragraph_fallback(self) -> None:
        summary = summarize("A lone statement about tidal turbines and the grid.")
        self.assertEqual(summary.method, "extractive:paragraph")
        self.assertEqual(len(summary.bullets), 1)

    def test_keywords_are_drawn_from_the_page(self) -> None:
        summary = summarize(ARTICLE)
        self.assertTrue(summary.keywords)
        lowered = summary.source_text.lower()
        for keyword in summary.keywords:
            self.assertIn(keyword, lowered)
        self.assertNotIn("the", summary.keywords)

    def test_coverage_is_a_fraction(self) -> None:
        summary = summarize(ARTICLE)
        self.assertGreater(summary.coverage, 0.0)
        self.assertLessEqual(summary.coverage, 1.0)

    def test_as_text_renders_every_bullet(self) -> None:
        summary = summarize(ARTICLE, max_bullets=3)
        rendered = summary.as_text()
        self.assertEqual(rendered.count("•"), len(summary.bullets))
        for bullet in summary.bullets:
            self.assertIn(bullet.text, rendered)

    def test_result_is_immutable(self) -> None:
        summary = summarize(ARTICLE)
        self.assertIsInstance(summary, LocalSummary)
        with self.assertRaises(AttributeError):
            summary.bullets = ()  # type: ignore[misc]


class RenderingTests(unittest.TestCase):
    """The rendered block is what a user reads and can save as a note."""

    def test_rendered_summary_quotes_every_bullet_and_states_provenance(self) -> None:
        from main import OctoBrowse

        summary = summarize(ARTICLE, max_bullets=4)
        rendered = OctoBrowse.render_local_summary(
            summary, "Tidal Power Comes of Age", "https://example.test/tidal"
        )

        self.assertIn("Tidal Power Comes of Age", rendered)
        self.assertIn("https://example.test/tidal", rendered)
        for bullet in summary.bullets:
            self.assertIn(bullet.text, rendered)
        self.assertIn("No page content was sent anywhere", rendered)
        self.assertIn("verbatim", rendered)

    def test_rendering_without_title_or_url_still_works(self) -> None:
        from main import OctoBrowse

        summary = summarize(ARTICLE, max_bullets=2)
        rendered = OctoBrowse.render_local_summary(summary, "", "")
        self.assertTrue(rendered.startswith("Key sentences"))


class BoundedRuntimeTests(unittest.TestCase):
    def test_long_page_is_capped_and_fast(self) -> None:
        sentence = (
            "Tidal stream turbines deliver predictable renewable electricity to "
            "the Scottish grid throughout the year number {index}. "
        )
        text = "".join(sentence.format(index=index) for index in range(4000))
        self.assertGreater(len(text), 120_000)

        started = time.perf_counter()
        summary = summarize(text)
        elapsed = time.perf_counter() - started

        self.assertEqual(summary.method, "extractive:textrank-capped")
        self.assertTrue(summary.bullets)
        self.assertLess(elapsed, 20.0, f"summarize took {elapsed:.2f}s")

    def test_cap_constant_bounds_the_similarity_graph(self) -> None:
        self.assertLessEqual(MAX_SCORED_SENTENCES, 1000)


if __name__ == "__main__":
    unittest.main()

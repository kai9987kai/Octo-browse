from __future__ import annotations

import unittest

from octobrowse.local_summary import summarize
from octobrowse.quote_anchor import (
    CONTEXT_CHARS,
    QuoteAnchor,
    build_anchor,
    locate_anchor,
)


PAGE = (
    "Tidal stream turbines have moved from prototype to production. "
    "The MeyGen array delivers electricity to the Scottish grid. "
    "Grid operators value predictability because it reduces reserve capacity. "
    "Costs remain higher than offshore wind."
)


class BuildAnchorTests(unittest.TestCase):
    def test_captures_the_exact_slice_and_its_context(self) -> None:
        offset = PAGE.index("The MeyGen array")
        anchor = build_anchor(PAGE, offset, len("The MeyGen array"))
        assert anchor is not None
        self.assertEqual(anchor.exact, "The MeyGen array")
        self.assertEqual(PAGE[offset - len(anchor.prefix) : offset], anchor.prefix)
        self.assertTrue(anchor.prefix.endswith("production. "))
        self.assertTrue(anchor.suffix.startswith(" delivers"))
        self.assertEqual(anchor.offset_hint, offset)

    def test_context_is_bounded(self) -> None:
        offset = PAGE.index("Grid operators")
        anchor = build_anchor(PAGE, offset, 14)
        assert anchor is not None
        self.assertLessEqual(len(anchor.prefix), CONTEXT_CHARS)
        self.assertLessEqual(len(anchor.suffix), CONTEXT_CHARS)

    def test_context_at_the_document_edges(self) -> None:
        head = build_anchor(PAGE, 0, 5)
        tail = build_anchor(PAGE, len(PAGE) - 5, 5)
        assert head is not None and tail is not None
        self.assertEqual(head.prefix, "")
        self.assertEqual(tail.suffix, "")

    def test_rejects_slices_that_anchor_to_nothing(self) -> None:
        self.assertIsNone(build_anchor(PAGE, 0, 0))
        self.assertIsNone(build_anchor(PAGE, -1, 5))
        self.assertIsNone(build_anchor(PAGE, len(PAGE) + 10, 5))
        self.assertIsNone(build_anchor("", 0, 5))
        self.assertIsNone(build_anchor("     ", 0, 5))
        self.assertIsNone(build_anchor(PAGE, "x", 5))  # type: ignore[arg-type]

    def test_a_length_past_the_end_is_clamped(self) -> None:
        anchor = build_anchor(PAGE, len(PAGE) - 4, 500)
        assert anchor is not None
        self.assertEqual(anchor.exact, PAGE[-4:])

    def test_very_long_quotes_are_truncated(self) -> None:
        long_page = "word " * 400
        anchor = build_anchor(long_page, 0, len(long_page))
        assert anchor is not None
        self.assertLessEqual(len(anchor.exact), 512)


class LocateAnchorTests(unittest.TestCase):
    def test_unique_quote_is_found_with_full_confidence(self) -> None:
        offset = PAGE.index("Costs remain")
        anchor = build_anchor(PAGE, offset, len("Costs remain higher"))
        assert anchor is not None
        match = locate_anchor(PAGE, anchor)
        assert match is not None
        self.assertEqual(match.offset, offset)
        self.assertEqual(match.confidence, 1.0)
        self.assertEqual(match.candidates, 1)
        self.assertEqual(PAGE[match.offset : match.offset + len(match.text)], match.text)

    def test_survives_text_inserted_before_the_quote(self) -> None:
        """The whole point: an offset breaks here, an anchor does not."""
        offset = PAGE.index("Grid operators")
        anchor = build_anchor(PAGE, offset, len("Grid operators value predictability"))
        assert anchor is not None

        edited = "A NEW OPENING PARAGRAPH WAS ADDED HERE. " + PAGE
        match = locate_anchor(edited, anchor)
        assert match is not None
        self.assertEqual(
            edited[match.offset : match.offset + len(match.text)],
            "Grid operators value predictability",
        )
        self.assertNotEqual(match.offset, anchor.offset_hint)

    def test_context_disambiguates_repeated_text(self) -> None:
        page = (
            "Alpha section. The result was positive. Beta notes here. "
            "Gamma section. The result was positive. Delta notes here."
        )
        second = page.index("The result was positive", page.index("Gamma"))
        anchor = build_anchor(page, second, len("The result was positive"))
        assert anchor is not None

        match = locate_anchor(page, anchor)
        assert match is not None
        self.assertEqual(match.offset, second)
        self.assertEqual(match.candidates, 2)
        self.assertGreater(match.confidence, 0.5)

    def test_missing_quote_reports_failure_instead_of_guessing(self) -> None:
        anchor = build_anchor(PAGE, PAGE.index("Costs remain"), 12)
        assert anchor is not None
        self.assertIsNone(locate_anchor("An entirely different document.", anchor))
        self.assertIsNone(locate_anchor("", anchor))

    def test_rewrapped_whitespace_still_matches_with_lower_confidence(self) -> None:
        anchor = build_anchor(PAGE, PAGE.index("Grid operators"), 34)
        assert anchor is not None
        rewrapped = PAGE.replace(" ", "\n   ")
        match = locate_anchor(rewrapped, anchor)
        assert match is not None
        self.assertLess(match.confidence, 1.0)
        self.assertGreater(match.confidence, 0.0)

    def test_bad_input_is_handled(self) -> None:
        anchor = build_anchor(PAGE, 0, 10)
        assert anchor is not None
        self.assertIsNone(locate_anchor(None, anchor))  # type: ignore[arg-type]
        self.assertIsNone(locate_anchor(PAGE, None))  # type: ignore[arg-type]
        self.assertIsNone(locate_anchor(PAGE, QuoteAnchor(exact="")))


class SerializationTests(unittest.TestCase):
    def test_round_trips_through_a_dict(self) -> None:
        anchor = build_anchor(PAGE, PAGE.index("The MeyGen"), 16)
        assert anchor is not None
        restored = QuoteAnchor.from_dict(anchor.to_dict())
        self.assertEqual(restored, anchor)

    def test_malformed_stored_data_fails_closed(self) -> None:
        for value in (None, [], "text", {}, {"exact": ""}, {"exact": 5}, {"exact": "  "}):
            with self.subTest(value=value):
                self.assertIsNone(QuoteAnchor.from_dict(value))

    def test_partial_data_recovers_with_safe_defaults(self) -> None:
        restored = QuoteAnchor.from_dict({"exact": "hello", "offset_hint": -9})
        assert restored is not None
        self.assertEqual(restored.prefix, "")
        self.assertEqual(restored.suffix, "")
        self.assertEqual(restored.offset_hint, -1)


class SummaryIntegrationTests(unittest.TestCase):
    """Anchors compose with the on-device summarizer's verbatim bullets."""

    def test_every_summary_bullet_can_be_anchored_and_relocated(self) -> None:
        summary = summarize(PAGE)
        self.assertTrue(summary.bullets)
        for bullet in summary.bullets:
            with self.subTest(bullet=bullet.text[:40]):
                anchor = build_anchor(
                    summary.source_text, bullet.offset, len(bullet.text)
                )
                assert anchor is not None
                self.assertEqual(anchor.exact, bullet.text)

                match = locate_anchor(summary.source_text, anchor)
                assert match is not None
                self.assertEqual(match.offset, bullet.offset)

    def test_bullets_relocate_in_an_edited_copy_of_the_page(self) -> None:
        summary = summarize(PAGE)
        anchors = [
            build_anchor(summary.source_text, bullet.offset, len(bullet.text))
            for bullet in summary.bullets
        ]
        edited = "Editor's note added later.\n\n" + summary.source_text
        for anchor in anchors:
            assert anchor is not None
            with self.subTest(quote=anchor.exact[:40]):
                match = locate_anchor(edited, anchor)
                assert match is not None
                self.assertEqual(
                    edited[match.offset : match.offset + len(match.text)], anchor.exact
                )


class CursorMappingTests(unittest.TestCase):
    """The Find-in-Page button acts on whichever quote the cursor is in."""

    class FakeCursor:
        def __init__(self, position: int) -> None:
            self._position = position

        def position(self) -> int:
            return self._position

    class FakeOutput:
        def __init__(self, position: int) -> None:
            self._position = position

        def textCursor(self) -> object:
            return CursorMappingTests.FakeCursor(self._position)

    class ExplodingOutput:
        def textCursor(self) -> object:
            raise RuntimeError("widget already destroyed")

    def setUp(self) -> None:
        from main import OctoBrowse

        self.resolve = OctoBrowse._anchor_under_cursor
        self.rendered = "• First quoted line.\n• Second quoted line.\n"
        self.anchors = [
            QuoteAnchor(exact="First quoted line."),
            QuoteAnchor(exact="Second quoted line."),
        ]

    def test_cursor_inside_a_quote_selects_it(self) -> None:
        inside_second = self.rendered.index("Second quoted line.") + 3
        anchor = self.resolve(
            self.rendered, self.FakeOutput(inside_second), self.anchors
        )
        assert anchor is not None
        self.assertEqual(anchor.exact, "Second quoted line.")

    def test_cursor_outside_every_quote_selects_nothing(self) -> None:
        self.assertIsNone(
            self.resolve(self.rendered, self.FakeOutput(0), self.anchors)
        )

    def test_no_anchors_selects_nothing(self) -> None:
        self.assertIsNone(self.resolve(self.rendered, self.FakeOutput(5), []))

    def test_a_dead_widget_does_not_raise(self) -> None:
        self.assertIsNone(
            self.resolve(self.rendered, self.ExplodingOutput(), self.anchors)
        )


if __name__ == "__main__":
    unittest.main()

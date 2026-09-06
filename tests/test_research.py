from __future__ import annotations

import unittest
from unittest.mock import patch

import octobrowse.research as research_module
from octobrowse.research import (
    RESEARCH_NOTE_VERSION,
    make_research_note,
    normalize_research_notes,
    research_note_to_markdown,
    workspace_research_to_markdown,
)
from octobrowse.quote_anchor import QuoteAnchor


class ResearchNoteTests(unittest.TestCase):
    def test_quote_anchors_survive_normalization_and_json_roundtrip(self) -> None:
        import json

        quote = "Long evidence " + "word " * 160 + "ending."
        anchor = QuoteAnchor(quote, "before ", " after", 12).to_dict()
        note = make_research_note("https://example.test/", "Evidence", quote, "Commentary", anchors=[anchor])
        restored = normalize_research_notes(json.loads(json.dumps([note])))[0]
        self.assertEqual(restored["anchors"], [anchor])
        self.assertEqual(len(restored["anchors"][0]["exact"]), len(quote))

    def test_summary_anchors_must_reference_retained_content(self) -> None:
        note = make_research_note(
            "https://example.test/", "Summary", "", "First quote.\nSecond quote.",
            anchors=[
                QuoteAnchor("First quote.").to_dict(),
                QuoteAnchor("Second quote.").to_dict(),
                QuoteAnchor("Not in summary.").to_dict(),
                QuoteAnchor("First quote.").to_dict(),
            ],
        )
        self.assertEqual([item["exact"] for item in note["anchors"]], ["First quote.", "Second quote."])
        note["body"] = "Rewritten commentary."
        self.assertNotIn("anchors", normalize_research_notes([note])[0])

    def test_malformed_anchors_cannot_bloat_a_note_or_certify_a_prefix(self) -> None:
        note = make_research_note(
            "https://example.test/", "Selection", "Full quote with changed tail.", "",
            anchors=[None, {"exact": "Full quote"}, {"exact": "x" * 8001}],
        )
        self.assertNotIn("anchors", note)
        note = make_research_note(
            "https://example.test/", "Quote", "Evidence", "",
            anchors=[QuoteAnchor("Evidence", "a" * 200, "b" * 200, True).to_dict()],
        )
        stored = note["anchors"][0]
        self.assertEqual(len(stored["prefix"]), 48)
        self.assertEqual(len(stored["suffix"]), 48)
        self.assertEqual(stored["offset_hint"], -1)

    def test_anchor_count_is_bounded(self) -> None:
        quotes = [f"Quote {index}." for index in range(20)]
        note = make_research_note(
            "https://example.test/", "Summary", "", "\n".join(quotes),
            anchors=[QuoteAnchor(quote).to_dict() for quote in quotes],
        )
        self.assertEqual(len(note["anchors"]), 12)

    def test_make_note_produces_stable_versioned_schema(self) -> None:
        first = make_research_note(
            " https://example.test/paper ",
            "  Useful   paper  ",
            " quoted line ",
            " analysis ",
            kind="page",
            now=123.25,
        )
        second = make_research_note(
            " https://example.test/paper ",
            "  Useful   paper  ",
            " quoted line ",
            " analysis ",
            kind="page",
            now=123.25,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "version",
                "id",
                "url",
                "title",
                "quote",
                "body",
                "kind",
                "created_at",
                "updated_at",
            },
        )
        self.assertEqual(first["version"], RESEARCH_NOTE_VERSION)
        self.assertTrue(first["id"].startswith("note-"))
        self.assertEqual(first["url"], "https://example.test/paper")
        self.assertEqual(first["title"], "Useful paper")
        self.assertEqual(first["created_at"], 123.25)
        self.assertEqual(first["updated_at"], 123.25)

    def test_custom_identifier_and_kind_are_normalized(self) -> None:
        note = make_research_note(
            "",
            "Freeform",
            "",
            "A standalone thought",
            kind=" AI Summary ",
            now=5,
            note_id=" custom id / unsafe ",
        )

        self.assertEqual(note["id"], "custom-id-unsafe")
        self.assertEqual(note["kind"], "ai-summary")

    def test_note_requires_content_and_supported_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "quoted text or a note body"):
            make_research_note("https://example.test", "Empty", "", "", now=1)
        with self.assertRaises(ValueError):
            make_research_note("", "Bad time", "", "body", now=float("inf"))
        with self.assertRaises(ValueError):
            make_research_note("", "Bad time", "", "body", now=-1)

    def test_legacy_mapping_and_tuple_records_are_migrated(self) -> None:
        modern = make_research_note(
            "https://modern.example",
            "Modern",
            "quote",
            "body",
            kind="selection",
            now=10,
            note_id="modern-note",
        )

        normalized = normalize_research_notes(
            [
                {"url": "https://legacy.example", "note": " Legacy body "},
                ("https://tuple.example", " Tuple body "),
                modern,
            ],
            now=50,
        )

        self.assertEqual(len(normalized), 3)
        self.assertEqual(normalized[0]["body"], "Legacy body")
        self.assertEqual(normalized[0]["kind"], "page")
        self.assertEqual(normalized[0]["created_at"], 50)
        self.assertEqual(normalized[1]["url"], "https://tuple.example")
        self.assertEqual(normalized[1]["body"], "Tuple body")
        self.assertEqual(normalized[2], modern)

    def test_normalization_preserves_ids_and_timestamps_across_round_trips(
        self,
    ) -> None:
        legacy = [
            {"url": "https://same.example", "note": "Duplicate"},
            {"url": "https://same.example", "note": "Duplicate"},
        ]

        first = normalize_research_notes(legacy, now=100)
        repeated_migration = normalize_research_notes(legacy, now=100)
        round_trip = normalize_research_notes(first, now=999)

        self.assertEqual(first, repeated_migration)
        self.assertEqual(first, round_trip)
        self.assertNotEqual(first[0]["id"], first[1]["id"])
        self.assertEqual(first[0]["created_at"], 100)
        self.assertEqual(first[0]["updated_at"], 100)

    def test_existing_updated_time_cannot_precede_creation(self) -> None:
        normalized = normalize_research_notes(
            [
                {
                    "id": "timed",
                    "body": "Body",
                    "created_at": 20,
                    "updated_at": 10,
                }
            ],
            now=100,
        )

        self.assertEqual(normalized[0]["created_at"], 20)
        self.assertEqual(normalized[0]["updated_at"], 20)

    def test_note_count_and_all_text_fields_are_bounded(self) -> None:
        values = [
            {
                "url": "https://example.test/" + str(index) * 40,
                "title": f"title-{index}-long",
                "quote": "q" * 20,
                "body": "b" * 20,
            }
            for index in range(3)
        ]
        with (
            patch.object(research_module, "MAX_RESEARCH_NOTES", 2),
            patch.object(research_module, "MAX_NOTE_URL_CHARS", 12),
            patch.object(research_module, "MAX_NOTE_TITLE_CHARS", 7),
            patch.object(research_module, "MAX_NOTE_QUOTE_CHARS", 6),
            patch.object(research_module, "MAX_NOTE_BODY_CHARS", 8),
            patch.object(research_module, "MAX_NOTE_CONTENT_CHARS", 10),
        ):
            normalized = normalize_research_notes(values, now=1)

        self.assertEqual(len(normalized), 2)
        self.assertTrue(normalized[0]["title"].startswith("title-1"))
        for note in normalized:
            self.assertLessEqual(len(note["url"]), 12)
            self.assertLessEqual(len(note["title"]), 7)
            self.assertLessEqual(len(note["quote"]), 6)
            self.assertLessEqual(len(note["body"]), 8)
            self.assertLessEqual(len(note["quote"]) + len(note["body"]), 10)

    def test_malformed_records_are_dropped_without_stringification(self) -> None:
        normalized = normalize_research_notes(
            [
                None,
                "not a note",
                {"url": "https://empty.example", "note": ""},
                {"url": "https://numeric.example", "note": 42},
                {"url": "https://quote.example", "quote": "Valid quote"},
            ],
            now=1,
        )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["url"], "https://quote.example")
        self.assertEqual(normalized[0]["quote"], "Valid quote")

    def test_markdown_keeps_every_quote_line_inside_a_safe_block(self) -> None:
        note = make_research_note(
            "https://example.test/a>b",
            "Unsafe [title]",
            "first\n\n# heading\n> nested\n<script>",
            "Body with <script>alert(1)</script>",
            now=0,
        )

        markdown = research_note_to_markdown(note)

        self.assertIn("# Unsafe \\[title\\]", markdown)
        self.assertIn("> first\n>\n> # heading\n> &gt; nested", markdown)
        self.assertIn("> &lt;script&gt;", markdown)
        self.assertIn("Body with &lt;script&gt;alert(1)&lt;/script&gt;", markdown)
        self.assertIn("a%3Eb", markdown)
        self.assertNotIn("<script>", markdown)

    def test_legacy_markdown_export_is_deterministic(self) -> None:
        legacy = {"url": "https://example.test", "note": "Legacy export"}

        first = research_note_to_markdown(legacy)
        second = research_note_to_markdown(legacy)

        self.assertEqual(first, second)
        self.assertIn("1970-01-01T00:00:00Z", first)

    def test_workspace_export_includes_only_notes_for_workspace_urls(self) -> None:
        workspace = {
            "name": "Project [Atlas]",
            "tabs": [
                {
                    "title": "Paper",
                    "url": "https://Example.TEST/paper#section",
                },
                {
                    "title": "Dataset",
                    "url": "https://data.example.test/set",
                },
            ],
        }
        notes = [
            make_research_note(
                "https://example.test/paper",
                "Matching note",
                "Evidence",
                "Included body",
                now=1,
            ),
            make_research_note(
                "https://data.example.test/set#row-2",
                "Dataset note",
                "",
                "Also included",
                now=2,
            ),
            make_research_note(
                "https://unrelated.example.test",
                "Unrelated",
                "",
                "Excluded body",
                now=3,
            ),
            make_research_note(
                "",
                "Freeform",
                "",
                "No source URL",
                now=4,
            ),
        ]

        markdown = workspace_research_to_markdown(workspace, notes)

        self.assertIn("# Project \\[Atlas\\]", markdown)
        self.assertIn("Saved tabs: 2", markdown)
        self.assertIn("### Matching note", markdown)
        self.assertIn("Included body", markdown)
        self.assertIn("### Dataset note", markdown)
        self.assertIn("Also included", markdown)
        self.assertNotIn("Excluded body", markdown)
        self.assertNotIn("No source URL", markdown)

    def test_workspace_export_handles_no_matches_and_rejects_bad_workspace(
        self,
    ) -> None:
        workspace = {
            "name": "Empty research",
            "tabs": [{"url": "https://example.test", "title": "Example"}],
        }

        markdown = workspace_research_to_markdown(workspace, [])

        self.assertIn("_No research notes match this workspace._", markdown)
        with self.assertRaisesRegex(ValueError, "Invalid workspace"):
            workspace_research_to_markdown({"name": "No tabs", "tabs": []}, [])
        with self.assertRaisesRegex(ValueError, "Invalid research note"):
            research_note_to_markdown({"url": "https://example.test", "note": ""})


if __name__ == "__main__":
    unittest.main()

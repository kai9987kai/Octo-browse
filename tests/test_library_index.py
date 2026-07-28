from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import octobrowse.library_index as library_module
from octobrowse.library_index import (
    LibraryIndex,
    LibraryRecord,
    LibrarySearchResult,
    build_library_records,
)


class LibraryIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_rebuild_indexes_every_browser_collection_with_typed_results(
        self,
    ) -> None:
        with LibraryIndex() as index:
            count = index.rebuild(
                tabs=[
                    {
                        "title": "Current research",
                        "url": "https://tabs.example/current",
                        "tab_index": 7,
                    }
                ],
                history=[
                    {
                        "title": "Visited paper",
                        "url": "https://history.example/paper",
                    }
                ],
                bookmarks=["https://bookmarks.example/saved"],
                reading_list=["https://reading.example/later"],
                notes=[
                    {
                        "url": "https://notes.example/source",
                        "note": "Quantum materials observation",
                    }
                ],
                todos=["Review the experiment"],
                workspaces=[
                    {
                        "id": "workspace-atlas",
                        "name": "Project Atlas",
                        "tabs": [
                            {
                                "title": "Hidden workspace evidence",
                                "url": "https://workspace.example/evidence",
                            }
                        ],
                    }
                ],
            )

            results = index.search("", limit=20)

            self.assertEqual(count, 7)
            self.assertEqual(
                [result.kind for result in results],
                [
                    "Tab",
                    "History",
                    "Bookmark",
                    "Reading",
                    "Note",
                    "Task",
                    "Workspace",
                ],
            )
            self.assertTrue(
                all(isinstance(result, LibrarySearchResult) for result in results)
            )
            self.assertEqual(results[0].source_id, "7")
            self.assertEqual(results[0].record_type, "Tab")

            note = index.search("quantum")[0]
            workspace = index.search("hidden evidence")[0]
            self.assertEqual(note.url, "https://notes.example/source")
            self.assertIn("Quantum materials", note.snippet)
            self.assertEqual(workspace.kind, "Workspace")
            self.assertEqual(workspace.source_id, "workspace-atlas")

    def test_exact_and_title_prefix_matches_rank_deterministically(self) -> None:
        records = [
            LibraryRecord("Note", "Unrelated", snippet="alpha appears later"),
            LibraryRecord("Note", "Alphabet Soup"),
            LibraryRecord("Note", "Alpha Beta"),
            LibraryRecord("Note", "Alpha"),
        ]
        with LibraryIndex() as index:
            index.rebuild(records)

            first = index.search("alpha")
            second = index.search("alpha")

        expected = ["Alpha", "Alphabet Soup", "Alpha Beta", "Unrelated"]
        self.assertEqual([result.title for result in first], expected)
        self.assertEqual(first, second)

    def test_user_punctuation_and_quotes_never_become_fts_syntax(self) -> None:
        records = [
            LibraryRecord("Note", "Alpha Beta Reference"),
            LibraryRecord("Note", "NEAR Operator Guide"),
            LibraryRecord("Note", "C++ Browser Notes"),
        ]
        with LibraryIndex() as index:
            index.rebuild(records)

            quoted = index.search('"Alpha Beta"!!!')
            near_syntax = index.search('NEAR("Operator")')
            punctuation_name = index.search("C++")
            punctuation_only = index.search('""" () : ***')
            unterminated = index.search('"unterminated')

        self.assertEqual(quoted[0].title, "Alpha Beta Reference")
        self.assertEqual(near_syntax[0].title, "NEAR Operator Guide")
        self.assertEqual(punctuation_name[0].title, "C++ Browser Notes")
        self.assertEqual(punctuation_only, ())
        self.assertEqual(unterminated, ())

    def test_like_fallback_has_the_same_safe_prefix_ranking(self) -> None:
        with LibraryIndex(enable_fts=False) as index:
            self.assertFalse(index.fts_enabled)
            index.rebuild(
                [
                    LibraryRecord("Note", "Prefix Extended"),
                    LibraryRecord("Note", "Prefix"),
                    LibraryRecord("Note", "Elsewhere", snippet="prefix detail"),
                ]
            )

            results = index.search('"prefix":*')

        self.assertEqual(
            [result.title for result in results],
            ["Prefix", "Prefix Extended", "Elsewhere"],
        )

    def test_runtime_fts_failure_falls_back_to_like(self) -> None:
        with LibraryIndex() as index:
            index.rebuild([LibraryRecord("Note", "Fallback Target")])
            if index.fts_enabled:
                with index._connection:
                    index._connection.execute("DROP TABLE library_records_fts")

            results = index.search("fallback")

            self.assertEqual(results[0].title, "Fallback Target")
            self.assertFalse(index.fts_enabled)

    def test_failed_rebuild_rolls_back_to_previous_complete_index(self) -> None:
        with LibraryIndex() as index:
            index.rebuild([LibraryRecord("Note", "Original record")])
            with index._connection:
                index._connection.execute(
                    """
                    CREATE TRIGGER reject_rebuild
                    BEFORE INSERT ON library_records
                    WHEN NEW.title = 'Rejected record'
                    BEGIN
                        SELECT RAISE(ABORT, 'test rejection');
                    END
                    """
                )

            with self.assertRaises(sqlite3.IntegrityError):
                index.rebuild([LibraryRecord("Note", "Rejected record")])

            self.assertEqual(index.search("original")[0].title, "Original record")
            self.assertEqual(index.search("rejected"), ())

    def test_input_fields_record_count_query_and_results_are_capped(self) -> None:
        with (
            patch.object(library_module, "MAX_LIBRARY_RECORDS", 3),
            patch.object(library_module, "MAX_TITLE_CHARS", 8),
            patch.object(library_module, "MAX_URL_CHARS", 12),
            patch.object(library_module, "MAX_INDEXED_TEXT_CHARS", 10),
        ):
            records = build_library_records(
                bookmarks=["https://example.test/a-very-long-path"],
                todos=["abcdefghijklm", "second task", "third task", "fourth task"],
            )

        self.assertEqual(len(records), 3)
        self.assertLessEqual(len(records[0].title), 8)
        self.assertLessEqual(len(records[0].url), 12)
        self.assertLessEqual(len(records[1].snippet), 10)

        with LibraryIndex() as index:
            index.rebuild(
                [LibraryRecord("Task", f"alpha task {number}") for number in range(5)]
            )
            with (
                patch.object(library_module, "MAX_QUERY_CHARS", 5),
                patch.object(library_module, "MAX_SEARCH_RESULTS", 2),
            ):
                results = index.search("alpha impossible trailing input", limit=999)

        self.assertEqual(len(results), 2)
        self.assertTrue(all("alpha" in result.title for result in results))

    def test_result_snippet_is_bounded_and_centered_on_the_match(self) -> None:
        text = ("before " * 100) + "needle evidence " + ("after " * 100)
        with LibraryIndex() as index:
            index.rebuild([LibraryRecord("Note", "Long note", snippet=text)])
            with patch.object(
                library_module, "MAX_RESULT_SNIPPET_CHARS", 60
            ):
                result = index.search("needle")[0]

        self.assertLessEqual(len(result.snippet), 60)
        self.assertIn("needle", result.snippet)
        self.assertTrue(result.snippet.startswith("..."))
        self.assertTrue(result.snippet.endswith("..."))

    def test_file_index_persists_and_can_reopen_in_like_mode(self) -> None:
        database_path = self.root / "library.sqlite"
        with LibraryIndex(database_path) as index:
            index.rebuild(
                [
                    LibraryRecord(
                        "Bookmark",
                        "Persistent item",
                        url="https://example.test/persistent",
                    )
                ]
            )

        with LibraryIndex(database_path, enable_fts=False) as reopened:
            result = reopened.search("persistent")[0]
            reopened.rebuild([LibraryRecord("Task", "Updated in fallback mode")])

        self.assertEqual(result.kind, "Bookmark")
        self.assertEqual(result.url, "https://example.test/persistent")

        with LibraryIndex(database_path) as resynchronized:
            self.assertEqual(
                resynchronized.search("updated")[0].title,
                "Updated in fallback mode",
            )
            self.assertEqual(resynchronized.search("persistent"), ())

    def test_malformed_source_values_are_skipped_without_stringifying_them(
        self,
    ) -> None:
        records = build_library_records(
            tabs=[None, "not-a-tab", {"title": "", "url": ""}],
            history=[{}, {"url": "https://valid.example", "title": ""}],
            bookmarks=[None, 42, "https://bookmark.example"],
            notes=[{"url": "https://note.example"}, "not-a-note"],
            todos=[None, {"text": "Valid task"}],
            workspaces=[{"name": "", "tabs": []}, None],
        )

        self.assertEqual(
            [(record.kind, record.title) for record in records],
            [
                ("History", "https://valid.example"),
                ("Bookmark", "https://bookmark.example"),
                ("Task", "Valid task"),
            ],
        )

    def test_zero_limit_and_non_word_queries_return_no_results(self) -> None:
        with LibraryIndex() as index:
            index.rebuild([LibraryRecord("Task", "One item")])

            self.assertEqual(index.search("one", limit=0), ())
            self.assertEqual(index.search("***"), ())


if __name__ == "__main__":
    unittest.main()

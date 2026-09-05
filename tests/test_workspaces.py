from __future__ import annotations

import unittest
import time
from copy import deepcopy

from octobrowse.workspaces import (
    MAX_WORKSPACE_ID_CHARS,
    MAX_WORKSPACE_TABS,
    MAX_WORKSPACE_TIMESTAMP,
    MAX_WORKSPACE_URL_CHARS,
    make_workspace,
    normalize_workspaces,
    workspace_to_markdown,
)


class WorkspaceTests(unittest.TestCase):
    def test_make_and_normalize_workspace(self) -> None:
        workspace = make_workspace(
            "  Project   Atlas  ",
            [{"url": "https://example.com", "title": "Example"}],
            active_index=99,
            now=123.0,
            identifier="atlas",
        )
        self.assertEqual(workspace["name"], "Project Atlas")
        self.assertEqual(workspace["active_index"], 0)
        self.assertEqual(normalize_workspaces([workspace]), [workspace])

    def test_malformed_records_are_dropped(self) -> None:
        self.assertEqual(normalize_workspaces(None), [])
        self.assertEqual(normalize_workspaces([{}, {"name": "No tabs", "tabs": []}]), [])

    def test_markdown_export(self) -> None:
        workspace = make_workspace(
            "Research",
            [{"url": "https://example.com/paper", "title": "A [useful] paper"}],
            now=1.0,
        )
        rendered = workspace_to_markdown(workspace)
        self.assertIn("# Research", rendered)
        self.assertIn("[A \\[useful\\] paper](<https://example.com/paper>)", rendered)

    def test_malformed_tab_fields_do_not_become_destinations_or_pins(self) -> None:
        workspace = make_workspace(
            "Research",
            [
                {"url": None},
                {"url": 123},
                {"url": ["https://invalid.example"]},
                {"url": "https://bad.example/\nsecond-line"},
                {"url": "https://one.example", "title": None, "pinned": "false"},
                {"url": "https://two.example", "title": " A\x00 B\nC ", "pinned": True},
            ],
            now=1.0,
        )

        self.assertEqual(
            workspace["tabs"],
            [
                {"url": "https://one.example", "title": "", "pinned": False},
                {"url": "https://two.example", "title": "A B C", "pinned": True},
            ],
        )

    def test_selected_tab_is_remapped_after_invalid_earlier_records(self) -> None:
        values = [
            None,
            {"url": "https://one.example"},
            {"url": "https://selected.example"},
            {"url": "https://last.example"},
        ]
        workspace = make_workspace("Selection", values, active_index=2, now=1.0)
        persisted = normalize_workspaces([{"name": "Selection", "tabs": values, "active_index": 2}])[0]

        for result in (workspace, persisted):
            self.assertEqual(result["active_index"], 1)
            self.assertEqual(result["tabs"][result["active_index"]]["url"], "https://selected.example")

    def test_removed_selected_tab_uses_previous_surviving_tab(self) -> None:
        workspace = make_workspace(
            "Selection",
            [{"url": "https://one.example"}, None, {"url": "https://last.example"}],
            active_index=1,
            now=1.0,
        )
        self.assertEqual(workspace["active_index"], 0)

    def test_tab_limit_counts_valid_records_and_clamps_selection(self) -> None:
        values = [None] * MAX_WORKSPACE_TABS + [
            {"url": f"https://example.com/{index}"} for index in range(MAX_WORKSPACE_TABS + 5)
        ]
        workspace = make_workspace("Limit", values, active_index=len(values), now=1.0)

        self.assertEqual(len(workspace["tabs"]), MAX_WORKSPACE_TABS)
        self.assertEqual(workspace["active_index"], MAX_WORKSPACE_TABS - 1)

    def test_long_urls_are_dropped_instead_of_changing_their_destination(self) -> None:
        long_url = "https://example.com/" + "a" * MAX_WORKSPACE_URL_CHARS
        workspace = make_workspace(
            "Bounds",
            [{"url": long_url}, {"url": "https://kept.example", "title": "a" * 300}],
            now=1.0,
            identifier="id" * 100,
        )
        self.assertEqual(len(workspace["tabs"]), 1)
        self.assertEqual(workspace["tabs"][0]["url"], "https://kept.example")
        self.assertEqual(len(workspace["tabs"][0]["title"]), 240)
        self.assertEqual(len(workspace["id"]), MAX_WORKSPACE_ID_CHARS)

    def test_nonfinite_and_out_of_range_state_recovers_without_crashing(self) -> None:
        for invalid in (float("inf"), float("-inf"), float("nan"), "bad", {}, 10**1000):
            with self.subTest(invalid_type=type(invalid).__name__):
                workspace = normalize_workspaces(
                    [{
                        "name": "Recovery",
                        "tabs": [{"url": "https://example.com"}],
                        "active_index": invalid,
                        "created_at": invalid,
                        "updated_at": invalid,
                    }]
                )[0]
                self.assertEqual(workspace["active_index"], 0)
                self.assertEqual(workspace["created_at"], 0.0)
                self.assertEqual(workspace["updated_at"], 0.0)
                time.strftime("%Y-%m-%d %H:%M", time.localtime(workspace["updated_at"]))

    def test_creation_rejects_invalid_times_with_a_clear_value_error(self) -> None:
        for invalid in (float("inf"), float("nan"), -1.0, MAX_WORKSPACE_TIMESTAMP + 1, 10**1000, True):
            with self.subTest(invalid_type=type(invalid).__name__):
                with self.assertRaisesRegex(ValueError, "timestamp"):
                    make_workspace("Invalid", [{"url": "https://example.com"}], now=invalid)

    def test_persisted_timestamps_preserve_zero_and_recover_in_order(self) -> None:
        template = {"name": "Timestamp", "tabs": [{"url": "https://example.com"}]}
        records = normalize_workspaces(
            [
                {**template, "created_at": 0.0, "updated_at": 123.0},
                {**template, "created_at": 123.0, "updated_at": 1.0},
                {**template, "created_at": "bad", "updated_at": 123.0},
                {**template, "created_at": MAX_WORKSPACE_TIMESTAMP, "updated_at": MAX_WORKSPACE_TIMESTAMP},
            ]
        )
        self.assertEqual((records[0]["created_at"], records[0]["updated_at"]), (0.0, 123.0))
        self.assertEqual((records[1]["created_at"], records[1]["updated_at"]), (123.0, 123.0))
        self.assertEqual((records[2]["created_at"], records[2]["updated_at"]), (123.0, 123.0))
        for workspace in records:
            self.assertGreaterEqual(workspace["created_at"], 0.0)
            self.assertLessEqual(workspace["updated_at"], MAX_WORKSPACE_TIMESTAMP)
            time.localtime(workspace["updated_at"])

    def test_duplicate_ids_are_unique_bounded_stable_and_preserve_later_ids(self) -> None:
        template = {"name": "IDs", "tabs": [{"url": "https://example.com"}], "created_at": 1.0}
        records = normalize_workspaces(
            [{**template, "id": identifier} for identifier in ("same", "same", "same-2", "same")]
        )
        self.assertEqual([item["id"] for item in records], ["same", "same-3", "same-2", "same-4"])
        self.assertEqual(normalize_workspaces(records), records)

        long_ids = normalize_workspaces([{**template, "id": "a" * 120}] * 3)
        self.assertEqual(len({item["id"] for item in long_ids}), 3)
        self.assertTrue(all(len(item["id"]) <= MAX_WORKSPACE_ID_CHARS for item in long_ids))

    def test_missing_id_does_not_steal_a_later_explicit_id(self) -> None:
        workspace = make_workspace("Generated", [{"url": "https://example.com"}], now=1.0)
        missing_id = {key: value for key, value in workspace.items() if key != "id"}
        normalized = normalize_workspaces([missing_id, workspace])
        self.assertNotEqual(normalized[0]["id"], workspace["id"])
        self.assertEqual(normalized[1]["id"], workspace["id"])
        self.assertEqual(normalize_workspaces(normalized), normalized)

    def test_invalid_names_and_collections_are_not_stringified(self) -> None:
        self.assertEqual(normalize_workspaces([{"name": None, "tabs": ["https://example.com"]}]), [])
        for invalid_tabs in (None, "https://example.com", {"url": "https://example.com"}):
            with self.subTest(invalid_tabs=invalid_tabs):
                with self.assertRaisesRegex(ValueError, "tab"):
                    make_workspace("Invalid", invalid_tabs, now=1.0)

    def test_normalization_does_not_mutate_caller_data(self) -> None:
        original = [{"name": " Normalized ", "tabs": [{"url": " https://example.com "}], "active_index": 100}]
        before = deepcopy(original)
        normalize_workspaces(original)
        self.assertEqual(original, before)

    def test_unpaired_unicode_surrogates_cannot_break_ids_or_export(self) -> None:
        workspace = normalize_workspaces(
            [{
                "name": "Saved \ud800 name",
                "tabs": [
                    {"url": "https://example.com/\udfff"},
                    {"url": "https://kept.example", "title": "Title \ud800"},
                ],
            }]
        )[0]
        self.assertEqual(len(workspace["tabs"]), 1)
        self.assertEqual(workspace["name"], "Saved \ufffd name")
        self.assertIn(b"https://kept.example", workspace_to_markdown(workspace).encode("utf-8"))

    def test_markdown_escapes_html_delimiters_and_dangerous_links(self) -> None:
        workspace = make_workspace(
            '<script>Workspace</script> *name*',
            [
                {"url": 'https://example.com/a<evil>\\[x]?a=1&copy=2', "title": '<img src=x> [label]\\'},
                {"url": "javascript:alert(1)", "title": "Run script"},
                {"url": "data:text/html,<script>alert(1)</script>", "title": "Embedded script"},
                {"url": "https://[broken", "title": "Malformed URL"},
            ],
            now=1.0,
        )
        rendered = workspace_to_markdown(workspace)
        self.assertIn("# &lt;script&gt;Workspace&lt;/script&gt; \\*name\\*", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("%3Cevil%3E%5C[x]?a=1&amp;copy=2", rendered)
        self.assertIn("&lt;img src=x&gt; \\[label\\]\\\\", rendered)
        self.assertNotIn("(<javascript:", rendered)
        self.assertNotIn("(<data:", rendered)
        self.assertNotIn("(<https://[broken", rendered)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from octobrowse.workspaces import make_workspace, normalize_workspaces, workspace_to_markdown


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


if __name__ == "__main__":
    unittest.main()

import unittest

from octobrowse.session import (
    MAX_SESSION_TABS,
    make_session_snapshot,
    normalize_session_snapshot,
)


class SessionSnapshotTests(unittest.TestCase):
    def test_make_snapshot_preserves_order_duplicates_and_tab_metadata(self) -> None:
        snapshot = make_session_snapshot(
            [
                {"url": " https://example.com ", "title": " Example ", "pinned": True},
                {"url": "https://example.com", "title": "Duplicate", "pinned": False},
                {"url": "https://openai.com", "title": "OpenAI"},
            ],
            active_index=1,
        )

        self.assertEqual(snapshot["version"], 2)
        self.assertEqual(snapshot["active_index"], 1)
        self.assertEqual(
            snapshot["tabs"],
            [
                {"url": "https://example.com", "title": "Example", "pinned": True},
                {"url": "https://example.com", "title": "Duplicate", "pinned": False},
                {"url": "https://openai.com", "title": "OpenAI", "pinned": False},
            ],
        )

    def test_legacy_url_list_is_upgraded_without_deduplication(self) -> None:
        snapshot = normalize_session_snapshot(
            [" https://example.com ", "", "https://example.com", None, 42]
        )

        self.assertEqual(
            snapshot,
            {
                "version": 2,
                "tabs": [
                    {"url": "https://example.com", "title": "", "pinned": False},
                    {"url": "https://example.com", "title": "", "pinned": False},
                ],
                "active_index": 0,
            },
        )

    def test_legacy_record_list_drops_invalid_records(self) -> None:
        snapshot = normalize_session_snapshot(
            [
                {"url": "https://one.example", "title": "One", "pinned": True},
                {"title": "Missing URL"},
                {"url": None, "title": "Bad URL"},
                {"url": "   "},
                {"url": "https://two.example", "title": None, "pinned": "true"},
            ]
        )

        self.assertEqual(
            snapshot["tabs"],
            [
                {"url": "https://one.example", "title": "One", "pinned": True},
                {"url": "https://two.example", "title": "", "pinned": False},
            ],
        )

    def test_active_index_is_remapped_when_earlier_records_are_invalid(self) -> None:
        snapshot = normalize_session_snapshot(
            {
                "version": 2,
                "tabs": [
                    {"title": "invalid"},
                    {"url": "https://one.example"},
                    {"url": "https://two.example"},
                ],
                "active_index": 2,
            }
        )

        self.assertEqual(snapshot["active_index"], 1)

    def test_versioned_snapshot_is_upgraded_and_active_index_is_clamped(self) -> None:
        high = normalize_session_snapshot(
            {
                "version": 1,
                "tabs": ["https://one.example", {"url": "https://two.example"}],
                "active_index": 99,
            }
        )
        low = normalize_session_snapshot(
            {"version": 2, "tabs": ["https://one.example"], "active_index": -5}
        )

        self.assertEqual(high["version"], 2)
        self.assertEqual(high["active_index"], 1)
        self.assertEqual(low["active_index"], 0)

    def test_invalid_active_index_and_empty_snapshot_recover(self) -> None:
        malformed = normalize_session_snapshot(
            {"version": 2, "tabs": ["https://example.com"], "active_index": "bad"}
        )
        empty = normalize_session_snapshot({"version": 2, "tabs": "not-a-list"})

        self.assertEqual(malformed["active_index"], 0)
        self.assertEqual(empty, {"version": 2, "tabs": [], "active_index": 0})
        self.assertEqual(normalize_session_snapshot(None), empty)

    def test_snapshot_caps_tabs_at_maximum(self) -> None:
        tabs = [
            {"url": f"https://example.com/{index}", "title": str(index), "pinned": False}
            for index in range(MAX_SESSION_TABS + 5)
        ]

        snapshot = make_session_snapshot(tabs, active_index=MAX_SESSION_TABS + 4)

        self.assertEqual(len(snapshot["tabs"]), MAX_SESSION_TABS)
        self.assertEqual(snapshot["tabs"][0]["url"], "https://example.com/0")
        self.assertEqual(
            snapshot["tabs"][-1]["url"], f"https://example.com/{MAX_SESSION_TABS - 1}"
        )
        self.assertEqual(snapshot["active_index"], MAX_SESSION_TABS - 1)

    def test_make_snapshot_accepts_iterables_and_does_not_mutate_input(self) -> None:
        original = [{"url": "https://example.com", "title": " Example ", "pinned": True}]

        snapshot = make_session_snapshot(iter(original), active_index=0)

        self.assertEqual(original[0]["title"], " Example ")
        self.assertEqual(snapshot["tabs"][0]["title"], "Example")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from types import SimpleNamespace

from PyQt6.QtCore import QUrl

from main import OctoBrowse


class _ExplodingBrowser:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"Late shutdown callback touched browser.{name}")


class ShutdownTests(unittest.TestCase):
    def test_late_url_change_is_ignored_during_shutdown(self) -> None:
        window = SimpleNamespace(shutting_down=True)

        OctoBrowse.update_url_bar(
            window,
            QUrl("https://www.google.com/"),
            _ExplodingBrowser(),
        )

    def test_late_site_content_change_is_ignored_during_shutdown(self) -> None:
        window = SimpleNamespace(shutting_down=True)

        OctoBrowse.apply_site_content(
            window,
            _ExplodingBrowser(),
            QUrl("https://www.google.com/"),
        )

    def test_late_title_change_is_ignored_during_shutdown(self) -> None:
        window = SimpleNamespace(shutting_down=True)

        OctoBrowse.update_tab_title(
            window,
            _ExplodingBrowser(),
            "Late page title",
        )

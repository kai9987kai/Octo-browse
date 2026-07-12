from __future__ import annotations

import unittest

from octobrowse.urls import can_dispatch_octo_command, is_internal_url


class UrlClassificationTests(unittest.TestCase):
    def test_real_internal_pages(self) -> None:
        for url in ("", "about:blank", "data:text/plain,x", "octo:dashboard", "https://octobrowse.local/"):
            with self.subTest(url=url):
                self.assertTrue(is_internal_url(url))

    def test_attacker_urls_are_not_internal(self) -> None:
        for url in (
            "https://evil.test/?next=octobrowse.local",
            "https://octobrowse.local.evil.test/",
            "https://evil.test/octobrowse.local",
            "http://octobrowse.local/",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_internal_url(url))

    def test_octo_bridge_requires_a_generated_internal_page(self) -> None:
        internal = "https://octobrowse.local/"
        self.assertTrue(can_dispatch_octo_command("octo:dashboard", "dashboard", internal))
        self.assertFalse(can_dispatch_octo_command("octo:settings", "", internal))
        self.assertFalse(
            can_dispatch_octo_command("https://example.com", "dashboard", internal)
        )
        self.assertFalse(
            can_dispatch_octo_command("octo:settings", "dashboard", "https://evil.test/")
        )


if __name__ == "__main__":
    unittest.main()

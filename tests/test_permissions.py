from __future__ import annotations

import unittest

from PyQt6.QtWebEngineCore import QWebEnginePermission

from main import OctoBrowse


class PermissionLifetimeTests(unittest.TestCase):
    def test_sensitive_capture_permissions_are_page_lifetime_only(self) -> None:
        for name in (
            "MediaAudioCapture",
            "MediaVideoCapture",
            "MediaAudioVideoCapture",
            "DesktopVideoCapture",
            "DesktopAudioVideoCapture",
            "MouseLock",
        ):
            permission_type = getattr(
                QWebEnginePermission.PermissionType, name, None
            )
            if permission_type is None:
                continue
            with self.subTest(name=name):
                self.assertFalse(
                    OctoBrowse._permission_is_persistent(permission_type)
                )

    def test_site_level_permissions_use_the_persistent_profile_store(self) -> None:
        for name in ("Notifications", "Geolocation"):
            permission_type = getattr(
                QWebEnginePermission.PermissionType, name
            )
            with self.subTest(name=name):
                self.assertTrue(
                    OctoBrowse._permission_is_persistent(permission_type)
                )

    def test_content_controls_use_separate_private_session_storage(self) -> None:
        browser = OctoBrowse.__new__(OctoBrowse)
        browser.site_content = {"standard.example": {"javascript": False}}
        browser.private_site_content = {"private.example": {"images": False}}

        class FakeBrowser:
            def __init__(self, private: bool) -> None:
                self.private = private

            def property(self, name: str) -> bool:
                return self.private if name == "private" else False

        standard = browser.site_content_for_browser(FakeBrowser(False))  # type: ignore[arg-type]
        private = browser.site_content_for_browser(FakeBrowser(True))  # type: ignore[arg-type]

        self.assertIs(standard, browser.site_content)
        self.assertIs(private, browser.private_site_content)
        self.assertNotIn("private.example", standard)
        self.assertNotIn("standard.example", private)


if __name__ == "__main__":
    unittest.main()

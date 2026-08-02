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


class FakePermission:
    """Minimal stand-in for Qt's QWebEnginePermission."""

    def __init__(self, permission_type: object, origin: object = None) -> None:
        self._permission_type = permission_type
        self._origin = origin
        self.granted = 0
        self.denied = 0

    def permissionType(self) -> object:
        return self._permission_type

    def origin(self) -> object:
        return self._origin

    def grant(self) -> None:
        self.granted += 1

    def deny(self) -> None:
        self.denied += 1


class BrokenPermission(FakePermission):
    def origin(self) -> object:
        raise RuntimeError("Qt origin lookup failed")


class PermissionRememberRuleTests(unittest.TestCase):
    def test_only_persistent_standard_decisions_are_remembered(self) -> None:
        self.assertTrue(OctoBrowse._permission_should_remember(False, True))
        self.assertFalse(OctoBrowse._permission_should_remember(True, True))
        self.assertFalse(OctoBrowse._permission_should_remember(False, False))
        self.assertFalse(OctoBrowse._permission_should_remember(True, False))

    def test_page_private_flag_is_authoritative(self) -> None:
        class Page:
            private = True

            def parent(self) -> object:
                # A stale/incorrect view says "not private"; the page wins.
                return None

        self.assertTrue(OctoBrowse._page_is_private(Page()))

    def test_unclassifiable_page_is_treated_as_private(self) -> None:
        class Page:
            def parent(self) -> object:
                return object()

        class ExplodingPage:
            def parent(self) -> object:
                raise RuntimeError("no parent")

        self.assertTrue(OctoBrowse._page_is_private(Page()))
        self.assertTrue(OctoBrowse._page_is_private(ExplodingPage()))


class PermissionRequestHandlingTests(unittest.TestCase):
    def make_browser(self) -> OctoBrowse:
        browser = OctoBrowse.__new__(OctoBrowse)
        browser.site_permissions = {}
        browser.statuses: list[str] = []
        browser.set_status = browser.statuses.append  # type: ignore[assignment]
        browser.saved = 0

        def save_settings() -> None:
            browser.saved += 1

        browser.save_settings = save_settings  # type: ignore[assignment]
        return browser

    def test_internal_failure_denies_instead_of_hanging(self) -> None:
        browser = self.make_browser()
        browser._decide_permission = lambda *a, **k: True  # type: ignore[assignment]
        permission = BrokenPermission(
            QWebEnginePermission.PermissionType.Geolocation
        )

        browser.handle_permission_request(None, permission)  # type: ignore[arg-type]

        self.assertEqual(permission.denied, 1)
        self.assertEqual(permission.granted, 0)
        self.assertTrue(browser.statuses)
        self.assertIn("internal error", browser.statuses[-1])

    def test_private_page_grant_is_never_written_to_settings(self) -> None:
        browser = self.make_browser()

        class PrivatePage:
            private = True

            def parent(self) -> object:
                return None

        recorded: list[bool] = []

        def decide(origin: object, feature_name: str, *, remember: bool) -> bool:
            recorded.append(remember)
            return True

        browser._decide_permission = decide  # type: ignore[assignment]
        permission = FakePermission(
            QWebEnginePermission.PermissionType.Geolocation, "https://private.example"
        )

        browser.handle_permission_request(PrivatePage(), permission)  # type: ignore[arg-type]

        self.assertEqual(recorded, [False])
        self.assertEqual(permission.granted, 1)
        self.assertEqual(browser.site_permissions, {})
        self.assertEqual(browser.saved, 0)

    def test_standard_persistent_grant_is_recorded(self) -> None:
        browser = self.make_browser()

        class StandardPage:
            private = False

            def parent(self) -> object:
                return None

        recorded: list[bool] = []

        def decide(origin: object, feature_name: str, *, remember: bool) -> bool:
            recorded.append(remember)
            return True

        browser._decide_permission = decide  # type: ignore[assignment]
        permission = FakePermission(
            QWebEnginePermission.PermissionType.Geolocation, "https://standard.example"
        )

        browser.handle_permission_request(StandardPage(), permission)  # type: ignore[arg-type]

        self.assertEqual(recorded, [True])
        self.assertEqual(permission.granted, 1)

    def test_denied_decision_denies_the_permission(self) -> None:
        browser = self.make_browser()

        class StandardPage:
            private = False

            def parent(self) -> object:
                return None

        browser._decide_permission = lambda *a, **k: False  # type: ignore[assignment]
        permission = FakePermission(
            QWebEnginePermission.PermissionType.Geolocation, "https://standard.example"
        )

        browser.handle_permission_request(StandardPage(), permission)  # type: ignore[arg-type]

        self.assertEqual(permission.denied, 1)
        self.assertEqual(permission.granted, 0)


if __name__ == "__main__":
    unittest.main()

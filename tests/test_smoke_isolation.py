from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main as app_module
from main import BrowserSettings, IsolatedSettingsStore, SettingsStore


class SmokeIsolationTests(unittest.TestCase):
    def save_state(self, store: SettingsStore) -> None:
        store.save(
            BrowserSettings(
                openai_api_key="do-not-store-openai",
                weather_api_key="do-not-store-weather",
                news_api_key="do-not-store-news",
            ),
            ["https://saved.example"], [], [], [], [], {}, {}, [], {}, [],
        )

    def test_isolated_store_ignores_environment_vault_and_legacy_state(self) -> None:
        environment = {
            "OPENAI_API_KEY": "ambient-openai-canary",
            "OPENWEATHER_API_KEY": "ambient-weather-canary",
            "NEWS_API_KEY": "ambient-news-canary",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = root / "octobrowse_settings.json"
            legacy_payload = json.dumps({
                "openai_key": "legacy-canary",
                "bookmarks": ["https://legacy-private.example"],
                "homepage": "https://legacy-private.example",
            })
            legacy.write_text(legacy_payload, encoding="utf-8")
            with (
                patch.dict(os.environ, environment),
                patch("main.Path.cwd", return_value=root),
                patch("main.CredentialStore.get", side_effect=AssertionError("vault read")),
                patch("main.CredentialStore.set", side_effect=AssertionError("vault write")),
                patch("main.QStandardPaths.writableLocation", side_effect=AssertionError("user settings")),
            ):
                store = IsolatedSettingsStore(root / "isolated")
                loaded = store.load()
                settings = loaded[0]
                self.assertEqual(
                    (settings.openai_api_key, settings.weather_api_key, settings.news_api_key), ("", "", ""),
                )
                self.assertEqual(loaded[2], [])
                self.assertEqual(settings.homepage, app_module.DEFAULT_HOMEPAGE)
                self.save_state(store)
                saved = json.loads(store.path.read_text(encoding="utf-8"))
                self.assertEqual(saved["bookmarks"], ["https://saved.example"])
                for key in ("openai_api_key", "weather_api_key", "news_api_key"):
                    self.assertEqual(saved[key], "")
                self.assertNotIn("canary", store.path.read_text(encoding="utf-8"))
                self.assertEqual(legacy.read_text(encoding="utf-8"), legacy_payload)
            for name, value in environment.items():
                self.assertNotEqual(os.environ.get(name), value)

    def test_isolated_store_ignores_secrets_even_in_its_own_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = IsolatedSettingsStore(temp)
            store.path.write_text(json.dumps({
                "openai_api_key": "stored-openai-canary",
                "weather_api_key": "stored-weather-canary",
                "news_api_key": "stored-news-canary",
                "bookmarks": ["https://test.example"],
            }), encoding="utf-8")
            settings, _history, bookmarks, *_ = store.load()
            self.assertEqual((settings.openai_api_key, settings.weather_api_key, settings.news_api_key), ("", "", ""))
            self.assertEqual(bookmarks, ["https://test.example"])

    def test_ordinary_store_retains_environment_secret_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            credentials = Mock()
            credentials.get.return_value = ""
            credentials.set.return_value = True
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "ordinary-launch-key"}),
                patch("main.CredentialStore", return_value=credentials),
                patch("main.QStandardPaths.writableLocation", return_value=temp),
                patch("main.Path.cwd", return_value=Path(temp)),
            ):
                settings, *_ = SettingsStore().load()
                self.assertEqual(settings.openai_api_key, "ordinary-launch-key")
                credentials.set.assert_any_call("openai_api_key", "ordinary-launch-key")

    def test_main_smoke_uses_fresh_state_and_removes_it_after_shutdown(self) -> None:
        app = Mock()
        browser = Mock()
        created_paths: list[Path] = []
        lifecycle: list[str] = []
        callbacks = []

        def construct_browser(*, settings_store: SettingsStore | None = None) -> Mock:
            self.assertIsInstance(settings_store, IsolatedSettingsStore)
            created_paths.append(settings_store.directory)
            self.assertTrue(settings_store.directory.is_dir())
            self.assertFalse(settings_store.path.exists())
            self.save_state(settings_store)
            return browser

        def close_browser() -> None:
            self.assertTrue(created_paths[-1].is_dir())
            lifecycle.append("closed")

        def delete_browser() -> None:
            self.assertTrue(created_paths[-1].is_dir())
            lifecycle.append("deleted")

        def event_loop() -> int:
            callbacks.pop(0)()
            return 0

        browser.close.side_effect = close_browser
        browser.deleteLater.side_effect = delete_browser
        app.exec.side_effect = event_loop
        with (
            patch.object(app_module.sys, "argv", ["OctoBrowse.exe", "--smoke-test"]),
            patch("main.QApplication", return_value=app),
            patch("main.OctoBrowse", side_effect=construct_browser),
            patch("main.QStandardPaths.setTestModeEnabled"),
            patch("main.QCoreApplication.sendPostedEvents"),
            patch("main.QTimer.singleShot", side_effect=lambda _delay, callback: callbacks.append(callback)),
            patch("main.resource_path", return_value=Path("__missing_smoke_icon__")),
            patch("main.CredentialStore.get", side_effect=AssertionError("vault read")),
            patch("main.CredentialStore.set", side_effect=AssertionError("vault write")),
        ):
            self.assertEqual(app_module.main(), 0)
            self.assertFalse(created_paths[-1].exists())
            self.assertEqual(app_module.main(), 0)
            self.assertFalse(created_paths[-1].exists())
        self.assertEqual(lifecycle, ["closed", "deleted", "closed", "deleted"])
        self.assertNotEqual(created_paths[0], created_paths[1])
        self.assertEqual(browser.profile_for_tab.call_count, 2)
        browser.profile_for_tab.assert_called_with(True)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from main import BrowserSettings, SettingsStore


class FakeCredentials:
    def __init__(self, values: dict[str, str] | None = None, writable: bool = True) -> None:
        self.values = dict(values or {})
        self.writable = writable

    def get(self, name: str) -> str:
        return self.values.get(name, "")

    def set(self, name: str, value: str) -> bool:
        if self.writable:
            self.values[name] = value
        return self.writable


class SettingsStoreTests(unittest.TestCase):
    def make_store(self, root: Path, payload: object) -> SettingsStore:
        store = SettingsStore.__new__(SettingsStore)
        store.directory = root
        store.path = root / "settings.json"
        store.legacy_path = root / "legacy.json"
        store.credentials = FakeCredentials()
        store.path.write_text(json.dumps(payload), encoding="utf-8")
        return store

    def test_valid_but_wrong_json_roots_recover(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for payload in (None, [], "wrong", 42):
                with self.subTest(payload=payload):
                    store = self.make_store(root, payload)
                    settings, *_ = store.load()
                    self.assertEqual(settings.hibernation_minutes, 15)

    def test_bad_hibernation_value_recovers_and_workspaces_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(
                Path(temp_dir),
                {
                    "hibernation_minutes": "not-a-number",
                    "workspaces": [
                        {
                            "name": "Research",
                            "tabs": [{"url": "https://example.com", "title": "Example"}],
                        }
                    ],
                },
            )
            loaded = store.load()
            self.assertEqual(loaded[0].hibernation_minutes, 15)
            self.assertEqual(loaded[-1][0]["name"], "Research")

    def test_os_keyring_values_replace_plaintext_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self.make_store(root, {})
            credentials = FakeCredentials()
            store.credentials = credentials
            settings = BrowserSettings(
                openai_api_key="openai-secret",
                weather_api_key="weather-secret",
                news_api_key="news-secret",
            )
            store.save(settings, [], [], [], [], [], {}, {}, [], {}, [])
            payload = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["openai_api_key"], "")
            self.assertEqual(payload["weather_api_key"], "")
            self.assertEqual(payload["news_api_key"], "")
            self.assertEqual(credentials.values["openai_api_key"], "openai-secret")

    def test_keyring_failure_keeps_backward_compatible_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self.make_store(root, {})
            store.credentials = FakeCredentials(writable=False)
            settings = BrowserSettings(openai_api_key="fallback-secret")
            store.save(settings, [], [], [], [], [], {}, {}, [], {}, [])
            payload = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["openai_api_key"], "fallback-secret")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from main import BrowserSettings, SettingsStore
from octobrowse.research import make_research_note


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

    def test_legacy_session_urls_migrate_to_versioned_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(
                Path(temp_dir),
                {"session_tabs": ["https://example.com", "https://example.com"]},
            )

            snapshot = store.load()[5]

            self.assertEqual(snapshot["version"], 2)
            self.assertEqual(len(snapshot["tabs"]), 2)
            self.assertEqual(snapshot["tabs"][0]["url"], "https://example.com")

    def test_legacy_notes_migrate_to_versioned_research_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(
                Path(temp_dir),
                {
                    "notes": [
                        {
                            "url": "https://example.com/source",
                            "note": "Legacy observation",
                        }
                    ]
                },
            )

            note = store.load()[3][0]

            self.assertEqual(note["version"], 1)
            self.assertEqual(note["url"], "https://example.com/source")
            self.assertEqual(note["body"], "Legacy observation")
            self.assertTrue(note["id"].startswith("note-"))

    def test_structured_research_note_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self.make_store(root, {})
            note = make_research_note(
                "https://example.com/source",
                "Example source",
                "Quoted evidence",
                "My interpretation",
                now=123.0,
                note_id="note-round-trip",
            )

            store.save(
                BrowserSettings(),
                [],
                [note],
                [],
                [],
                [],
                {},
                {},
                [],
                {},
                [],
            )
            loaded_note = store.load()[3][0]

            self.assertEqual(loaded_note, note)

    def test_save_uses_canonical_session_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self.make_store(root, {})
            session = {
                "version": 2,
                "tabs": [
                    {"url": "https://example.com", "title": "Example", "pinned": True}
                ],
                "active_index": 0,
            }

            store.save(BrowserSettings(), [], [], [], session, [], {}, {}, [], {}, [])
            payload = json.loads(store.path.read_text(encoding="utf-8"))

            self.assertEqual(payload["session"], session)
            self.assertNotIn("session_tabs", payload)

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


class PasswordManagerTests(unittest.TestCase):
    """PasswordManager builds its cipher lazily; that must stay safe."""

    def test_available_reflects_a_constructed_cipher(self) -> None:
        from main import PasswordManager

        manager = PasswordManager()
        self.assertEqual(manager.available(), manager.cipher is not None)

    def test_available_is_false_when_the_backend_cannot_load(self) -> None:
        """cryptography commonly resolves and then fails to import its Rust
        backend on Windows. The dialog must not open on a cipher that can
        never be built."""
        from main import PasswordManager
        from octobrowse import optional_deps

        manager = PasswordManager()
        original = optional_deps.load
        optional_deps.load = lambda name: (  # type: ignore[assignment]
            None if name == "cryptography.fernet" else original(name)
        )
        try:
            self.assertFalse(manager.available())
            with self.assertRaises(RuntimeError):
                manager.encrypt("hunter2")
        finally:
            optional_deps.load = original  # type: ignore[assignment]

    def test_concurrent_first_use_never_discards_a_key(self) -> None:
        """Regression: the lazy property was a check-then-act race. Two
        threads could each generate a key and the second assignment discarded
        the first, making anything encrypted with the lost key undecryptable."""
        import sys
        import threading

        from main import PasswordManager

        if PasswordManager().cipher is None:
            self.skipTest("cryptography is not installed")

        original_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-9)
        try:
            failures = 0
            for _ in range(200):
                manager = PasswordManager()
                start = threading.Barrier(2)
                errors: list[BaseException] = []

                def toucher(
                    manager: object = manager,
                    start: threading.Barrier = start,
                    errors: list = errors,
                ) -> None:
                    try:
                        start.wait()
                        manager.cipher  # noqa: B018 - forces construction
                    except BaseException as exc:  # pragma: no cover
                        errors.append(exc)

                def saver(
                    manager: object = manager,
                    start: threading.Barrier = start,
                    errors: list = errors,
                ) -> None:
                    try:
                        start.wait()
                        manager.save_password("https://x.test", "hunter2")
                    except BaseException as exc:  # pragma: no cover
                        errors.append(exc)

                threads = [
                    threading.Thread(target=toucher),
                    threading.Thread(target=saver),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(errors, [])
                if manager.get_password("https://x.test") != "hunter2":
                    failures += 1
            self.assertEqual(failures, 0, f"{failures}/200 trials lost the key")
        finally:
            sys.setswitchinterval(original_interval)

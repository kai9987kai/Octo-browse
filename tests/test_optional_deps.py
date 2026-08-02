from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from octobrowse import optional_deps


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFERRED = ("openai", "gtts", "speech_recognition", "requests", "cryptography.fernet")


class OptionalDepsTests(unittest.TestCase):
    def setUp(self) -> None:
        optional_deps.reset_cache()

    def tearDown(self) -> None:
        optional_deps.reset_cache()

    def test_available_reports_a_present_module(self) -> None:
        self.assertTrue(optional_deps.available("json"))

    def test_available_reports_a_missing_module(self) -> None:
        self.assertFalse(optional_deps.available("octobrowse_no_such_module"))

    def test_available_does_not_import_the_module(self) -> None:
        name = "wave"  # stdlib, unlikely to be imported by the test runner
        sys.modules.pop(name, None)
        optional_deps.available(name)
        self.assertNotIn(name, sys.modules)

    def test_available_tolerates_a_malformed_name(self) -> None:
        self.assertFalse(optional_deps.available(""))
        self.assertFalse(optional_deps.available(".relative"))

    def test_load_returns_the_module(self) -> None:
        module = optional_deps.load("json")
        self.assertIsNotNone(module)
        self.assertEqual(module.loads("[1]"), [1])  # type: ignore[union-attr]

    def test_load_returns_none_for_a_missing_module(self) -> None:
        self.assertIsNone(optional_deps.load("octobrowse_no_such_module"))

    def test_load_is_cached(self) -> None:
        first = optional_deps.load("json")
        second = optional_deps.load("json")
        self.assertIs(first, second)
        self.assertGreaterEqual(optional_deps.load.cache_info().hits, 1)

    def test_load_survives_a_module_that_raises_on_import(self) -> None:
        # A dependency whose own import explodes must not take the browser
        # down; it is reported as simply unavailable.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "octobrowse_broken_probe.py").write_text(
                "raise RuntimeError('boom')\n", encoding="utf-8"
            )
            sys.path.insert(0, str(root))
            try:
                self.assertIsNone(optional_deps.load("octobrowse_broken_probe"))
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("octobrowse_broken_probe", None)

    def test_every_deferred_dependency_is_declared(self) -> None:
        for name in DEFERRED:
            with self.subTest(name=name):
                self.assertIn(name, optional_deps.OPTIONAL_DISTRIBUTIONS)

    def test_install_hint_names_the_distribution_not_the_module(self) -> None:
        self.assertIn("cryptography", optional_deps.install_hint("cryptography.fernet"))
        self.assertIn("gTTS", optional_deps.install_hint("gtts"))
        self.assertIn(
            "SpeechRecognition", optional_deps.install_hint("speech_recognition")
        )
        # Unknown names degrade to the module name rather than raising.
        self.assertIn("mystery", optional_deps.install_hint("mystery"))

    def test_available_does_not_leak_a_broken_parent_package(self) -> None:
        """Resolving a dotted name imports the parent. A parent whose __init__
        raises must be reported as unavailable, not escape into a Qt slot."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "octobrowse_broken_parent"
            package.mkdir()
            (package / "__init__.py").write_text(
                "raise RuntimeError('backend blew up at import time')\n",
                encoding="utf-8",
            )
            (package / "leaf.py").write_text("value = 1\n", encoding="utf-8")
            sys.path.insert(0, str(root))
            try:
                self.assertFalse(
                    optional_deps.available("octobrowse_broken_parent.leaf")
                )
                self.assertIsNone(optional_deps.load("octobrowse_broken_parent.leaf"))
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("octobrowse_broken_parent", None)


class StartupImportTests(unittest.TestCase):
    """The whole point of optional_deps: none of these load at startup."""

    def test_importing_main_does_not_pull_in_optional_dependencies(self) -> None:
        script = (
            "import sys\n"
            "import main\n"
            f"names = {DEFERRED!r}\n"
            "print(','.join(name for name in names if name in sys.modules))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"},
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        leaked = result.stdout.strip()
        self.assertEqual(
            leaked,
            "",
            f"these should load on demand, not at startup: {leaked}",
        )


class FrozenBuildContractTests(unittest.TestCase):
    """PyInstaller cannot see a runtime import, so it must be told."""

    def test_packaging_declares_a_hidden_import_for_each_deferred_dependency(self) -> None:
        build_common = REPO_ROOT / "packaging" / "build_common.ps1"
        self.assertTrue(build_common.exists(), "packaging/build_common.ps1 is missing")
        text = build_common.read_text(encoding="utf-8", errors="replace")
        for name in DEFERRED:
            with self.subTest(name=name):
                self.assertIn(
                    name,
                    text,
                    f"{name} is loaded at runtime but has no --hidden-import; "
                    "the frozen build would lose the feature silently.",
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import unittest
from pathlib import Path

from main import OCTO_BROWSER_VERSION
from octobrowse.version import __version__


REPO_ROOT = Path(__file__).resolve().parent.parent


class VersionTests(unittest.TestCase):
    """octobrowse.version is the single source of truth.

    Every other copy is checked against it rather than against a literal, so
    bumping the release in one place can no longer leave a stale version baked
    into a shipped artifact.
    """

    def test_version_is_a_release_number(self) -> None:
        self.assertRegex(__version__, r"^\d+\.\d+(?:\.\d+)?$")

    def test_main_uses_package_release_version(self) -> None:
        self.assertEqual(OCTO_BROWSER_VERSION, __version__)

    def test_inno_setup_fallback_matches(self) -> None:
        script = REPO_ROOT / "packaging" / "octobrowse.iss"
        match = re.search(
            r'#define\s+MyAppVersion\s+"([^"]+)"',
            script.read_text(encoding="utf-8", errors="replace"),
        )
        self.assertIsNotNone(match, "MyAppVersion is missing from octobrowse.iss")
        self.assertEqual(match.group(1), __version__)  # type: ignore[union-attr]

    def test_release_notes_exist_for_this_version(self) -> None:
        notes = REPO_ROOT / f"RELEASE_NOTES_v{__version__}.md"
        self.assertTrue(
            notes.exists(),
            f"{notes.name} is missing; every release ships notes.",
        )

    def test_packaging_scripts_do_not_hardcode_a_version(self) -> None:
        """A hardcoded default silently mislabels the artifact after a bump."""
        pattern = re.compile(r'\$Version\s*=\s*"\d+\.\d+')
        for script in sorted((REPO_ROOT / "packaging").glob("*.ps1")):
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8", errors="replace")
                self.assertIsNone(
                    pattern.search(text),
                    f"{script.name} hardcodes a version; read it from "
                    "octobrowse.version via Get-OctoVersion instead.",
                )


if __name__ == "__main__":
    unittest.main()

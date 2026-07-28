from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from octobrowse.extensions import (
    ExtensionManifestError,
    extension_review_text,
    inspect_extension_source,
)


class ExtensionPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def base_manifest(**overrides: object) -> dict[str, object]:
        manifest: dict[str, object] = {
            "manifest_version": 3,
            "name": "Test Extension",
            "version": "1.2.3",
        }
        manifest.update(overrides)
        return manifest

    def write_directory_manifest(
        self, directory_name: str = "unpacked", **overrides: object
    ) -> Path:
        directory = self.root / directory_name
        directory.mkdir()
        manifest = self.base_manifest(**overrides)
        (directory / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return directory

    def write_zip(
        self,
        name: str = "extension.zip",
        manifest_path: str = "manifest.json",
        manifest: dict[str, object] | None = None,
        extra_files: dict[str, bytes] | None = None,
    ) -> Path:
        archive_path = self.root / name
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                manifest_path,
                json.dumps(manifest if manifest is not None else self.base_manifest()),
            )
            for filename, data in (extra_files or {}).items():
                archive.writestr(filename, data)
        return archive_path

    def test_directory_manifest_is_normalized_into_frozen_record(self) -> None:
        directory = self.write_directory_manifest(
            directory_name="normalized",
            description="  A useful extension.  ",
            permissions=[" tabs ", "history", "tabs", "activeTab"],
            host_permissions=[
                " HTTPS://Example.COM/Private/* ",
                "https://example.com/Private/*",
                "https://*.Example.NET/*",
            ],
            content_scripts=[
                {
                    "matches": [
                        " https://*.Example.NET/* ",
                        "HTTP://Docs.Example.ORG/*",
                    ]
                },
                {"matches": ["http://docs.example.org/*"]},
            ],
        )

        extension = inspect_extension_source(directory)

        self.assertEqual(extension.package_type, "directory")
        self.assertEqual(extension.manifest_version, 3)
        self.assertEqual(extension.name, "Test Extension")
        self.assertEqual(extension.version, "1.2.3")
        self.assertEqual(extension.description, "A useful extension.")
        self.assertEqual(
            extension.permissions, ("tabs", "history", "activeTab")
        )
        self.assertEqual(extension.optional_permissions, ())
        self.assertEqual(
            extension.host_permissions,
            (
                "https://example.com/Private/*",
                "https://*.example.net/*",
            ),
        )
        self.assertEqual(extension.optional_host_permissions, ())
        self.assertEqual(
            extension.content_script_matches,
            (
                "https://*.example.net/*",
                "http://docs.example.org/*",
            ),
        )
        self.assertEqual(
            extension.site_access_patterns,
            (
                "https://example.com/Private/*",
                "https://*.example.net/*",
                "http://docs.example.org/*",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            extension.name = "Changed"  # type: ignore[misc]

    def test_zip_with_top_level_manifest_is_inspected_without_extraction(self) -> None:
        archive_path = self.write_zip(
            manifest=self.base_manifest(
                name="ZIP Extension",
                version="4.0",
                permissions=["storage"],
            ),
            extra_files={"scripts/background.js": b"console.log('loaded');"},
        )

        extension = inspect_extension_source(archive_path)

        self.assertEqual(extension.package_type, "zip")
        self.assertEqual(extension.name, "ZIP Extension")
        self.assertEqual(extension.permissions, ("storage",))
        self.assertFalse((self.root / "scripts").exists())

    def test_manifest_v2_is_rejected_with_specific_error_type(self) -> None:
        directory = self.write_directory_manifest(manifest_version=2)

        with self.assertRaisesRegex(ExtensionManifestError, "Manifest V3"):
            inspect_extension_source(directory)

        self.assertTrue(issubclass(ExtensionManifestError, ValueError))

    def test_manifest_must_exist_at_package_root(self) -> None:
        empty_directory = self.root / "empty"
        empty_directory.mkdir()
        nested_zip = self.write_zip(
            name="nested.zip", manifest_path="nested/manifest.json"
        )

        with self.assertRaisesRegex(ExtensionManifestError, "top-level manifest"):
            inspect_extension_source(empty_directory)
        with self.assertRaisesRegex(ExtensionManifestError, "archive root"):
            inspect_extension_source(nested_zip)

    def test_invalid_json_and_non_object_manifest_are_rejected(self) -> None:
        invalid_json = self.root / "invalid-json"
        invalid_json.mkdir()
        (invalid_json / "manifest.json").write_bytes(b"{broken")

        non_object = self.root / "non-object"
        non_object.mkdir()
        (non_object / "manifest.json").write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(ExtensionManifestError, "valid UTF-8 JSON"):
            inspect_extension_source(invalid_json)
        with self.assertRaisesRegex(ExtensionManifestError, "JSON object"):
            inspect_extension_source(non_object)

    def test_name_and_version_must_be_nonempty_strings(self) -> None:
        invalid_values = (
            ("missing-name", {"name": None}),
            ("blank-name", {"name": " \t"}),
            ("missing-version", {"version": None}),
            ("blank-version", {"version": ""}),
        )
        for directory_name, overrides in invalid_values:
            with self.subTest(directory_name):
                directory = self.write_directory_manifest(
                    directory_name=directory_name, **overrides
                )
                with self.assertRaisesRegex(
                    ExtensionManifestError, "nonempty string"
                ):
                    inspect_extension_source(directory)

    def test_directory_manifest_size_is_bounded_before_parsing(self) -> None:
        directory = self.root / "oversized-directory"
        directory.mkdir()
        (directory / "manifest.json").write_bytes(b" " * 65)

        with patch("octobrowse.extensions.MAX_MANIFEST_BYTES", 64):
            with self.assertRaisesRegex(ExtensionManifestError, "safety limit"):
                inspect_extension_source(directory)

    def test_zip_manifest_and_total_expanded_size_are_bounded(self) -> None:
        oversized_manifest = self.write_zip(
            name="oversized-manifest.zip",
            manifest=self.base_manifest(description="x" * 200),
        )
        with patch("octobrowse.extensions.MAX_MANIFEST_BYTES", 80):
            with self.assertRaisesRegex(ExtensionManifestError, "manifest.json exceeds"):
                inspect_extension_source(oversized_manifest)

        manifest_data = json.dumps(self.base_manifest()).encode("utf-8")
        oversized_payload = self.write_zip(
            name="oversized-payload.zip",
            extra_files={"payload.bin": b"x" * 32},
        )
        with patch(
            "octobrowse.extensions.MAX_ZIP_UNCOMPRESSED_BYTES",
            len(manifest_data) + 31,
        ):
            with self.assertRaisesRegex(ExtensionManifestError, "expanded size"):
                inspect_extension_source(oversized_payload)

    def test_non_zip_file_and_missing_path_raise_package_error(self) -> None:
        plain_file = self.root / "not-an-extension.txt"
        plain_file.write_text("not a zip", encoding="utf-8")

        with self.assertRaisesRegex(ExtensionManifestError, "extension ZIP"):
            inspect_extension_source(plain_file)
        with self.assertRaisesRegex(ExtensionManifestError, "does not exist"):
            inspect_extension_source(self.root / "missing")

    def test_permission_collections_and_match_patterns_are_validated(self) -> None:
        cases = (
            ("permissions", {"permissions": "tabs"}, "must be an array"),
            (
                "empty-permission",
                {"permissions": ["tabs", " "]},
                "nonempty string",
            ),
            (
                "host-pattern",
                {"host_permissions": ["example.com"]},
                "invalid match pattern",
            ),
            (
                "optional-permissions",
                {"optional_permissions": "history"},
                "must be an array",
            ),
            (
                "optional-host-pattern",
                {"optional_host_permissions": ["example.com"]},
                "invalid match pattern",
            ),
            (
                "content-script-shape",
                {"content_scripts": ["not-an-object"]},
                "must be an object",
            ),
            (
                "content-script-matches",
                {"content_scripts": [{"js": ["content.js"]}]},
                "matches.*required",
            ),
        )
        for directory_name, overrides, expected_error in cases:
            with self.subTest(directory_name):
                directory = self.write_directory_manifest(
                    directory_name=directory_name, **overrides
                )
                with self.assertRaisesRegex(
                    ExtensionManifestError, expected_error
                ):
                    inspect_extension_source(directory)

    def test_permission_review_flags_all_sites_and_sensitive_permissions(self) -> None:
        directory = self.write_directory_manifest(
            permissions=["storage", "history", "nativeMessaging", "cookies"],
            host_permissions=["<all_urls>"],
            content_scripts=[{"matches": ["https://*/*"]}],
        )
        extension = inspect_extension_source(directory)

        review = extension_review_text(extension)

        self.assertTrue(extension.all_sites_access)
        self.assertTrue(extension.has_all_sites_access)
        self.assertEqual(
            extension.sensitive_permissions,
            ("history", "nativeMessaging", "cookies"),
        )
        self.assertEqual(extension.permission_review, review)
        self.assertIn("WARNING: ALL-SITES ACCESS", review)
        self.assertIn("WARNING: SENSITIVE PERMISSIONS", review)
        self.assertIn("history, nativeMessaging, cookies", review)

    def test_optional_permissions_are_included_in_risk_review(self) -> None:
        directory = self.write_directory_manifest(
            optional_permissions=["history", "cookies"],
            optional_host_permissions=["<all_urls>"],
        )

        extension = inspect_extension_source(directory)
        review = extension_review_text(extension)

        self.assertEqual(extension.optional_permissions, ("history", "cookies"))
        self.assertEqual(extension.optional_host_permissions, ("<all_urls>",))
        self.assertTrue(extension.all_sites_access)
        self.assertEqual(extension.sensitive_permissions, ("history", "cookies"))
        self.assertIn("WARNING: ALL-SITES ACCESS", review)
        self.assertIn("WARNING: SENSITIVE PERMISSIONS", review)
        self.assertIn("Optional API permissions: history, cookies", review)
        self.assertIn("Optional host permissions: <all_urls>", review)

    def test_permission_review_describes_narrow_or_absent_access_without_warning(
        self,
    ) -> None:
        narrow = inspect_extension_source(
            self.write_directory_manifest(
                directory_name="narrow",
                permissions=["storage"],
                host_permissions=["https://docs.example.com/*"],
            )
        )
        no_access = inspect_extension_source(
            self.write_directory_manifest(directory_name="none")
        )

        narrow_review = narrow.permission_review
        no_access_review = no_access.permission_review

        self.assertFalse(narrow.all_sites_access)
        self.assertIn("Site access: https://docs.example.com/*", narrow_review)
        self.assertNotIn("WARNING:", narrow_review)
        self.assertIn("Site access: none declared.", no_access_review)
        self.assertIn("Sensitive permissions: none declared.", no_access_review)

    def test_zip_rejects_unsafe_or_duplicate_member_paths(self) -> None:
        unsafe = self.write_zip(
            name="unsafe.zip", extra_files={"../escape.js": b"bad"}
        )
        duplicate = self.root / "duplicate.zip"
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("manifest.json", json.dumps(self.base_manifest()))
            archive.writestr("SCRIPT.js", "one")
            archive.writestr("script.js", "two")

        with self.assertRaisesRegex(ExtensionManifestError, "unsafe member path"):
            inspect_extension_source(unsafe)
        with self.assertRaisesRegex(ExtensionManifestError, "duplicate member path"):
            inspect_extension_source(duplicate)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from octobrowse.snapshots import (
    manifest_path_for_archive,
    snapshot_filename,
    verify_snapshot_bundle,
    write_snapshot_manifest,
)


class SnapshotTests(unittest.TestCase):
    def test_default_filename_is_bounded_and_windows_safe(self) -> None:
        name = snapshot_filename('  CON  ')
        self.assertEqual(name, "_CON.mhtml")
        self.assertEqual(snapshot_filename("CON.txt"), "_CON.txt.mhtml")
        self.assertNotIn(":", snapshot_filename('An <unsafe>: "title"'))
        self.assertLessEqual(len(snapshot_filename("x" * 300)), 102)
        self.assertEqual(snapshot_filename(None), "OctoBrowse snapshot.mhtml")

    def test_manifest_round_trip_verifies_archive_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "evidence.mhtml"
            archive.write_bytes(b"From: <Saved by Blink>\r\nContent-Type: text/html\r\n")
            sidecar = write_snapshot_manifest(
                archive,
                source_url="https://example.test/article",
                source_title="Evidence",
                octobrowse_version="3.4",
                chromium_version="138.0",
                captured_at=1_700_000_000,
                private_capture=False,
            )

            result = verify_snapshot_bundle(archive)
            self.assertTrue(result.valid, result.reason)
            self.assertEqual(result.manifest_path, sidecar)
            self.assertEqual(result.archive_path, archive)
            manifest = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(manifest["archive"]["file"], archive.name)
            self.assertEqual(manifest["archive"]["bytes"], archive.stat().st_size)
            self.assertEqual(len(manifest["archive"]["sha256"]), 64)
            self.assertEqual(manifest["source"]["url"], "https://example.test/article")
            self.assertEqual(manifest["capture"]["created_at"], "2023-11-14T22:13:20Z")

    def test_verification_detects_modified_or_missing_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "capture.mhtml"
            archive.write_bytes(b"original")
            sidecar = write_snapshot_manifest(
                archive,
                source_url="https://example.test/",
                source_title="Capture",
                octobrowse_version="3.4",
                chromium_version="138",
            )
            archive.write_bytes(b"tampered")
            self.assertFalse(verify_snapshot_bundle(sidecar).valid)
            archive.unlink()
            missing = verify_snapshot_bundle(sidecar)
            self.assertFalse(missing.valid)
            self.assertIn("missing", missing.reason.lower())

    def test_sidecar_cannot_redirect_verifier_outside_its_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sidecar = Path(temp) / "hostile.mhtml.json"
            for archive_name in ("../outside.mhtml", "CON.mhtml"):
                with self.subTest(archive_name=archive_name):
                    sidecar.write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "format": "mhtml",
                                "archive": {
                                    "file": archive_name,
                                    "bytes": 0,
                                    "sha256": "0" * 64,
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
                    result = verify_snapshot_bundle(sidecar)
                    self.assertFalse(result.valid)
                    self.assertIn("unsafe", result.reason.lower())

    def test_selected_archive_must_match_the_sidecar_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "actual.mhtml"
            archive.write_bytes(b"archive")
            sidecar = write_snapshot_manifest(
                archive,
                source_url="https://example.test/",
                source_title="Actual",
                octobrowse_version="3.4",
                chromium_version="138",
            )
            selected = Path(temp) / "renamed.mhtml"
            sidecar.rename(manifest_path_for_archive(selected))
            result = verify_snapshot_bundle(selected)
            self.assertFalse(result.valid)
            self.assertIn("different archive", result.reason.lower())

    def test_archive_sidecar_name_is_portable_and_adjacent(self) -> None:
        archive = Path("folder") / "page.mhtml"
        self.assertEqual(
            manifest_path_for_archive(archive),
            Path("folder") / "page.mhtml.json",
        )

    def test_malformed_metadata_and_deep_json_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "metadata.mhtml"
            archive.write_bytes(b"archive")
            sidecar = write_snapshot_manifest(
                archive,
                source_url="https://example.test/",
                source_title="Metadata",
                octobrowse_version="3.4",
                chromium_version="138",
            )
            manifest = json.loads(sidecar.read_text(encoding="utf-8"))
            manifest["source"] = []
            sidecar.write_text(json.dumps(manifest), encoding="utf-8")
            malformed = verify_snapshot_bundle(sidecar)
            self.assertFalse(malformed.valid)
            self.assertIn("source metadata", malformed.reason.lower())

            sidecar.write_text(
                "[" * 20_000 + "0" + "]" * 20_000,
                encoding="utf-8",
            )
            nested = verify_snapshot_bundle(sidecar)
            self.assertFalse(nested.valid)
            self.assertIn("unreadable", nested.reason.lower())

            sidecar.write_text(
                '{"oversized_integer":' + "1" * 5_000 + "}",
                encoding="utf-8",
            )
            oversized_integer = verify_snapshot_bundle(sidecar)
            self.assertFalse(oversized_integer.valid)
            self.assertIn("unreadable", oversized_integer.reason.lower())

    def test_concurrent_manifest_writes_use_unique_atomic_temps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "concurrent.mhtml"
            archive.write_bytes(b"one stable archive")
            metadata = {
                "source_url": "https://example.test/",
                "source_title": "Concurrent",
                "octobrowse_version": "3.4",
                "chromium_version": "138",
            }
            with ThreadPoolExecutor(max_workers=2) as executor:
                paths = list(
                    executor.map(
                        lambda _index: write_snapshot_manifest(
                            archive,
                            **metadata,
                        ),
                        range(2),
                    )
                )
            self.assertEqual(paths[0], paths[1])
            self.assertTrue(verify_snapshot_bundle(archive).valid)


if __name__ == "__main__":
    unittest.main()

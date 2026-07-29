"""Integrity metadata for portable offline research snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SOURCE_URL = 8192
MAX_SOURCE_TITLE = 512
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


@dataclass(frozen=True)
class SnapshotVerification:
    """Result of checking an MHTML archive against its provenance sidecar."""

    valid: bool
    reason: str
    archive_path: Path | None = None
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None


def snapshot_filename(title: Any) -> str:
    """Return a bounded Windows-safe default filename for an MHTML archive."""

    if not isinstance(title, str):
        title = ""
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", title)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")
    if not stem:
        stem = "OctoBrowse snapshot"
    if stem.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    return f"{stem[:96].rstrip(' ._') or 'OctoBrowse snapshot'}.mhtml"


def manifest_path_for_archive(archive_path: str | Path) -> Path:
    archive = Path(archive_path)
    return archive.with_name(f"{archive.name}.json")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _single_line(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", " ").split())[:limit]


def build_snapshot_manifest(
    archive_path: str | Path,
    *,
    source_url: Any,
    source_title: Any,
    octobrowse_version: Any,
    chromium_version: Any,
    captured_at: float | None = None,
    private_capture: bool = False,
) -> dict[str, Any]:
    """Hash a completed archive and build its portable provenance record."""

    archive = Path(archive_path)
    if not archive.is_file():
        raise FileNotFoundError(f"Snapshot archive does not exist: {archive}")
    timestamp = time.time() if captured_at is None else float(captured_at)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("Snapshot capture time is invalid.")
    title = _single_line(source_title, MAX_SOURCE_TITLE)
    url = _single_line(source_url, MAX_SOURCE_URL)
    version = _single_line(octobrowse_version, 64)
    chromium = _single_line(chromium_version, 128)
    try:
        created_at = datetime.fromtimestamp(
            timestamp, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError("Snapshot capture time is outside the supported range.") from exc
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "format": "mhtml",
        "archive": {
            "file": archive.name,
            "bytes": archive.stat().st_size,
            "sha256": _sha256_file(archive),
        },
        "source": {
            "title": title,
            "url": url,
            "private_capture": bool(private_capture),
        },
        "capture": {
            "created_at": created_at,
            "octobrowse_version": version,
            "chromium_version": chromium,
        },
    }


def write_snapshot_manifest(
    archive_path: str | Path,
    **metadata: Any,
) -> Path:
    """Atomically write a completed snapshot's JSON sidecar."""

    archive = Path(archive_path)
    manifest = build_snapshot_manifest(archive, **metadata)
    manifest_path = manifest_path_for_archive(archive)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=manifest_path.parent,
            prefix=f".{manifest_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        temporary.replace(manifest_path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return manifest_path


def _invalid(reason: str, *, manifest_path: Path | None = None) -> SnapshotVerification:
    return SnapshotVerification(False, reason, manifest_path=manifest_path)


def _valid_manifest_string(value: Any, limit: int, *, required: bool = False) -> bool:
    return (
        isinstance(value, str)
        and (bool(value) or not required)
        and len(value) <= limit
        and all(ord(character) >= 32 for character in value)
    )


def verify_snapshot_bundle(path: str | Path) -> SnapshotVerification:
    """Verify a selected archive or sidecar without trusting sidecar paths."""

    selected = Path(path)
    if selected.suffix.lower() == ".json":
        manifest_path = selected
        selected_archive: Path | None = None
    else:
        manifest_path = manifest_path_for_archive(selected)
        selected_archive = selected
    try:
        manifest_exists = manifest_path.is_file()
    except OSError:
        manifest_exists = False
    if not manifest_exists:
        return _invalid("The snapshot provenance sidecar is missing.", manifest_path=manifest_path)
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            return _invalid("The snapshot sidecar is too large.", manifest_path=manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ):
        return _invalid("The snapshot sidecar is unreadable.", manifest_path=manifest_path)
    if not isinstance(manifest, dict):
        return _invalid("The snapshot sidecar must contain a JSON object.", manifest_path=manifest_path)
    if manifest.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return _invalid("The snapshot sidecar uses an unsupported schema.", manifest_path=manifest_path)
    if manifest.get("format") != "mhtml":
        return _invalid("The snapshot sidecar does not describe an MHTML archive.", manifest_path=manifest_path)

    archive_record = manifest.get("archive")
    if not isinstance(archive_record, dict):
        return _invalid("The snapshot archive record is missing.", manifest_path=manifest_path)
    archive_name = archive_record.get("file")
    if (
        not isinstance(archive_name, str)
        or not archive_name
        or len(archive_name) > 255
        or Path(archive_name).name != archive_name
        or bool(re.search(r'[<>:"/\\|?*\x00-\x1f]', archive_name))
        or archive_name.endswith((" ", "."))
    ):
        return _invalid("The snapshot archive filename is unsafe.", manifest_path=manifest_path)
    source_record = manifest.get("source")
    capture_record = manifest.get("capture")
    if (
        not isinstance(source_record, dict)
        or not _valid_manifest_string(
            source_record.get("title"),
            MAX_SOURCE_TITLE,
        )
        or not _valid_manifest_string(
            source_record.get("url"),
            MAX_SOURCE_URL,
        )
        or not isinstance(source_record.get("private_capture"), bool)
    ):
        return _invalid(
            "The snapshot source metadata is invalid.",
            manifest_path=manifest_path,
        )
    if (
        not isinstance(capture_record, dict)
        or not _valid_manifest_string(
            capture_record.get("created_at"),
            64,
            required=True,
        )
        or not _UTC_TIMESTAMP_PATTERN.fullmatch(capture_record["created_at"])
        or not _valid_manifest_string(
            capture_record.get("octobrowse_version"),
            64,
        )
        or not _valid_manifest_string(
            capture_record.get("chromium_version"),
            128,
        )
    ):
        return _invalid(
            "The snapshot capture metadata is invalid.",
            manifest_path=manifest_path,
        )
    if selected_archive is not None and archive_name != selected_archive.name:
        return _invalid(
            "The sidecar names a different archive than the selected file.",
            manifest_path=manifest_path,
        )
    archive_path = manifest_path.parent / archive_name
    try:
        archive_exists = archive_path.is_file()
    except OSError:
        archive_exists = False
    if not archive_exists:
        return SnapshotVerification(
            False,
            "The MHTML archive named by the sidecar is missing.",
            archive_path=archive_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    expected_bytes = archive_record.get("bytes")
    expected_hash = archive_record.get("sha256")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes < 0
        or not isinstance(expected_hash, str)
        or not _SHA256_PATTERN.fullmatch(expected_hash)
    ):
        return SnapshotVerification(
            False,
            "The snapshot integrity fields are invalid.",
            archive_path=archive_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    try:
        actual_bytes = archive_path.stat().st_size
        actual_hash = _sha256_file(archive_path)
    except OSError:
        return SnapshotVerification(
            False,
            "The MHTML archive could not be read.",
            archive_path=archive_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    if actual_bytes != expected_bytes:
        return SnapshotVerification(
            False,
            "The MHTML archive size no longer matches its provenance record.",
            archive_path=archive_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    if actual_hash != expected_hash:
        return SnapshotVerification(
            False,
            "The MHTML archive SHA-256 no longer matches its provenance record.",
            archive_path=archive_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    return SnapshotVerification(
        True,
        "Snapshot integrity verified.",
        archive_path=archive_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )


__all__ = [
    "MAX_MANIFEST_BYTES",
    "SNAPSHOT_SCHEMA_VERSION",
    "SnapshotVerification",
    "build_snapshot_manifest",
    "manifest_path_for_archive",
    "snapshot_filename",
    "verify_snapshot_bundle",
    "write_snapshot_manifest",
]

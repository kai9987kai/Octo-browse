"""Pure inspection and validation for Manifest V3 extension packages.

This module deliberately does not load, extract, or install extensions.  It
only reads enough package metadata to let the UI present a meaningful
permission review without executing package code.
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_MANIFEST_BYTES = 512 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000

SENSITIVE_PERMISSIONS = frozenset(
    {
        "bookmarks",
        "browsingData",
        "clipboardRead",
        "clipboardWrite",
        "contentSettings",
        "cookies",
        "debugger",
        "declarativeNetRequestWithHostAccess",
        "downloads",
        "downloads.open",
        "downloads.ui",
        "geolocation",
        "history",
        "identity",
        "idle",
        "management",
        "nativeMessaging",
        "privacy",
        "proxy",
        "sessions",
        "scripting",
        "tabCapture",
        "tabs",
        "topSites",
        "unlimitedStorage",
        "webNavigation",
        "webRequest",
        "webRequestBlocking",
    }
)
_SENSITIVE_PERMISSION_KEYS = frozenset(
    permission.casefold() for permission in SENSITIVE_PERMISSIONS
)
_MATCH_SCHEME_RE = re.compile(r"^(?:\*|[a-z][a-z0-9+.-]*)$", re.IGNORECASE)


def _is_all_sites_pattern(pattern: str) -> bool:
    if pattern == "<all_urls>":
        return True
    scheme, separator, remainder = pattern.partition("://")
    if not separator or scheme not in {"*", "http", "https"}:
        return False
    host, path_separator, _path = remainder.partition("/")
    return bool(path_separator) and host == "*"


class ExtensionManifestError(ValueError):
    """Raised when an extension package is malformed or unsupported."""


# Compatibility name for callers that describe failures at the package level.
ExtensionPackageError = ExtensionManifestError


@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    """Normalized metadata obtained without loading extension code."""

    source: Path
    package_type: str
    manifest_version: int
    name: str
    version: str
    description: str
    permissions: tuple[str, ...]
    optional_permissions: tuple[str, ...]
    host_permissions: tuple[str, ...]
    optional_host_permissions: tuple[str, ...]
    content_script_matches: tuple[str, ...]

    @property
    def site_access_patterns(self) -> tuple[str, ...]:
        """Return all declared host and content-script patterns once each."""
        return tuple(
            dict.fromkeys(
                (
                    *self.host_permissions,
                    *self.optional_host_permissions,
                    *self.content_script_matches,
                )
            )
        )

    @property
    def all_sites_access(self) -> bool:
        """Whether any declaration spans every ordinary web host."""
        return any(_is_all_sites_pattern(pattern) for pattern in self.site_access_patterns)

    @property
    def has_all_sites_access(self) -> bool:
        """Readable alias for callers building confirmation dialogs."""
        return self.all_sites_access

    @property
    def sensitive_permissions(self) -> tuple[str, ...]:
        """Return declared API permissions with elevated privacy/security impact."""
        return tuple(
            permission
            for permission in dict.fromkeys(
                (*self.permissions, *self.optional_permissions)
            )
            if permission.casefold() in _SENSITIVE_PERMISSION_KEYS
        )

    @property
    def permission_review(self) -> str:
        """Return a concise review suitable for an inspector dialog."""
        return extension_review_text(self)


def _package_error(
    message: str, cause: BaseException | None = None
) -> ExtensionManifestError:
    error = ExtensionManifestError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _read_directory_manifest(directory: Path) -> bytes:
    manifest_path = directory / "manifest.json"
    try:
        if not manifest_path.is_file():
            raise _package_error(
                "Extension directory must contain a top-level manifest.json file."
            )
        declared_size = manifest_path.stat().st_size
        if declared_size > MAX_MANIFEST_BYTES:
            raise _package_error(
                f"manifest.json exceeds the {MAX_MANIFEST_BYTES}-byte safety limit."
            )
        with manifest_path.open("rb") as manifest_file:
            data = manifest_file.read(MAX_MANIFEST_BYTES + 1)
    except ExtensionManifestError:
        raise
    except OSError as exc:
        raise _package_error(f"Could not read manifest.json: {exc}", exc)
    if len(data) > MAX_MANIFEST_BYTES:
        raise _package_error(
            f"manifest.json exceeds the {MAX_MANIFEST_BYTES}-byte safety limit."
        )
    return data


def _validate_zip_member_names(infos: list[zipfile.ZipInfo]) -> None:
    """Reject member names that are unsafe to extract on Windows later."""
    seen: set[str] = set()
    for info in infos:
        name = info.filename
        normalized = name.replace("\\", "/")
        parts = normalized.split("/")
        if (
            not name
            or "\\" in name
            or normalized.startswith("/")
            or (parts and ":" in parts[0])
            or any(part == ".." for part in parts)
        ):
            raise _package_error(f"ZIP contains an unsafe member path: {name!r}.")
        collision_key = normalized.rstrip("/").casefold()
        if collision_key and collision_key in seen:
            raise _package_error(f"ZIP contains a duplicate member path: {name!r}.")
        if collision_key:
            seen.add(collision_key)


def _read_zip_manifest(archive_path: Path) -> bytes:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise _package_error(
                    f"ZIP contains more than the {MAX_ZIP_ENTRIES}-entry safety limit."
                )
            _validate_zip_member_names(infos)

            total_size = 0
            for info in infos:
                total_size += info.file_size
                if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise _package_error(
                        "ZIP expanded size exceeds the "
                        f"{MAX_ZIP_UNCOMPRESSED_BYTES}-byte safety limit."
                    )

            manifest_infos = [
                info
                for info in infos
                if info.filename == "manifest.json" and not info.is_dir()
            ]
            if not manifest_infos:
                raise _package_error(
                    "Extension ZIP must contain manifest.json at the archive root."
                )
            if len(manifest_infos) != 1:
                raise _package_error(
                    "Extension ZIP must contain exactly one top-level manifest.json."
                )
            manifest_info = manifest_infos[0]
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise _package_error(
                    f"manifest.json exceeds the {MAX_MANIFEST_BYTES}-byte safety limit."
                )
            with archive.open(manifest_info, "r") as manifest_file:
                data = manifest_file.read(MAX_MANIFEST_BYTES + 1)
    except ExtensionManifestError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise _package_error(f"Could not read extension ZIP: {exc}", exc)

    if len(data) > MAX_MANIFEST_BYTES:
        raise _package_error(
            f"manifest.json exceeds the {MAX_MANIFEST_BYTES}-byte safety limit."
        )
    return data


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value}")


def _decode_manifest(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8-sig")
        value = json.loads(text, parse_constant=_reject_nonstandard_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise _package_error(f"manifest.json is not valid UTF-8 JSON: {exc}", exc)
    if not isinstance(value, dict):
        raise _package_error("manifest.json must contain a JSON object.")
    return value


def _required_text(manifest: dict[str, Any], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value.strip():
        raise _package_error(f"manifest.json requires a nonempty string {field!r}.")
    return value.strip()


def _optional_text(manifest: dict[str, Any], field: str) -> str:
    if field not in manifest:
        return ""
    value = manifest[field]
    if not isinstance(value, str):
        raise _package_error(f"manifest.json field {field!r} must be a string.")
    return value.strip()


def _normalize_string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _package_error(f"manifest.json field {field!r} must be an array.")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _package_error(
                f"manifest.json field {field!r} item {index} must be a nonempty string."
            )
        item = item.strip()
        if item not in seen:
            seen.add(item)
            normalized.append(item)
    return tuple(normalized)


def _normalize_match_pattern(pattern: str, field: str) -> str:
    if pattern.casefold() == "<all_urls>":
        return "<all_urls>"

    scheme, separator, remainder = pattern.partition("://")
    if not separator or not _MATCH_SCHEME_RE.fullmatch(scheme):
        raise _package_error(
            f"manifest.json field {field!r} contains invalid match pattern {pattern!r}."
        )
    slash_index = remainder.find("/")
    if slash_index < 0:
        raise _package_error(
            f"manifest.json field {field!r} contains invalid match pattern {pattern!r}."
        )
    host = remainder[:slash_index]
    path = remainder[slash_index:]
    normalized_scheme = scheme.lower()
    if (
        any(character.isspace() for character in pattern)
        or not path.startswith("/")
        or (normalized_scheme != "file" and not host)
    ):
        raise _package_error(
            f"manifest.json field {field!r} contains invalid match pattern {pattern!r}."
        )
    return f"{normalized_scheme}://{host.lower()}{path}"


def _normalize_match_patterns(value: Any, field: str) -> tuple[str, ...]:
    patterns = _normalize_string_list(value, field)
    normalized: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        canonical = _normalize_match_pattern(pattern, field)
        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)
    return tuple(normalized)


def _content_script_matches(manifest: dict[str, Any]) -> tuple[str, ...]:
    if "content_scripts" not in manifest:
        return ()
    scripts = manifest["content_scripts"]
    if not isinstance(scripts, list):
        raise _package_error("manifest.json field 'content_scripts' must be an array.")

    result: list[str] = []
    seen: set[str] = set()
    for index, script in enumerate(scripts):
        if not isinstance(script, dict):
            raise _package_error(
                f"manifest.json content_scripts item {index} must be an object."
            )
        field = f"content_scripts[{index}].matches"
        if "matches" not in script:
            raise _package_error(f"manifest.json field {field!r} is required.")
        matches = _normalize_match_patterns(script["matches"], field)
        if not matches:
            raise _package_error(f"manifest.json field {field!r} cannot be empty.")
        for pattern in matches:
            if pattern not in seen:
                seen.add(pattern)
                result.append(pattern)
    return tuple(result)


def _parse_manifest(
    data: bytes, source: Path, package_type: str
) -> ExtensionManifest:
    manifest = _decode_manifest(data)
    manifest_version = manifest.get("manifest_version")
    if type(manifest_version) is not int or manifest_version != 3:
        raise _package_error(
            "Only Manifest V3 extensions are supported "
            f"(found {manifest_version!r})."
        )

    permissions = (
        _normalize_string_list(manifest["permissions"], "permissions")
        if "permissions" in manifest
        else ()
    )
    optional_permissions = (
        _normalize_string_list(
            manifest["optional_permissions"], "optional_permissions"
        )
        if "optional_permissions" in manifest
        else ()
    )
    host_permissions = (
        _normalize_match_patterns(
            manifest["host_permissions"], "host_permissions"
        )
        if "host_permissions" in manifest
        else ()
    )
    optional_host_permissions = (
        _normalize_match_patterns(
            manifest["optional_host_permissions"], "optional_host_permissions"
        )
        if "optional_host_permissions" in manifest
        else ()
    )
    return ExtensionManifest(
        source=source,
        package_type=package_type,
        manifest_version=manifest_version,
        name=_required_text(manifest, "name"),
        version=_required_text(manifest, "version"),
        description=_optional_text(manifest, "description"),
        permissions=permissions,
        optional_permissions=optional_permissions,
        host_permissions=host_permissions,
        optional_host_permissions=optional_host_permissions,
        content_script_matches=_content_script_matches(manifest),
    )


def inspect_extension_source(
    source: str | os.PathLike[str],
) -> ExtensionManifest:
    """Validate an unpacked directory or ZIP and return normalized metadata."""
    try:
        source_path = Path(source).expanduser()
        is_directory = source_path.is_dir()
        is_file = source_path.is_file()
    except (TypeError, ValueError, OSError) as exc:
        raise _package_error(f"Invalid extension package path: {source!r}.", exc)

    if is_directory:
        data = _read_directory_manifest(source_path)
        package_type = "directory"
    elif is_file:
        data = _read_zip_manifest(source_path)
        package_type = "zip"
    else:
        raise _package_error(f"Extension package does not exist: {source_path}.")
    return _parse_manifest(data, source_path, package_type)


def extension_review_text(extension: ExtensionManifest) -> str:
    """Build a deterministic, human-readable permission review."""
    lines = [f"Permission review for {extension.name} {extension.version}"]
    patterns = extension.site_access_patterns
    if extension.all_sites_access:
        lines.append(
            "WARNING: ALL-SITES ACCESS - this extension may read or change data "
            "across all websites."
        )
    elif patterns:
        lines.append("Site access: " + ", ".join(patterns))
    else:
        lines.append("Site access: none declared.")

    if extension.sensitive_permissions:
        lines.append(
            "WARNING: SENSITIVE PERMISSIONS - "
            + ", ".join(extension.sensitive_permissions)
        )
    else:
        lines.append("Sensitive permissions: none declared.")

    lines.append(
        "API permissions: "
        + (", ".join(extension.permissions) if extension.permissions else "none")
    )
    lines.append(
        "Optional API permissions: "
        + (
            ", ".join(extension.optional_permissions)
            if extension.optional_permissions
            else "none"
        )
    )
    if extension.host_permissions:
        lines.append("Host permissions: " + ", ".join(extension.host_permissions))
    if extension.optional_host_permissions:
        lines.append(
            "Optional host permissions: "
            + ", ".join(extension.optional_host_permissions)
        )
    if extension.content_script_matches:
        lines.append(
            "Content-script matches: "
            + ", ".join(extension.content_script_matches)
        )
    return "\n".join(lines)


inspect_extension_package = inspect_extension_source
preflight_extension_package = inspect_extension_source
format_permission_review = extension_review_text


__all__ = [
    "ExtensionManifest",
    "ExtensionManifestError",
    "ExtensionPackageError",
    "MAX_MANIFEST_BYTES",
    "MAX_ZIP_ENTRIES",
    "MAX_ZIP_UNCOMPRESSED_BYTES",
    "SENSITIVE_PERMISSIONS",
    "extension_review_text",
    "format_permission_review",
    "inspect_extension_source",
    "inspect_extension_package",
    "preflight_extension_package",
]

# OctoBrowse 3.3 — Durable Sessions and Trusted Releases

OctoBrowse 3.3 makes the research browser safer to resume, smoother to use,
and much easier to install. This release adds full-fidelity crash recovery,
strengthens private-data boundaries, moves speech work off the interface
thread, and introduces a verified Windows installer and standalone executable.

## Download

**Most users should download `OctoBrowse-3.3-Setup.exe`.** It installs for the
current Windows user, creates Start Menu and uninstall entries, and upgrades an
existing installation without removing browsing data.

Choose `OctoBrowse-3.3.exe` if you prefer a standalone executable that can be
run without installation.

## Highlights

- **Reliable session recovery** — restores up to 50 standard tabs with their
  original order, duplicate URLs, titles, pinned state, and selected tab.
  Existing URL-only sessions migrate automatically.
- **Responsive Read Aloud** — speech is generated on a worker thread so the
  browser remains responsive. Private-page text requires confirmation every
  time, and temporary audio is removed automatically.
- **Smaller native runtime** — image upscaling now uses Qt's native
  high-quality scaling, removing the OpenCV and NumPy runtime dependency.
- **Safer private downloads** — private download state now comes directly from
  the off-the-record profile and cannot fall through into persistent history.
- **Hardened internal commands** — external websites can no longer invoke the
  privileged `octo:` page-command bridge. Typed address-bar commands continue
  to work normally.
- **Cleaner temporary data** — generated previews and speech files are removed
  when they are no longer needed and are excluded from saved sessions and
  research workspaces.
- **New visual identity** — the application, executable, and installer now use
  consistent OctoBrowse 3.3 branding and version metadata.

## Privacy and reliability fixes

- Clearing download history keeps active transfers and their progress
  callbacks intact.
- Turning on private mode no longer changes the cookie policy of the standard
  browsing profile.
- API-key fields and fallback credential entry are password-masked.
- Private, generated, and ephemeral preview tabs are excluded from crash
  recovery snapshots.
- Session data is saved atomically and legacy session files remain supported.

## Windows release improvements

The new release pipeline builds and verifies both Windows delivery formats. It
checks architecture, embedded version information, bundled OctoBrowse modules,
QtWebEngine resources, frozen-module contents, output freshness, and native
command exit codes before publishing artifacts.

The final build excludes unused OpenCV, NumPy, PocketSphinx model data, Qt debug
resource packs, and unrelated Qt modules. The installer also removes obsolete
frozen-runtime files during upgrades while leaving user browsing data intact.

## Verification

The v3.3 release passed:

- 41 automated regression tests;
- Python compilation and Ruff checks;
- PowerShell packaging-script parsing and `git diff --check`;
- isolated launch smoke tests for both the installer runtime and standalone
  executable;
- frozen archive, PE metadata, architecture, and QtWebEngine resource checks.

## SHA-256 checksums

```text
66727BB82485A9E047FF6C945BC94004C572E6770A220E53C291642A3760655F  OctoBrowse-3.3.exe
DB0733E096B9FE77C1441B67F7B639A593A937DBCEB5DB2AEA8156904F8BA87E  OctoBrowse-3.3-Setup.exe
```

The same values are included in the attached `SHA256SUMS.txt`; detailed build
provenance is available in `build-manifest.json`.

## Important notes

These binaries are not Authenticode-signed. Windows SmartScreen may therefore
show a warning on first launch. Verify the SHA-256 checksum above before
running a downloaded file.

OctoBrowse remains an experimental browser prototype. Private browsing has not
undergone a full security audit, trusted Python extensions run as local code,
and Read Aloud sends invoked page text to the cloud-based Google Text-to-Speech
service. Private pages require explicit confirmation on every use.

Thank you for trying OctoBrowse 3.3.

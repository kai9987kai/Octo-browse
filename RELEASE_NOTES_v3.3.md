# OctoBrowse v3.3 - Durable Sessions and Trusted Releases

12 July 2026

This release advances the v3.2 research browser with full-fidelity crash
recovery, tighter private-data boundaries, a smaller native runtime, and a
release pipeline that produces and verifies both a standalone executable and a
proper Windows installer.

## Browser improvements

- Versioned session snapshots now preserve up to 50 ordinary tabs, including
  order, duplicate URLs, titles, pinned state, and the selected position.
  Legacy URL lists migrate automatically; private, generated, and ephemeral
  preview tabs remain excluded.
- Page upscaling now uses Qt's native high-quality image scaling. The OpenCV and
  NumPy runtime is no longer required, and temporary previews are deleted when
  their tabs close or the application exits.
- The application and window expose a consistent v3.3 identity and a new
  branded OctoBrowse icon.
- The in-app feature audit now reflects the current session, privacy, speech,
  and release implementation.

## Privacy and reliability

- Read Aloud generates `gTTS` audio on a worker thread instead of freezing the
  browser. Private-page text requires explicit confirmation every time and
  temporary audio is automatically removed.
- Private download provenance is supplied directly by the off-the-record
  profile instead of being inferred from a fallible download-page lookup, so
  private URLs and paths cannot fail open into persistent history.
- Clearing download history preserves active rows and their live callback
  targets rather than destroying objects that still receive progress events.
- External pages can no longer invoke the privileged `octo:` command bridge;
  only generated OctoBrowse pages carry the required trust marker. Typed
  address-bar commands continue to work normally.
- Enabling private mode no longer mutates the cookie policy of the standard
  persistent profile, and fallback API-key entry uses password masking.

## Windows release engineering

- `octobrowse/version.py` is the canonical version source for the application,
  PyInstaller builds, Inno Setup, verification, and publishing.
- The stale generated spec with a machine-absolute path has been removed.
- Native command exit codes, target architecture, output timestamps, PE version
  metadata, mandatory QtWebEngine resources, and bundled OctoBrowse modules are
  verified before a build can succeed.
- The release pipeline emits a standalone `OctoBrowse-3.3.exe`, a per-user Inno
  Setup installer, `SHA256SUMS.txt`, and a machine-readable build manifest.
- Executables and the installer carry the branded icon plus FileVersion,
  ProductVersion, description, and product metadata.
- PyInstaller now relies on its focused QtWebEngine hooks instead of collecting
  all of PyQt6. OpenCV, NumPy, PocketSphinx models, and unrelated Qt modules are
  excluded from the release payload.
- The installer cleans obsolete frozen-runtime files on upgrade while leaving
  browsing data in the user's application-data directory untouched.

## Verification

```text
python -m compileall -q main.py alpha.py octobrowse tests
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_release.ps1
```

The final verification stage smoke-launches both the onedir and standalone
executables with an isolated test profile, checks the frozen module archive and
QtWebEngine runtime, and records whether the artifacts are Authenticode-signed.

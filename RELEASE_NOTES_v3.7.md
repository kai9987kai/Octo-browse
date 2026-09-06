# OctoBrowse 3.7 — Research evidence and filter refinements

## New and improved

- **Quote Check:** revisit saved selections and on-device summary sentences on
  their source page. Reports distinguish exact text, whitespace-only changes,
  ambiguous occurrences, and missing quotations, with current surrounding text.
  Use Data > Check Saved Quotes, the command palette, or Check Quotes in a note.
- Saved quote anchors survive persistence and note edits. Full quotations are
  checked instead of their opening words. Source, profile, and navigation
  guards prevent checking against the wrong document. Checks run locally and
  establish text presence, not factual accuracy or publisher authenticity.
- **Expanded filter support:** included/excluded network `$domain=` scopes,
  initiating-frame origins, and exact-selector cosmetic `#@#` exceptions.
  Subscription changes and disabling blocking remove stale injected CSS from
  loaded pages. Per-host CSS caching is bounded and invalidated on updates.
- **Workspace recovery:** malformed pins, timestamps, tab records, Unicode,
  and duplicate IDs recover safely; selected-tab positions are retained when
  invalid entries are dropped. Markdown exports escape unsafe content.
- Deleting research notes or clearing history immediately updates Library
  Search. Quote selection also handles Qt's UTF-16 cursor positions correctly.

## Validation and Windows builds

The Windows build pipeline compiles and tests the source, builds the onedir
application and standalone portable executable, creates an Inno Setup
installer, checks embedded versions and Qt resources, and checks both frozen
Python archives for the application modules, including the new evidence module.
Release smoke tests use temporary settings and profiles, with credential-vault,
environment-key, and legacy-settings access disabled.

Artifact validation and startup smoke outcomes are recorded in
`release/build-manifest.json`; `release/SHA256SUMS.txt` records artifact hashes.
The startup smoke exercises application/profile creation and shutdown. It is
separate from full live page-rendering validation, which was blocked on this
machine during development by Qt graphics-context errors.

The portable file is `OctoBrowse-3.7.exe`; the per-user installer is
`OctoBrowse-3.7-Setup.exe`. These artifacts are unsigned unless the manifest
reports a valid Authenticode signature. Existing installations use the same
installer AppId for upgrades.

See [research rationale and usage](docs/research-advance.md) for sources,
limits, and regression coverage.

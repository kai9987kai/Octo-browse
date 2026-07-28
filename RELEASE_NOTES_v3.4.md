# OctoBrowse 3.4 — Guardian Sessions

OctoBrowse 3.4 focuses on durable everyday browsing, clearer trust signals,
and stronger separation between standard and private sessions.

## Highlights

- **Persistent standard browsing:** normal tabs now use a named WebEngine
  profile, so cookies, logins, cache, local storage, and persistent site
  permissions survive a restart. Private tabs remain off the record.
- **Site Trust Center:** click the address-bar trust badge to see the exact
  connection type, active profile, content overrides, permission state, and
  per-site blocking telemetry.
- **Permission-aware privacy:** camera, microphone, and screen-capture choices
  last only for the page lifetime; private-tab choices are never written to
  OctoBrowse settings. Persistent location and notification choices can be
  reviewed or reset.
- **Gesture-aware popups:** user-requested windows open as tabs while automatic
  script popups are blocked and counted per tab.
- **Private telemetry isolation:** standard and private profiles now maintain
  separate in-memory tracker and HTTPS-upgrade statistics.
- **Private content-control isolation:** JavaScript and image overrides created
  in a private tab stay in memory and never alter persistent standard-profile
  settings.
- **Safe MV3 inspection:** folders and ZIP packages can be audited without
  installation or execution. The inspector rejects Manifest V2, dangerous ZIP
  paths, duplicate entries, and oversized packages, and highlights broad host
  or sensitive required and optional API access.
- **PDF export:** save the active page directly as a PDF with completion
  reporting.
- **Faster long-page AI context:** broad summary sampling no longer scales
  cubically; a 50,000-chunk stress case completes in a few hundredths of a
  second on the development machine.
- **More honest internal identity:** only exact OctoBrowse-generated pages
  receive the trusted application badge.

## Compatibility and safety note

Native extension execution is not enabled in this release. Live compatibility
testing found that enabling an extension through the current PyQt/Qt WebEngine
Windows binding can terminate the process. OctoBrowse therefore exposes only
the non-executing package inspector until that runtime path is stable.

Python plugins remain trusted local automation and are disabled by default
behind Developer Mode.

## For source users

OctoBrowse 3.4 requires Python 3.10+ and PyQt6/PyQt6-WebEngine 6.8 or newer.
Install dependencies from `requirements.txt`, then run:

```powershell
python main.py
```

The release artifacts are unsigned unless a code-signing certificate is added
to the local packaging process.

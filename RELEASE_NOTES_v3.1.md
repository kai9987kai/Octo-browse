# OctoBrowse 3.1

A large feature + privacy + security release for the PyQt6/QtWebEngine browser.

## Highlights

### Privacy & content blocking
- **EasyList-compatible filter engine** — network rules (`||domain^`, `@@`
  exceptions, hosts lines, wildcard/separator path patterns) indexed by literal
  token for fast per-request matching, parsed off the UI thread. Load via
  **Tools → Update EasyList** or import any Adblock-format file; the cached list
  refreshes itself weekly.
- **Cosmetic element-hiding** (`##selector`, generic and per-domain) injected as
  chunked CSS when ad blocking is on.
- **HTTPS-only mode**, **Global Privacy Control** (`Sec-GPC`/`DNT`) headers, and
  **per-site permission prompts** (camera, mic, location, notifications) with
  remembered decisions.
- **Per-site content controls** — disable JavaScript or image loading per site.

### Performance & UX
- **SQLite-backed history** with titles, visit counts, and **frecency-ranked**
  address suggestions (auto-migrates from the old JSON history).
- **Background-tab hibernation** via Chromium's page-lifecycle API to reclaim
  memory; tabs reload when reselected.
- Download manager with **pause/resume/cancel**, open file/folder, and a
  persistent download history.
- HTML5 fullscreen for video, built-in PDF viewer, render-crash auto-recovery,
  find-in-page match counter, connection security badge, configurable search
  engine, tab navigation shortcuts (Ctrl+Tab, Ctrl+1–9), and per-tab mute.

### Extensibility
- **Permissioned plugin API** — plugins are Python files with a `MANIFEST` and an
  `activate(api)` entry point, installed through **Tools → Plugin Manager**. Each
  declares permissions you approve on first run; every API call is
  permission-checked. See `examples/page_word_count.py`.

## Security hardening (this release)
Adversarial review of the new subsystems surfaced and fixed:
- Plugin permission grants are bound to the plugin file's SHA-256, so a different
  file reusing an approved name cannot inherit its permissions.
- Plugin `fetch()` blocks private/loopback/link-local/reserved hosts (SSRF
  guardrail) and no longer follows redirects.
- Reader View escapes page-derived keywords (prevented script injection into the
  internal `octobrowse.local` origin).
- Dashboard / Tab Overview links pass through a URL-scheme allowlist, neutralizing
  `javascript:`/`data:` URLs from bookmarks, history, or titles.

> Note: plugins run in-process with restricted builtins. This is a guardrail
> against accidents, not a hard sandbox — only install plugins you trust.

## Install (Windows)
Download `OctoBrowse-3.1-Setup.exe` from the assets below and run it. It's a
standard per-user installer (no admin prompt) with Start Menu and optional
desktop shortcuts, and a proper uninstaller / Add-or-Remove-Programs entry.
The binary is unsigned, so Windows SmartScreen will show a "More info → Run
anyway" prompt on first launch. Or run from source:

```powershell
py -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Asset integrity
`OctoBrowse-3.1-Setup.exe` SHA-256:

```
CC9C48C2E87FF15122A682F1F31EAA898250FAE973B918EAD1E667B64854EBA9
```

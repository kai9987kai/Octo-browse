# Octo-browse

Octo-browse is an experimental Python + PyQt6/QtWebEngine desktop browser. It
combines a normal tabbed browser surface with power tools for notes, history,
bookmarks, page source, page saving, ad blocking, private tabs, page upscaling,
text-to-speech, voice commands, cited AI page research, weather/news side panels,
named research workspaces, a session password scratchpad, and opt-in trusted
Python automation.

## Entry points

- `main.py` is the maintained application.
- `alpha.py` is now a compatibility launcher that starts the same maintained
  app. The previous alpha-only features were merged into `main.py`.

## Key features

- Tabbed browsing with movable/closable tabs, dynamic page titles, Ctrl+Tab /
  Ctrl+1-9 tab navigation, and per-tab audio mute.
- Activity-safe background-tab hibernation uses Qt's recommended lifecycle
  state, skips pinned tabs and pages with active content or forms, and reloads
  discarded tabs automatically when reselected.
- Named Research Workspaces save ordinary tabs, order, active position, and
  pinned state; workspaces can be reopened alongside the current session,
  restored as a replacement, searched from Library Search, or exported as
  Markdown or as a research pack containing matching notes. Private tabs are
  never captured.
- Selection-anchored Research Notes (`Ctrl+Alt+N`) preserve source title, URL,
  quoted evidence, commentary, timestamps, and kind in a versioned bounded
  format. Legacy notes migrate automatically; notes can be viewed, edited,
  copied as Markdown, deleted, and exported with a workspace. Private-tab and
  internal-page content is rejected by the shared persistence path used by the
  UI, AI summaries, and plugins.
- Verifiable Offline Snapshots (`Ctrl+Shift+S`) save the complete active page
  as one portable MHTML archive, then create an adjacent provenance sidecar
  with the source, capture time, runtime versions, byte size, and SHA-256.
  Verification runs off the UI thread and rejects unsafe sidecar paths or
  modified archives. Private-page capture requires an explicit disk-persistence
  warning and never enters standard download history. The sidecar provides
  local integrity checking, not signer authentication.
- A shared, bounded readability pipeline prefers visible semantic
  `<article>`/`<main>` content, removes navigation, advertisements, dialogs,
  and other page furniture, and safely falls back to bounded plain text. It
  runs in Qt's isolated Application World and returns text rather than
  untrusted HTML. Reader View, Page Insights, Read Aloud, cited summaries, and
  page Q&A now use the same document-bound extraction result.
- Frecency-ranked address suggestions (Mozilla-style visit-count x recency
  scoring) backed by titled history entries with visit counts and timestamps.
- Configurable default search engine: Google, DuckDuckGo, Bing, Brave, or
  Startpage.
- HTTPS-only mode, Global Privacy Control through both `Sec-GPC` and
  `navigator.globalPrivacyControl`, optional legacy DNT, and an optional strict
  third-party cookie/storage filter.
- Per-site permission prompts (camera, microphone, location, notifications)
  now respect Qt's real permission lifetimes: persistent standard-profile
  choices can be reviewed and reset, while camera, microphone, screen, and
  private-tab choices are never written to OctoBrowse settings.
- Clickable Site Trust Center with exact origin/profile state, honest HTTPS
  wording, per-site tracker and popup counts, permission state, and shortcuts
  to content controls. Gesture-driven new windows open as tabs while automatic
  script popups are blocked.
- A named persistent standard profile retains normal site logins, storage,
  and cache across restarts. Private tabs remain isolated in a separate
  off-the-record profile with separate privacy telemetry.
- A non-executing Manifest V3 inspector audits extension folders and ZIPs for
  required and optional API/host access plus content-script matches. It rejects
  legacy manifests, unsafe ZIP paths, duplicate entries, and oversized packages
  before any code can run.
- Find-in-page match counter, HTML5 fullscreen for video players, built-in PDF
  viewer, and render-process crash auto-recovery.
- Cleaner browser chrome with a compact navigation toolbar, left workspace rail,
  full menu bar, status badges, a command palette (`Ctrl+K`), and in-page find
  (`Ctrl+F`).
- Dashboard tab with recent history, bookmarks, todo counts, weather status,
  shortcuts, saved-tab counts, downloads, ad-block stats, and clickable action
  tiles for the main browser workspaces.
- Feature Audit page for checking that merged main/alpha-era features and newer
  Octo Browser capabilities are present.
- Transactional SQLite/FTS5 Library Search (`Ctrl+Shift+F`) for fast ranked
  search across ordinary open tabs, history, bookmarks, reading-list items,
  research-note titles/quotes/commentary, tasks, and workspaces. It falls back
  safely when FTS5 is unavailable and never indexes private tabs.
- Smart address commands: `octo:dashboard`, `octo:identity`, `octo:tabs`,
  `octo:features`, `octo:library`, `octo:downloads`, `octo:reading`,
  `octo:history`, `octo:bookmarks`, `octo:todos`, `octo:notes`,
  `octo:permissions`, `octo:extensions`, `octo:workspaces`, plus bang searches
  like `!yt`, `!gh`, `!w`, `!maps`, `!news`, `!pypi`, and `!mdn`.
- Address-bar autocomplete for Octo commands, bang searches, history,
  bookmarks, and reading list items.
- Standard and private tabs. Private tabs use a separate off-the-record
  `QWebEngineProfile`.
- Ad and tracker blocking through `QWebEngineUrlRequestInterceptor`, with
  O(host-labels) suffix matching, an expanded tracker domain list, and an
  in-session privacy report covering blocks and HTTPS upgrades.
- EasyList-compatible filter list support: `||domain^` rules, path-level `@@`
  exceptions, hosts-file lines, wildcard/separator patterns, resource-type
  options, inverse types, and first/third-party constraints. Literal-token
  indexing keeps matching fast. Lists load from Tools > Update EasyList or an
  imported Adblock-format file and refresh weekly.
- Cosmetic element-hiding rules (`##selector`, generic and per-domain) are
  injected into pages as chunked CSS when ad blocking is on.
- Trusted Python automation API: plugins are Python files with a `MANIFEST`
  and `activate(api)` entry point. Declared capabilities document intended API
  use, but arbitrary Python cannot be sandboxed in-process. Execution is off by
  default and requires explicit Developer Mode; only run code you trust. See
  `examples/page_word_count.py`.
- `examples/mv3_hello` is a permission-free package for verifying the Manifest
  V3 inspector without contacting the network.
- SQLite-backed browsing history (one upsert per visit instead of rewriting a
  JSON blob), with automatic migration from the old format.
- Download manager with pause/resume/cancel, open file/folder actions, and a
  persistent download history.
- Per-site content controls: disable JavaScript or image loading for chosen
  sites (Tools > Site Controls). Standard choices persist; private-tab choices
  stay in memory and never enter the settings file.
- Persistent settings, workspaces, bookmarks, versioned research notes, and
  todos stored as JSON under the platform app-data directory. History lives in
  `history.sqlite` and the rebuildable unified-search index in
  `library.sqlite`; API keys use the OS credential vault through `keyring` when
  available.
- Crash-resilient, versioned session restore preserves as many as 50 standard
  tabs, including order, duplicate URLs, titles, pinned state, and the active
  position, with an atomic 30-second autosave. Legacy URL-only sessions migrate
  automatically and closing all ordinary tabs persists an empty session.
- Reopen recently closed tabs with `Ctrl+Shift+T`.
- Download handling with a save prompt, progress state, and downloads panel.
- Persistent reading list panel for pages to revisit later.
- User-initiated target-blank and popup-style requests open as normal tabs;
  script-only popup requests are blocked per tab.
- Sidebar panels for structured research notes, calendar, todos, history,
  news, bookmarks, and extension code. Page-aware AI chat has its own focused
  dialog.
- Page tools: save page HTML, save and verify complete MHTML research snapshots,
  view source, open current page in a new tab, semantic reader view, article
  insights,
  screenshot saving, upscaled screenshot preview, native PDF export, zoom controls,
  duplicate tab, copy URL, copy Markdown link, tab overview, browser identity,
  site info, custom user agent, themes, and fullscreen.
- Native Qt WebEngine identity avoids contradictory User-Agent and Client Hint
  spoofing; the identity page reports the actual Chromium runtime and security
  patch base. A custom User-Agent remains available for compatibility testing.
- Optional OpenAI summaries and page Q&A select relevant labelled excerpts,
  require evidence citations, isolate untrusted page instructions, set
  `store=False`, and require per-use consent before sending private-tab text.
- Optional weather and news fetches run off the UI thread, with timeouts.
- Python automation is treated as trusted local code. A reduced-builtins path
  helps prevent accidents, while the full-access path retains an explicit
  warning; neither path is presented as a security sandbox.

## Requirements

- Python 3.10+
- PyQt6 and PyQt6-WebEngine 6.8+ (modern permission APIs)
- See `requirements.txt` for the full dependency list.

Optional system/runtime notes:

- Voice commands usually require a working microphone and PyAudio support for
  `SpeechRecognition`.
- Text-to-speech uses the cloud-based `gTTS` service off the UI thread, opens
  the generated audio with the OS, and removes its temporary file. Private-tab
  text is sent only after confirmation on every use.
- Weather needs an OpenWeather API key.
- News needs a NewsAPI key.
- AI features need an OpenAI API key.

## Install

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The compatibility launcher still works:

```bash
python alpha.py
```

## Building the Windows release

The one-command release pipeline compiles and tests the source, builds both
application formats, creates the Inno Setup installer, smoke-tests the frozen
apps, checks embedded versions and QtWebEngine resources, and writes SHA-256
checksums plus a JSON build manifest:

```powershell
# Requires Inno Setup: winget install --id JRSoftware.InnoSetup
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_release.ps1
```

The release outputs are:

- `release\OctoBrowse-<version>.exe`: standalone portable x64 executable.
- `release\OctoBrowse-<version>-Setup.exe`: per-user installer with shortcuts,
  upgrade handling, Add/Remove Programs registration, and an uninstaller.
- `release\SHA256SUMS.txt` and `release\build-manifest.json`: integrity and
  provenance records.
- `dist\OctoBrowse\OctoBrowse.exe`: onedir application used by the installer;
  it requires the adjacent `_internal` folder and is not standalone.

Individual stages remain available as `build_app.ps1`, `build_portable.ps1`,
`build_inno.ps1`, and `verify_release.ps1`. The IExpress builder is retained as
a clearly named fallback package when Inno Setup is unavailable.

To publish a GitHub release (requires an authenticated `gh auth login`):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\publish_release.ps1
```

The generated binaries are unsigned unless a code-signing certificate is added
to the local release process, so Windows SmartScreen may warn on first run. The
manifest records the Authenticode status rather than implying a signed build.

## Configuration

You can configure keys in the Settings dialog, or set environment variables
before launching:

```bash
OPENAI_API_KEY=...
OCTOBROWSE_OPENAI_MODEL=gpt-5.6-luna
OPENWEATHER_API_KEY=...
NEWS_API_KEY=...
```

API keys entered in the app are stored in the operating-system credential
vault through `keyring`. If no usable keyring backend exists, OctoBrowse falls
back to the legacy JSON fields and the Settings dialog should not be treated as
a secure vault on that system.

## Security notes

- Python plugins and the extension lab run in-process as trusted automation.
  They are disabled by default behind Developer Mode. Manifest permissions and
  reduced builtins are usability guardrails, not a security boundary.
- The trusted extension action runs code with full Python access and should be
  treated like running a local script.
- The session password scratchpad is in-memory only. It is not a persistent
  password manager.
- Private tabs share a separate off-the-record profile for the current app
  session; none of that profile's storage is made persistent. This prototype
  should not be treated as a hardened privacy browser.
- The Manifest V3 inspector does not install or execute extension code. Native
  extension runtime support remains disabled until the underlying Qt/PyQt
  enablement path is stable on supported Windows builds.
- Read Aloud uses Google Text-to-Speech. Standard pages are sent when the action
  is invoked; private pages require an explicit confirmation every time.
- The filter engine implements a practical subset of Adblock Plus syntax;
  domain scoping and advanced procedural cosmetic rules are still skipped, so
  coverage remains below a full uBlock Origin.

## Architecture map

- `OctoBrowse(QMainWindow)`: main window, toolbars, tabs, sidebars, actions.
- `OctoRequestInterceptor`: ad/tracker blocking, HTTPS-only upgrades, and
  Global Privacy Control headers with per-session stats.
- `octobrowse/filtering.py` / `FilterParseWorker`: testable EasyList-subset
  parsing and indexed matching, parsed off the UI thread.
- `octobrowse/ai_context.py`: source chunking, deterministic relevance
  selection, bounded broad-page sampling, citations, and untrusted-content
  prompt boundaries.
- `octobrowse/extensions.py`: defensive, non-executing Manifest V3 directory/ZIP
  inspection, normalization, size/path limits, and permission review.
- `octobrowse/library_index.py`: bounded transactional SQLite/FTS5 metadata
  search with sanitized prefix queries, deterministic ranking, and LIKE
  fallback.
- `octobrowse/research.py`: versioned research-note migration, validation, and
  Markdown/workspace research-pack export.
- `octobrowse/readability.py`: bounded semantic DOM scoring, text-only article
  extraction, trusted source binding, and malformed-result normalization.
- `octobrowse/snapshots.py`: portable snapshot naming, atomic provenance
  sidecars, streamed SHA-256 hashing, and path-safe integrity verification.
- `octobrowse/workspaces.py`: versioned workspace validation and Markdown
  export.
- `octobrowse/urls.py`: exact internal URL trust-boundary classification.
- `OctoPluginAPI`: intended-capability API passed to trusted Python automation.
- `HistoryDatabase`: SQLite visit store (url, title, visit count, last visit)
  with legacy JSON import.
- `SettingsStore` / `CredentialStore`: atomic JSON state, malformed-data
  recovery, legacy migration, and OS-keyring secret storage.
- `ApiFetchWorker`: weather/news requests on a worker thread.
- `OpenAIWorker`: bounded, non-stored Responses API calls on a worker thread.
- `CommandPalette`: keyboard-first command discovery and execution.
- `LibrarySearchDialog`: indexed search across tabs and saved browser
  collections, with note/workspace-aware result routing.
- `SettingsDialog`: homepage, model, location, and API-key settings.

## Roadmap

- Optional full-page text capture with explicit storage controls; the current
  FTS5 index intentionally stores browser metadata and user-authored research
  text, not page bodies.
- Procedural cosmetic filters (`#?#`) and cosmetic exceptions (`#@#`).
- Revisit native extension execution after Qt/PyQt provides a stable Windows
  enablement path; retain provenance and permission review before activation.

## Tests

```bash
python -m unittest discover -s tests -v
python -m py_compile main.py alpha.py
python tests/live_ui_smoke.py
```

GitHub Actions runs the unit regression suite on Python 3.10 and 3.13. The
live smoke additionally constructs both profile types and drives the real MV3
inspector dialog against the bundled permission-free sample.

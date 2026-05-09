# Octo-browse

Octo-browse is an experimental Python + PyQt6/QtWebEngine desktop browser. It
combines a normal tabbed browser surface with power tools for notes, history,
bookmarks, page source, page saving, ad blocking, private tabs, page upscaling,
text-to-speech, voice commands, AI page summarisation, weather/news side panels,
a session password scratchpad, and a constrained extension lab.

## Entry points

- `main.py` is the maintained application.
- `alpha.py` is now a compatibility launcher that starts the same maintained
  app. The previous alpha-only features were merged into `main.py`.

## Key features

- Tabbed browsing with movable/closable tabs and dynamic page titles.
- Cleaner browser chrome with a compact navigation toolbar, left workspace rail,
  full menu bar, status badges, a command palette (`Ctrl+K`), and in-page find
  (`Ctrl+F`).
- Dashboard tab with recent history, bookmarks, todo counts, weather status,
  shortcuts, saved-tab counts, downloads, ad-block stats, and clickable action
  tiles for the main browser workspaces.
- Feature Audit page for checking that merged main/alpha-era features and newer
  Octo Browser capabilities are present.
- Library Search (`Ctrl+Shift+F`) for searching open tabs, history, bookmarks,
  reading list items, notes, and tasks from one dialog.
- Smart address commands: `octo:dashboard`, `octo:identity`, `octo:tabs`,
  `octo:features`, `octo:library`, `octo:downloads`, `octo:reading`,
  `octo:history`, `octo:bookmarks`, `octo:todos`, `octo:notes`, plus bang
  searches like `!yt`, `!gh`, `!w`, `!maps`, `!news`, `!pypi`, and `!mdn`.
- Address-bar autocomplete for Octo commands, bang searches, history,
  bookmarks, and reading list items.
- Standard and private tabs. Private tabs use a separate off-the-record
  `QWebEngineProfile`.
- Ad blocking through `QWebEngineUrlRequestInterceptor`, with safer host/domain
  matching and an in-session privacy report.
- Persistent settings, bookmarks, history, notes, and todos stored under the
  platform app-data directory, with migration from the old
  `octobrowse_settings.json` file if it exists.
- Session restore for standard tabs from the previous run.
- Reopen recently closed tabs with `Ctrl+Shift+T`.
- Download handling with a save prompt, progress state, and downloads panel.
- Persistent reading list panel for pages to revisit later.
- Target-blank and popup-style new-window requests open as normal Octo Browser
  tabs.
- Sidebar panels for notes/chat, calendar, todos, history, news, bookmarks, and
  extension code.
- Page tools: save page HTML, view source, open current page in a new tab,
  reader view, page insights, screenshot saving, upscaled screenshot preview,
  zoom controls,
  duplicate tab, copy URL, copy Markdown link, tab overview, browser identity,
  site info, custom user agent, themes, and fullscreen.
- Octo Browser identity is applied through the HTTP user agent and injected
  `navigator` values so browser-check pages can see `OctoBrowser`.
- Optional OpenAI page summarisation and page Q&A through the current OpenAI
  Responses API.
- Optional weather and news fetches run off the UI thread, with timeouts.
- Extension lab executes code in a constrained namespace with `browser`,
  `current_tab`, and a small safe builtins set instead of full process globals.
- A separate trusted extension action preserves the original full Python
  execution behavior behind an explicit warning.

## Requirements

- Python 3.10+
- PyQt6 and PyQt6-WebEngine
- See `requirements.txt` for the full dependency list.

Optional system/runtime notes:

- Voice commands usually require a working microphone and PyAudio support for
  `SpeechRecognition`.
- Text-to-speech uses `gTTS` and opens the generated audio file with the OS.
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

## Configuration

You can configure keys in the Settings dialog, or set environment variables
before launching:

```bash
OPENAI_API_KEY=...
OCTOBROWSE_OPENAI_MODEL=gpt-5-mini
OPENWEATHER_API_KEY=...
NEWS_API_KEY=...
```

Settings entered in the app are stored as local JSON. Do not treat this as a
secure vault for long-lived secrets.

## Security notes

- The extension lab is intentionally constrained, but it still exposes the
  running browser object. Run only code you understand.
- The trusted extension action runs code with full Python access and should be
  treated like running a local script.
- The session password scratchpad is in-memory only. It is not a persistent
  password manager.
- Private tabs isolate browser profile storage for new private tabs, but this
  prototype should not be treated as a hardened privacy browser.
- The ad blocker uses a small static domain list, not full EasyList/uBlock rule
  parsing.

## Architecture map

- `OctoBrowse(QMainWindow)`: main window, toolbars, tabs, sidebars, actions.
- `AdBlockerInterceptor`: request interception, domain blocking, block stats.
- `SettingsStore`: JSON load/save and legacy settings migration.
- `ApiFetchWorker`: weather/news requests on a worker thread.
- `OpenAIWorker`: page summarisation and page Q&A on a worker thread.
- `CommandPalette`: keyboard-first command discovery and execution.
- `LibrarySearchDialog`: unified search across tabs and saved browser
  collections.
- `SettingsDialog`: homepage, model, location, and API-key settings.

## Roadmap

- Replace the static ad-domain list with real filter-list parsing.
- Add per-site permissions and content controls.
- Move persistent user data to SQLite.
- Add a download manager.
- Replace the extension lab with a real permissioned plugin API.

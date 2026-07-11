# OctoBrowse v3.2 - Research Workspaces and Trust

11 July 2026

This release turns OctoBrowse's existing collection of browser tools into a
more coherent private-research workflow, while correcting important filter,
identity, session, and Python-automation trust issues.

## New features

- **Research Workspaces** save and restore named sets of ordinary tabs,
  including tab order, active position, and pinned state. Workspaces can open
  alongside the current session, replace ordinary tabs, appear in Library
  Search, and export to Markdown. Private tabs are never captured.
- **Cited page assistant** replaces fixed-prefix page prompts with deterministic
  source chunking and query-relevant excerpt selection. Summaries and answers
  cite `[S1]`-style source labels, can be copied, and summaries can be saved as
  notes.
- **Pinned tabs** stay active and are excluded from automatic hibernation.
- **Strict cookie mode** can block third-party cookies and equivalent storage
  access through Qt WebEngine's cookie filter.
- **OS credential storage** moves OpenAI, weather, and news API keys to the
  system keyring when a backend is available, with automatic migration and a
  compatibility fallback.
- **CI and regression suite** cover Python 3.10 and 3.13, with tests for prompt
  boundaries, relevance selection, filters, settings recovery, URL trust,
  credentials, and workspaces.

## Correctness and privacy

- EasyList `$script`, `$image`, inverse type, and `$third-party` options now
  constrain matching instead of becoming unconditional blocks. Path-level
  exceptions are supported.
- Exact internal-origin checks prevent attacker URLs containing
  `octobrowse.local` from receiving internal treatment.
- Empty tab sessions persist correctly instead of resurrecting previously
  closed tabs. Session state is atomically autosaved every 30 seconds.
- Tab hibernation follows Qt's `recommendedState()`, protecting active media,
  downloads, notifications, and partially filled forms.
- Private URLs are omitted from standard-profile tab overview pages and private
  download history is not persisted.
- Global Privacy Control now sets both `Sec-GPC: 1` and
  `navigator.globalPrivacyControl`; legacy DNT is a separate opt-in.
- Clear Browser Data now includes visited links, saved permissions, per-site
  controls, and storage for active origins.

## AI safety and API updates

- Page-controlled text is escaped, explicitly marked as untrusted data, and
  kept below the application instruction layer.
- Responses API calls pass `instructions` and `input` separately, use a bounded
  timeout, set `store=False`, and default new installs to `gpt-5.6-luna`.
- Sending private-tab text to OpenAI requires explicit confirmation on every
  use.
- Page Q&A now has a dedicated non-modal dialog with a real input field; Enter
  reliably submits instead of depending on parent-window key handling.

## Compatibility and trust changes

- The hard-coded Chrome 126 and synthetic Client Hints spoof has been removed.
  OctoBrowse now uses Qt WebEngine's internally consistent native identity and
  reports the actual Chromium runtime and security patch base. Existing custom
  User-Agent overrides remain intact.
- Python plugins and the extension lab are now accurately presented as trusted
  local automation, disabled by default behind Developer Mode. Manifest grants
  document intended API use but are no longer described as a security sandbox.
- Duplicate `QAction` shortcuts were removed to prevent ambiguous hotkeys.
- App shutdown waits asynchronously for active worker threads instead of
  destroying them after a 300 ms timeout.

## Verification

```text
python -m unittest discover -s tests -v
python -m py_compile main.py alpha.py
```

The source UI was also launched and visually checked on Windows with Qt
WebEngine, including the dashboard and Research Workspaces manager.

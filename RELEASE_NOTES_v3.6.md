# OctoBrowse 3.6 — Anchored

OctoBrowse 3.6 audits everything 3.5 shipped, fixes what the audit found —
including three defects introduced by 3.5 itself — and turns the summarizer's
character offsets into quotes that can still be found after a page changes.

## Highlights

### Relocatable quote anchors

- **Find a quote again after the page has changed.** A stored character offset
  identifies a quote only in the exact text it came from; reload a week later
  and it silently points at the wrong words. The new anchor format keeps the
  quote plus a window of the text either side, following the W3C Web
  Annotation model, and relocates in confidence order: a unique match wins
  outright, an ambiguous one is resolved by whichever occurrence best
  reproduces the stored context, and a quote that is genuinely gone reports
  failure instead of guessing — a wrong highlight is worse than an honest
  "not on this page any more".
- **Wired into on-device summaries.** Every bullet in an on-device summary is
  now anchored. Put the cursor on a quoted line and **Find in Page** scrolls
  the live page to that exact sentence and highlights it.
- **Whitespace-tolerant.** A page re-rendered with different line wrapping
  still matches, at reduced confidence, so the result says how sure it is.
- **Persistable.** Anchors are plain JSON-safe dicts that fail closed on
  malformed stored data, so they can outlive the session that made them.

### Correctness — including three regressions from 3.5

- **A denied permission could be silently granted next time.** `3.5` widened
  the permission handler's error path to fail closed, but the decision was
  persisted *before* Qt accepted it. If anything failed afterwards — and
  `save_settings` walks live views while the permission modal pumps events,
  so it can — an "Allow" was left on disk for a request that was actually
  denied, and the next request read that stored value and granted with no
  prompt. Decisions are now recorded only after Qt has applied them, and a
  failed save is reported rather than converted into a denial.
- **Two public-suffix data errors.** `sch.uk` shipped as a plain rule when the
  real list entry is `*.sch.uk`, collapsing every UK school under a local
  authority onto one site; and the seven `!city.<city>.jp` exceptions shipped
  without the `*.<city>.jp` wildcards they exist to carve holes in, merging
  unrelated Japanese organisations. Both disabled `$third-party` rules exactly
  where they were needed. A new structural test asserts every exception has
  its parent wildcard, which is the invariant that would have caught both.
- **A shared host's apex is not the same site as its subdomains.** The
  first-party short-circuit treated any DNS ancestor as the same site, so a
  document served at `neocities.org` was first-party with every user's
  subdomain on the platform. An ancestor now only counts when somebody
  actually owns it.
- **A lost password key.** Making the cipher lazy in 3.5 introduced a
  check-then-act race: two callers could each generate a key and the second
  assignment discarded the first, leaving anything encrypted with the lost key
  permanently unreadable. Measured at 6.3% of contended trials before the fix;
  0 of 200 after. `PasswordManager.available()` also reflects a *constructed*
  cipher again, so the password dialog no longer opens when cryptography
  resolves but fails to load its backend — the common Windows case.
- **The blocker no longer fails open on an unknown origin.** `about:blank`,
  `file://` and `data:` documents all yield an empty first-party host, which
  made *both* `$third-party` and `$~third-party` rules non-matching. An unknown
  origin is now treated as third-party: a blocker should fail toward blocking.
- **Smaller fixes:** `available()` no longer lets an exception from a broken
  parent package escape into a Qt slot; host:port and bracketed IPv6 forms are
  normalised before site identity is computed; and install messages are
  generated from one table instead of seven hand-written strings that had
  already drifted apart.

### Performance

- **The address bar no longer scans the history list on every navigation.**
  Each URL change did a linear scan of up to 500 `QListWidget` rows — one PyQt
  round-trip per row — plus a full frecency re-sort and a completer rebuild,
  and every title change scanned again, several times per page load. The
  widget side now has the same URL-keyed index the data side always had:
  **1.68 ms → 0.23 µs** per lookup, measured at a full 500-entry history.
  Completer rebuilds are coalesced behind a 300 ms debounce, flushed when a
  suggestion is accepted so it never acts on stale data.
- **Frecency ranking moved into `octobrowse/frecency.py`** and now has the
  tests its bucket boundaries never had, including malformed, missing,
  negative and NaN timestamps, and a stable tie-break so equal-scoring entries
  cannot reshuffle under the cursor.

## Test suite

229 tests, all passing offline and headless (up from 178):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests
```

Coverage for `octobrowse/` holds at 89% against a widened codebase. New suites
cover quote anchoring (context windows, ambiguity resolution, document edits,
re-wrapped whitespace, malformed stored data, and round-tripping against real
summarizer output), frecency bucket edges, the public-suffix ruleset
invariants, and the password-key race.

## Compatibility and safety note

The public-suffix subset remains a committed snapshot, not a network-updated
mirror. Quote anchors locate text, they do not verify it: an anchor proves
where a quote *is now*, not that the page still says what it said when the
quote was taken — use a verified snapshot for that.

Native extension execution remains disabled. Python plugins remain trusted
local automation, off by default behind Developer Mode.

## Windows artifacts

Built with PyInstaller 6.20 on Python 3.13.14, target `win-amd64:64`. Both
binaries pass the frozen-app smoke test.

| Artifact | Size | SHA-256 |
| --- | --- | --- |
| `OctoBrowse-3.6-Setup.exe` (installer, per-user) | 136 MB | `7D153CF75A61CF5216F0277A0433B2E1D74F3A16D473BC813DBD02DE6DA74E9D` |
| `OctoBrowse-3.6.exe` (portable, single file) | 188 MB | `1C38176759E1E69C901A0ED2A318C00E8B0008A3471519D93850CB643FC89BA7` |

Verify a download before running it:

```powershell
Get-FileHash .\OctoBrowse-3.6-Setup.exe -Algorithm SHA256
```

Both artifacts are **unsigned** — Windows SmartScreen will warn on first run
until a code-signing certificate is added to the packaging process.

`release/SHA256SUMS.txt` and `release/build-manifest.json` carry the same
values alongside the build's Python version, file counts, and Authenticode
status.

## For source users

OctoBrowse 3.6 requires Python 3.10+ and PyQt6/PyQt6-WebEngine 6.8 or newer.
Install dependencies from `requirements.txt`, then run:

```powershell
python main.py
```

The release artifacts are unsigned unless a code-signing certificate is added
to the local packaging process.

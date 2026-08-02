# OctoBrowse 3.5 — Independent

OctoBrowse 3.5 removes the browser's remaining dependencies on things outside
the machine it runs on: a cloud account to summarize a page, a network-updated
list to tell one site from another, and a second of startup spent loading
features most sessions never open.

## Highlights

### On-device summaries

- **Summarize any page with no API key and no network.** A new deterministic
  extractive summarizer runs in-process using only the standard library. It is
  available from Tools ▸ Summarize Page (On-Device) and from the command
  palette, and it works in private tabs with no consent prompt because nothing
  leaves the process.
- **Bullets that cannot be invented.** Every line of an on-device summary is a
  sentence copied word-for-word from the page, carrying the character offset it
  came from. A reader can always check a bullet against its source. The summary
  is labelled as a mechanical selection, not an understanding of the article.
- **Declining a key is no longer a dead end.** The OpenAI key prompt now offers
  the on-device summarizer instead of ending in an error.
- **Bounded on long pages.** Ranking is TextRank-flavoured degree centrality
  over a TF-IDF similarity graph with maximal-marginal-relevance selection, and
  the quadratic stage is capped so a 120,000-character page still completes in
  well under a second. Identical input always produces identical bullets.

### Blocking correctness

- **Third-party rules now fire on shared hosting.** Site identity previously
  folded every host to its last two labels unless it matched a 30-entry table,
  so `tracker.github.io` and `victim.github.io` looked like one site and every
  `$third-party` rule against them silently declined to fire. A committed
  offline subset of the Public Suffix List — covering the ICANN ccTLD second
  levels plus the private-section platforms trackers actually use (`github.io`,
  `pages.dev`, `vercel.app`, `s3.amazonaws.com`, `herokuapp.com`, dynamic-DNS
  parents and more) — now determines registrable domains, with full wildcard
  and exception-rule handling. A host and its own ancestor stay first-party;
  only sibling subdomains under a shared suffix are treated as cross-site.
- **No network dependency.** The suffix data ships in the repository. An
  out-of-date subset degrades to the previous last-two-labels answer rather
  than to a wrong one.

### Stability and privacy

- **Blocking telemetry is thread-safe.** Blocked-request and HTTPS-upgrade
  counters were plain `Counter`/`dict` objects written from Chromium's IO
  thread while the UI thread summed and sorted them. A dict resized mid-read
  raises, and an unhandled exception inside a Qt slot aborts the process — so
  the status bar and Site Trust Center could kill the browser precisely when
  the shield was busiest. All tallies now live behind a lock and every
  accessor returns a private copy.
- **Permission requests fail closed.** The Qt 6.8+ permission handler wrapped
  its whole body in a silent `except: pass`, leaving `getUserMedia` and
  geolocation promises unsettled forever with no feedback when anything went
  wrong. Failures now deny the request and report why. The handler also reads
  the authoritative private flag from the page itself rather than
  reconstructing it from a dynamic property, and an unclassifiable page is
  treated as private — so a private-tab grant can no longer reach
  `settings.json`.

### Startup and engineering

- **Cold start is roughly a third of what it was.** `openai`, `gtts`,
  `speech_recognition`, `requests` and `cryptography` are now loaded on first
  use instead of at import. Measured on the development machine, `import main`
  fell from 1.96 s to 0.60 s; `openai` alone accounted for 1.05 s of the old
  figure and is only ever reached from a background thread. A regression test
  asserts none of them load at startup, and a second test asserts the frozen
  build declares a matching `--hidden-import` for each.
- **CI is a real gate.** A new `pyproject.toml` makes `octobrowse/`
  pip-installable and configures ruff, coverage and mypy. The Quality workflow
  now installs `requirements.txt` (so its pip cache is honest), runs ruff, runs
  the suite under coverage with a 35% total floor and an 85% floor for
  `octobrowse/`, and adds a Windows job that runs the tests, exercises the
  `--smoke-test` flag the release verifier depends on, and lints the packaging
  scripts. A concurrency group stops every PR branch building twice.
- **Versions can no longer drift.** `packaging/build_installer.ps1` read a
  hardcoded default version, so a forgotten bump produced an installer named
  after the previous release; it now reads `octobrowse.version` like its
  siblings. The version test cross-checks every copy against that single source
  instead of against a literal.

## Test suite

174 tests, all passing offline and headless:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests
```

Coverage is 89% for `octobrowse/`. New suites cover the summarizer
(determinism, verbatim offsets, redundancy suppression, CJK and abbreviation
segmentation, bounded runtime), the public-suffix engine (wildcards, exception
rules, IP literals, unknown-TLD fallback), the thread-safe counters (concurrent
readers and writers under contention), deferred imports, and the permission
fail-closed paths.

## Compatibility and safety note

Native extension execution remains disabled; the non-executing package
inspector is unchanged. Python plugins remain trusted local automation, off by
default behind Developer Mode.

The public-suffix subset is a snapshot, not a mirror of publicsuffix.org, and
it is not updated over the network. On-device summaries are extractive: they
select sentences, they do not paraphrase or reason.

## For source users

OctoBrowse 3.5 requires Python 3.10+ and PyQt6/PyQt6-WebEngine 6.8 or newer.
Install dependencies from `requirements.txt`, then run:

```powershell
python main.py
```

The release artifacts are unsigned unless a code-signing certificate is added
to the local packaging process.

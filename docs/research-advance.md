# Research and browser refinements

Included in OctoBrowse 3.7; researched 5 September 2026. Existing 3.6 release
binaries do not include these changes.

## Revisit saved evidence

Select text and press **Ctrl+Alt+N**, or choose **Save as Note** from an on-device
summary. Quote anchors now survive the note's save/load/edit cycle. Open the
source in a standard tab and choose **Data > Check Saved Quotes**, search for
that action in **Ctrl+K**, or use **Check Quotes** inside a saved note.

The report checks full quotations against the loaded page and includes current
context. Its outcomes mean:

| Outcome | Meaning |
| --- | --- |
| Exact | The complete quote occurs verbatim. |
| Normalized | The complete quote occurs with whitespace changes only. |
| Ambiguous | Multiple occurrences remain; saved context cannot identify one. |
| Missing | The complete quote is absent from the extracted text. |
| Empty | No quotation was available to check. |

Checks use up to 120,000 readable characters, 8,000 characters per quotation,
12 stored anchors per note, and 100 quotes per report. Batch checks prepare the
document once. A missing quote can reflect changed text, unloaded content, or
extraction limits. Results remain in the dialog unless explicitly copied.
They do not establish truth, authenticate the publisher, prove model citation
faithfulness, or replace an archived snapshot.

Source matching preserves scheme, path, query, and credentials. Only hostname
case, default HTTP(S) ports, fragments, and the equivalent empty/root HTTP path
are normalized. A changed URL, reload, closed tab, or tab switch cancels pending
delivery. Saved research checks reject private tabs. A private on-device
summary can check its own source locally, but cannot persist a note.

Older selection notes work without an anchor. Older summary notes that did not
save their quoted sentences cannot retroactively recover those sentences.
On-device summaries now expose **Check Quote** instead of the old shortened
Find-in-Page action, which could search another tab or match only a quote's
opening words. Unicode cursor positions are translated from Qt's UTF-16 units.

## Filter compatibility and reliability

Network rules support included/excluded `$domain=` scopes, constrained by
resource types and request-party options. Qt's request initiator supplies the
document origin when available; top-level first-party URL is the fallback for
an empty initiator and still owns block telemetry. Opaque initiators do not
inherit a positive domain permission.

Cosmetic rules support included and excluded domains, plus exact-selector
`#@#` exceptions. More-specific domains take precedence. Unsupported or malformed
constraints are skipped instead of becoming unconditional rules. CSS is
deduplicated and cached for at most 128 hosts. Subscription updates invalidate
that cache and refresh loaded tabs in Qt's isolated Application World; newly
excepted pages and disabled blocking remove the old injected style.

Workspace recovery now handles nulls, malformed string fields, non-boolean
pins, nonfinite/out-of-range timestamps, invalid Unicode, and colliding IDs.
Dropping invalid tab records preserves the intended active position. Markdown
exports escape HTML and do not turn executable URL schemes into links.

Clearing history and deleting notes immediately rebuilds the library index so
removed items no longer appear in search. This is logical removal from the
application, not a claim of forensic erasure from storage or backups.

## Research decisions

- [W3C Web Annotation Data Model, Text Quote Selector](https://www.w3.org/TR/annotation-model/#text-quote-selector)
  supplies the exact/prefix/suffix model. The new checker requires complete
  context to resolve duplicates and never treats a stale offset as evidence.
- [Correctness is not Faithfulness in RAG Attributions](https://arxiv.org/abs/2412.18004)
  distinguishes whether sources support statements from whether the model
  actually relied on those sources. This supports the deliberately narrow
  text-presence wording and explicit access to the source quotation.
- [Understanding before verifying: Claim normalization for automated citation verification](https://arxiv.org/abs/2608.30145)
  is a recent preprint submitted 31 August 2026. It separates claim normalization,
  grounded evidence retrieval, and citation classification. The implementation
  decision here is to make evidence inspection reliable first; this browser
  does not implement CNCV or inherit its reported results.
- [Adblock Plus filter documentation](https://help.adblockplus.org/adblock-plus-help-center/how-to-write-filters)
  and [the official core's domain matching implementation](https://gitlab.com/eyeo/adblockplus/adblockpluscore/-/raw/master/lib/filterClasses.js)
  define network domain scopes, cosmetic exceptions, and domain precedence.
- [Qt request information](https://doc.qt.io/qt-6/qwebengineurlrequestinfo.html#initiator)
  provides the origin of the initiating document, allowing frame-aware domain
  filters while retaining top-level telemetry.

The papers guide product boundaries and workflow design; this work makes no
model-training, benchmark-reproduction, or factual-verification claims.

## Validation

On this Windows checkout, 300 regression tests pass and the pure helper package
has 93% statement coverage (85% required). Ruff, compilation, and whitespace
checks pass. The actual Qt Quote Check dialog is also exercised by the unit
suite. A local stress sample of 100 repeated-quote checks against 120,000
characters completed in 0.37 seconds; this is one machine's observation, not a
cross-platform benchmark.

The full WebEngine smoke could not complete here: Qt failed to create graphics
contexts and the initial dashboard remained unloaded with an empty URL. The
new live CSS and page-extraction assertions are present but were not reached.
Full rendering validation remains separate from frozen startup checks; consult
the release manifest for the packaged startup results. Release smoke tests now
use isolated settings, profiles, and credentials, with ambient API keys ignored.

The automated suites cover malformed persistence, full-quote tail mutations,
duplicate and whitespace matches, source and profile boundaries, stale
callbacks, anchor roundtrips, frame-domain filters, cosmetic exceptions and
cache invalidation, and index removal on history/note deletion. The live Qt
smoke exercises actual page extraction, persisted summary anchors, the quote
report, and CSS visibility before and after exceptions and blocking changes.

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests
python -m compileall -q main.py alpha.py octobrowse tests
ruff check .
python tests/live_ui_smoke.py
```

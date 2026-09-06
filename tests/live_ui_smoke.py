"""Manual offscreen-friendly smoke checks for the real Qt browser window."""

from __future__ import annotations

import sys
import faulthandler
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QStandardPaths, QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import OCTO_BROWSER_NAME, OCTO_BROWSER_VERSION, OctoBrowse, SettingsStore
from octobrowse.evidence import capture_quote_anchor
from octobrowse.filtering import FilterRuleSet
from octobrowse.readability import MAX_READABLE_CHARS, ReadablePage
from octobrowse.snapshots import manifest_path_for_archive, verify_snapshot_bundle


def main() -> int:
    faulthandler.dump_traceback_later(45)
    QStandardPaths.setTestModeEnabled(True)
    app = QApplication(sys.argv)
    app.setApplicationName(OCTO_BROWSER_NAME)
    app.setApplicationDisplayName(OCTO_BROWSER_NAME)
    app.setApplicationVersion(OCTO_BROWSER_VERSION)
    app.setOrganizationName("OctoBrowse")
    # A live test must not restore earlier test tabs, use the real credential
    # vault, or issue optional API requests using the user's saved keys.
    test_state = tempfile.TemporaryDirectory(prefix="octobrowse-live-", ignore_cleanup_errors=True)
    store = SettingsStore.__new__(SettingsStore)
    store.directory = Path(test_state.name)
    store.path = store.directory / "settings.json"
    store.legacy_path = store.directory / "legacy.json"
    store.credentials = SimpleNamespace(get=lambda _name: "", set=lambda _name, _value: True)
    with patch("main.SettingsStore", return_value=store):
        browser = OctoBrowse()
    try:
        return _run_checks(app, browser)
    finally:
        # Failed assertions must also stop WebEngine and workers before Python
        # tears down Qt, otherwise a failed smoke can leave a process running.
        browser.close()
        app.processEvents()
        test_state.cleanup()
        faulthandler.cancel_dump_traceback_later()


def _run_checks(app: QApplication, browser: OctoBrowse) -> int:
    print("Live smoke: window created", flush=True)
    state: dict[str, str] = {}

    def inspect_sample() -> None:
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QDialog):
            state["error"] = "Extension inspector did not become modal."
            return
        sample_button = next(
            (
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "Inspect Sample"
            ),
            None,
        )
        output = dialog.findChild(QPlainTextEdit)
        if sample_button is None or output is None:
            state["error"] = "Extension inspector controls are incomplete."
        else:
            sample_button.click()
            state["report"] = output.toPlainText()
        dialog.accept()

    QTimer.singleShot(100, inspect_sample)
    browser.open_extension_inspector()

    report = state.get("report", "")
    print("Live smoke: extension inspector complete", flush=True)
    expected = (
        "Permission review for OctoBrowse MV3 Hello 1.0.0",
        "Site access: none declared.",
        "did not install, extract, load, enable, or execute",
    )
    if state.get("error") or any(text not in report for text in expected):
        raise AssertionError(state.get("error") or f"Unexpected inspector report: {report}")
    if browser.profile.isOffTheRecord():
        raise AssertionError("Standard profile unexpectedly runs off the record.")
    if not browser.profile_for_tab(True).isOffTheRecord():
        raise AssertionError("Private profile unexpectedly persists data.")
    browser.open_dashboard()
    dashboard = browser.current_browser()
    if dashboard is None or not dashboard.property("generated_page"):
        raise AssertionError("Generated dashboard is missing its trust marker.")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if (
            not dashboard.property("loading")
            and not dashboard.property("generated_navigation_pending")
            and dashboard.url().host() == "octobrowse.local"
        ):
            break
        time.sleep(0.01)
    internal_url = QUrl("https://octobrowse.local/")
    if browser.security_badge.text() != "Octo":
        raise AssertionError(
            "Generated dashboard did not retain app identity after its real load: "
            f"url={dashboard.url().toString()}, generated={dashboard.property('generated_page')}, "
            f"loading={dashboard.property('loading')}, pending={dashboard.property('generated_navigation_pending')}, "
            f"load_ok={dashboard.property('load_ok')}, badge={browser.security_badge.text()}"
        )
    dashboard.setProperty("generated_page", False)
    browser.update_security_badge(internal_url, dashboard)
    if browser.security_badge.text() == "Octo":
        raise AssertionError("A URL without the generated-page marker was trusted.")
    dashboard.setProperty("generated_page", True)

    second_tab = browser.add_tab(QUrl("about:blank"), "Lifecycle Smoke", private=False)
    if float(dashboard.property("background_since") or 0) <= 0:
        raise AssertionError("Outgoing tab did not begin background-idle timing.")
    browser.tabs.setCurrentWidget(dashboard)
    if float(dashboard.property("background_since") or 0) != 0:
        raise AssertionError("Active tab retained a background-idle timestamp.")
    if float(second_tab.property("background_since") or 0) <= 0:
        raise AssertionError("Second tab did not begin background-idle timing.")

    original_note_ids = {
        str(note.get("id", "")) for note in browser.notes
    }
    print("Live smoke: dashboard and lifecycle complete", flush=True)
    note = browser.save_research_note(
        url="https://example.test/research",
        title="Live smoke research",
        quote="The quotation is searchable.",
        body="Lifecycle evidence belongs with its source.",
        kind="selection",
        source_private=False,
    )
    if note is None:
        raise AssertionError("Standard research note was not saved.")
    browser.rebuild_library_index()
    note_results = browser.library_index.search("quotation searchable")
    if not note_results or note_results[0].kind != "Note":
        raise AssertionError("Research quotation was not indexed in Library Search.")
    if browser.research_source_is_persistable(
        "https://private.example/",
        source_private=True,
        show_message=False,
    ):
        raise AssertionError("Private research source was accepted for persistence.")

    article_tab = browser.add_tab(
        QUrl("about:blank"),
        "Readable Article Smoke",
        private=False,
    )
    article_tab.setHtml(
        """<!doctype html>
<html lang="en">
<head>
  <title>Fallback document title</title>
  <meta property="og:site_name" content="Octo Test Journal">
  <script>
    window.getComputedStyle = () => ({display: "none", visibility: "hidden"});
  </script>
</head>
<body class="menu-open sidebar-layout">
  <header><nav>Site navigation should not become research evidence.</nav></header>
  <div class="cookie-banner">Cookie preferences should be excluded.</div>
  <main>
    <article>
      <h1>Semantic extraction wins</h1>
      <p>The distinctive article evidence explains how bounded extraction
      keeps meaningful paragraphs while removing surrounding browser-page
      furniture from downstream reading and research tools.</p>
      <p>A second substantial paragraph gives the semantic article enough
      evidence density to outrank menus, advertisements, and related links.</p>
      <p style="display:none">HIDDEN EXTRACTION DECOY</p>
      <div style="opacity: 0"><p>TRANSPARENT ANCESTOR DECOY</p></div>
      <div aria-hidden="TRUE"><p>ARIA HIDDEN DECOY</p></div>
      <section class="related"><p>RELATED CONTENT DECOY</p></section>
      <footer><span rel="author">By Test Researcher</span></footer>
    </article>
    <aside>Sponsored related links should be excluded.</aside>
  </main>
  <footer>Footer boilerplate should be excluded.</footer>
</body>
</html>""",
        QUrl("https://example.test/readable"),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if (
            not article_tab.property("loading")
            and article_tab.url().host() == "example.test"
        ):
            break
        time.sleep(0.01)
    readable_state: dict[str, object] = {}
    browser.extract_readable_page(
        article_tab,
        lambda readable: readable_state.setdefault("page", readable),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and "page" not in readable_state:
        app.processEvents()
        time.sleep(0.01)
    readable = readable_state.get("page")
    if readable is None:
        raise AssertionError("Readable-page extraction did not return.")
    if readable.title != "Semantic extraction wins":
        raise AssertionError("Readable-page extraction missed the article title.")
    if "distinctive article evidence" not in readable.text:
        raise AssertionError("Readable-page extraction missed article evidence.")
    for noise in (
        "Site navigation",
        "Cookie preferences",
        "Sponsored related links",
        "Footer boilerplate",
        "HIDDEN EXTRACTION DECOY",
        "TRANSPARENT ANCESTOR DECOY",
        "ARIA HIDDEN DECOY",
        "RELATED CONTENT DECOY",
    ):
        if noise in readable.text:
            raise AssertionError(f"Readable-page extraction retained noise: {noise}")
    if readable.byline != "By Test Researcher":
        raise AssertionError("Article-footer byline metadata was filtered out.")
    if readable.method != "semantic:article":
        raise AssertionError(
            f"Readable-page extraction chose an unexpected root: {readable.method}"
        )
    print("Live smoke: article extraction complete", flush=True)

    quote = "distinctive article evidence"
    anchor = capture_quote_anchor(readable.text, quote)
    if anchor is None:
        raise AssertionError("Evidence capture did not produce a full quote anchor.")

    def save_summary_note() -> None:
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QDialog):
            state["error"] = "Summary dialog did not open."
            return
        for button in dialog.findChildren(QPushButton):
            if button.text() == "Save as Note":
                button.click()
                return
        state["error"] = "Summary save button is missing."
        dialog.reject()

    QTimer.singleShot(100, save_summary_note)
    browser.show_ai_summary(
        f"Saved evidence: {quote}", readable.url, "Anchored smoke summary",
        note_kind="local-summary", anchors=[anchor],
    )
    print("Live smoke: summary note saved", flush=True)
    if state.get("error"):
        raise AssertionError(state["error"])
    stored_summary = next(note for note in browser.store.load()[3] if note["title"] == "Anchored smoke summary")
    if stored_summary.get("anchors") != [anchor.to_dict()]:
        raise AssertionError("Saving a summary dropped its quote anchors on disk.")
    browser.save_research_note(
        url=readable.url, title="Missing quote smoke", quote="This quotation was removed from the article.",
    )
    report_state: dict[str, str] = {}
    report_deadline = time.monotonic() + 10

    def inspect_quote_report() -> None:
        dialog = app.activeModalWidget()
        if isinstance(dialog, QDialog) and dialog.windowTitle() == "Quote Check":
            output = dialog.findChild(QPlainTextEdit)
            report_state["text"] = output.toPlainText() if output else ""
            capture_path = Path(__file__).resolve().parents[1] / "build" / "qa" / "quote-check.png"
            capture_path.parent.mkdir(parents=True, exist_ok=True)
            dialog.grab().save(str(capture_path))
            dialog.accept()
        elif time.monotonic() < report_deadline:
            QTimer.singleShot(20, inspect_quote_report)

    QTimer.singleShot(20, inspect_quote_report)
    browser.check_saved_quotes()
    while time.monotonic() < report_deadline and "text" not in report_state:
        app.processEvents()
        time.sleep(0.01)
    report_text = report_state.get("text", "")
    print("Live smoke: quote report complete", flush=True)
    if not all(expected in report_text for expected in ("EXACT", "MISSING", readable.url, "Text presence only")):
        raise AssertionError(f"Quote report did not display correct outcomes: {report_text}")

    # Check real rendered CSS, including restoring visibility after exceptions
    # arrive and after the blocker is disabled on an already-loaded document.
    def cosmetic_display() -> str:
        result: dict[str, str] = {}
        article_tab.page().runJavaScript(
            "getComputedStyle(document.querySelector('h1')).display",
            1,  # Isolated world avoids the page's deliberate getComputedStyle override.
            lambda value: result.setdefault("display", str(value)),
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "display" not in result:
            app.processEvents()
            time.sleep(0.01)
        return result.get("display", "")

    old_rules = browser.request_interceptor.filter_rules
    old_enabled = browser.ad_block_enabled
    rules = FilterRuleSet()
    rules.parse_text("~other.test##h1")
    browser.ad_block_enabled = True
    browser.handle_filter_rules_parsed(rules)
    if cosmetic_display() != "none":
        raise AssertionError("Negated-domain cosmetic rule did not hide its target.")
    rules.parse_text("example.test#@#h1")
    browser.handle_filter_rules_parsed(rules)
    if cosmetic_display() != "block":
        raise AssertionError("New cosmetic exception left stale injected CSS behind.")
    rules = FilterRuleSet()
    rules.parse_text("##h1")
    browser.handle_filter_rules_parsed(rules)
    if cosmetic_display() != "none":
        raise AssertionError("Generic cosmetic rule did not hide its target.")
    browser.ad_block_enabled = False
    browser.refresh_cosmetic_filters()
    if cosmetic_display() != "block":
        raise AssertionError("Disabling cosmetic blocking left stale injected CSS.")
    browser.ad_block_enabled = old_enabled
    browser.request_interceptor.filter_rules = old_rules
    if browser.private_request_interceptor is not None:
        browser.private_request_interceptor.filter_rules = old_rules
    browser.refresh_cosmetic_filters()
    browser.close_tab(browser.tabs.indexOf(article_tab))
    browser.tabs.setCurrentWidget(dashboard)

    browser.show_reader_tab(
        ReadablePage(
            text="'" * MAX_READABLE_CHARS,
            title="Encoded reader limit smoke",
            url="https://example.test/encoded-reader",
        ),
        private=False,
    )
    bounded_reader_tab = browser.current_browser()
    if bounded_reader_tab is None:
        raise AssertionError("Bounded Reader View did not open.")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if not bounded_reader_tab.property("loading"):
            break
        time.sleep(0.01)
    if not bounded_reader_tab.property("load_ok"):
        raise AssertionError("Bounded Reader View exceeded Qt's setHtml limit.")
    bounded_reader_state: dict[str, str] = {}
    bounded_reader_tab.page().toPlainText(
        lambda text: bounded_reader_state.setdefault("text", text)
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and "text" not in bounded_reader_state:
        app.processEvents()
        time.sleep(0.01)
    if "display safely shortened" not in bounded_reader_state.get("text", ""):
        raise AssertionError("Reader View did not enforce its encoded HTML budget.")
    browser.close_tab(browser.tabs.indexOf(bounded_reader_tab))
    browser.tabs.setCurrentWidget(dashboard)

    private_snapshot_tab = browser.add_tab(
        QUrl("about:blank"),
        "Private Snapshot Smoke",
        private=True,
    )
    private_snapshot_tab.setHtml(
        """<!doctype html>
<html>
<head><title>Private capture sentinel</title></head>
<body><main><h1>Private capture sentinel</h1></main></body>
</html>""",
        QUrl("https://private.example/snapshot-smoke"),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if (
            not private_snapshot_tab.property("loading")
            and private_snapshot_tab.url().host() == "private.example"
        ):
            break
        time.sleep(0.01)
    original_downloads_history = list(browser.downloads_history)
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "live-dashboard.mhtml"
        private_archive = Path(temp) / "live-private.mhtml"
        browser.start_offline_snapshot(dashboard, str(archive))
        browser.start_offline_snapshot(private_snapshot_tab, str(private_archive))
        manifest = manifest_path_for_archive(archive)
        private_manifest = manifest_path_for_archive(private_archive)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if (
                manifest.exists()
                and private_manifest.exists()
                and not browser.snapshot_workers
                and not browser.pending_snapshot_saves
                and not browser.snapshot_targets_in_progress
            ):
                break
            time.sleep(0.01)
        if (
            browser.snapshot_workers
            or browser.pending_snapshot_saves
            or browser.snapshot_targets_in_progress
            or dashboard.page().property("pending_snapshot_token")
            or private_snapshot_tab.page().property("pending_snapshot_token")
        ):
            raise AssertionError(
                "Concurrent snapshots left workers, tokens, or target locks behind."
            )
        verification = verify_snapshot_bundle(archive)
        private_verification = verify_snapshot_bundle(private_archive)
        if not verification.valid:
            raise AssertionError(
                f"Live MHTML snapshot did not verify: {verification.reason}"
            )
        if not private_verification.valid:
            raise AssertionError(
                "Live private MHTML snapshot did not verify: "
                f"{private_verification.reason}"
            )
        public_source = (verification.manifest or {}).get("source", {})
        private_source = (private_verification.manifest or {}).get("source", {})
        if public_source.get("private_capture") is not False:
            raise AssertionError("Standard snapshot received private provenance.")
        if private_source.get("private_capture") is not True:
            raise AssertionError("Private snapshot lost its private provenance.")
        if public_source.get("url") != dashboard.url().toString():
            raise AssertionError("Standard snapshot source URL was cross-wired.")
        if (
            private_source.get("url")
            != private_snapshot_tab.url().toString()
            or private_source.get("title") != "Private capture sentinel"
        ):
            raise AssertionError("Private snapshot source metadata was cross-wired.")
        saved_history_paths = {
            str(record.get("file", ""))
            for record in browser.downloads_history[
                len(original_downloads_history) :
            ]
        }
        if str(archive) not in saved_history_paths:
            raise AssertionError("Standard snapshot was not recorded in download history.")
        if str(private_archive) in saved_history_paths:
            raise AssertionError("Private snapshot leaked into download history.")

    browser.downloads_history = original_downloads_history
    browser.close_tab(browser.tabs.indexOf(private_snapshot_tab))
    browser.notes = [
        item
        for item in browser.notes
        if str(item.get("id", "")) in original_note_ids
    ]
    browser.refresh_notes_sidebar()
    browser.save_settings()

    print(
        "Live profile, internal trust, tab lifecycle, bounded article/Reader "
        "extraction, quote persistence/checking, live cosmetic exceptions, research index, "
        "concurrent profile-safe snapshots, and "
        "MV3 inspector smoke passed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Manual offscreen-friendly smoke checks for the real Qt browser window."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import OCTO_BROWSER_NAME, OCTO_BROWSER_VERSION, OctoBrowse
from octobrowse.snapshots import manifest_path_for_archive, verify_snapshot_bundle


def main() -> int:
    QStandardPaths.setTestModeEnabled(True)
    app = QApplication(sys.argv)
    app.setApplicationName(OCTO_BROWSER_NAME)
    app.setApplicationDisplayName(OCTO_BROWSER_NAME)
    app.setApplicationVersion(OCTO_BROWSER_VERSION)
    app.setOrganizationName("OctoBrowse")
    browser = OctoBrowse()
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
    internal_url = QUrl("https://octobrowse.local/")
    if browser.security_badge.text() != "Octo":
        raise AssertionError(
            "Generated dashboard did not retain app identity after its real load."
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
<body>
  <header><nav>Site navigation should not become research evidence.</nav></header>
  <div class="cookie-banner">Cookie preferences should be excluded.</div>
  <main>
    <article>
      <h1>Semantic extraction wins</h1>
      <p class="byline">By Test Researcher</p>
      <p>The distinctive article evidence explains how bounded extraction
      keeps meaningful paragraphs while removing surrounding browser-page
      furniture from downstream reading and research tools.</p>
      <p>A second substantial paragraph gives the semantic article enough
      evidence density to outrank menus, advertisements, and related links.</p>
      <p style="display:none">HIDDEN EXTRACTION DECOY</p>
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
    ):
        if noise in readable.text:
            raise AssertionError(f"Readable-page extraction retained noise: {noise}")
    if readable.method != "semantic:article":
        raise AssertionError(
            f"Readable-page extraction chose an unexpected root: {readable.method}"
        )
    browser.close_tab(browser.tabs.indexOf(article_tab))
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

    browser.close()
    app.processEvents()
    print(
        "Live profile, internal trust, tab lifecycle, article extraction, "
        "research index, concurrent profile-safe snapshots, and MV3 inspector "
        "smoke passed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

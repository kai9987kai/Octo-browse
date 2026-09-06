"""Browser integration tests for evidence source binding and persistence."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow, QPlainTextEdit

from main import OctoBrowse, OctoRequestInterceptor, QMessageBox
from octobrowse.filtering import FilterRuleSet
from octobrowse.library_index import LibraryIndex
from octobrowse.quote_anchor import QuoteAnchor
from octobrowse.research import make_research_note
from octobrowse.readability import ReadablePage


SOURCE = "https://example.test/paper"


class FakeView:
    def __init__(self, url: str = SOURCE, private: bool = False) -> None:
        self.source = url
        self.properties = {"private": private, "loading": False, "document_generation": 1}
        self.webpage = Mock()
        self.webpage.title.return_value = "Paper"

    def url(self) -> QUrl:
        return QUrl(self.source)

    def property(self, key: str) -> object:
        return self.properties.get(key)

    def page(self) -> Mock:
        return self.webpage


class ResearchWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.browser = OctoBrowse.__new__(OctoBrowse)
        self.view = FakeView()
        self.browser.current_browser = Mock(return_value=self.view)
        self.browser.set_status = Mock()
        self.browser.show_quote_check_report = Mock()
        self.browser.tabs = SimpleNamespace(indexOf=lambda _view: 0, tabText=lambda _index: "Paper")
        self.browser.notes = [make_research_note(SOURCE, "Paper", "Saved quote.", "")]

    def deliver(self, text: str = "Saved quote.") -> None:
        callback = self.view.webpage.runJavaScript.call_args.args[2]
        callback({"text": text, "title": "Paper", "url": "https://evil.test/"})

    def test_saved_quotes_use_complete_text_and_trusted_source(self) -> None:
        self.browser.check_saved_quotes()
        self.deliver()
        page, items = self.browser.show_quote_check_report.call_args.args
        self.assertEqual(page.url, SOURCE)
        self.assertEqual(items, [("Paper", "Saved quote.", None)])

    def test_other_sources_and_private_profiles_are_not_checked(self) -> None:
        with patch.object(QMessageBox, "information"):
            self.view.source = "https://example.test/paper?other-version"
            self.browser.check_saved_quotes()
            self.view.source = SOURCE
            self.view.properties["private"] = True
            self.browser.check_saved_quotes()
        self.view.webpage.runJavaScript.assert_not_called()

    def test_navigation_reload_closed_tab_and_tab_switch_cancel_results(self) -> None:
        for event in ("url", "generation", "closed", "switch"):
            with self.subTest(event=event):
                self.setUp()
                self.browser.check_saved_quotes()
                if event == "url":
                    self.view.source = "https://example.test/changed"
                elif event == "generation":
                    self.view.properties["document_generation"] = 2
                elif event == "closed":
                    self.browser.tabs.indexOf = lambda _view: -1
                else:
                    self.browser.current_browser.return_value = FakeView()
                self.deliver()
                self.browser.show_quote_check_report.assert_not_called()

    def test_loading_page_is_not_checked(self) -> None:
        self.view.properties["loading"] = True
        self.browser.check_saved_quotes()
        self.browser.locate_quote_in_page(QuoteAnchor("Saved quote."), SOURCE)
        self.view.webpage.runJavaScript.assert_not_called()

    def test_summary_check_cannot_cross_profiles_or_sources(self) -> None:
        anchor = QuoteAnchor("Saved quote.")
        self.browser.locate_quote_in_page(anchor, "https://other.test/")
        self.browser.locate_quote_in_page(anchor, SOURCE, source_private=True)
        self.view.webpage.runJavaScript.assert_not_called()
        self.browser.locate_quote_in_page(anchor, SOURCE)
        self.deliver()
        self.browser.show_quote_check_report.assert_called_once()

    def test_saved_summary_anchors_route_as_individual_quotes(self) -> None:
        self.browser.notes = [make_research_note(
            SOURCE, "Summary", "", "First quote.\nSecond quote.",
            anchors=[QuoteAnchor("First quote.").to_dict(), QuoteAnchor("Second quote.").to_dict()],
        )]
        self.browser.check_saved_quotes()
        self.deliver("First quote. Second quote.")
        items = self.browser.show_quote_check_report.call_args.args[1]
        self.assertEqual([item[1] for item in items], ["First quote.", "Second quote."])

    def test_whitespace_normalized_note_retains_anchor_context(self) -> None:
        anchor = QuoteAnchor("Saved  quote.", "Before ", " after").to_dict()
        self.browser.notes = [make_research_note(SOURCE, "Paper", "Saved quote.", "", anchors=[anchor])]
        self.browser.check_saved_quotes()
        self.deliver("Before Saved quote. after Other Saved quote. context")
        items = self.browser.show_quote_check_report.call_args.args[1]
        self.assertEqual(items[0][2].prefix, "Before ")

    def test_long_summary_bullet_is_not_shortened_before_check(self) -> None:
        self.browser.show_ai_summary = Mock()
        text = "A long evidence sentence " + "meaningful words " * 40 + "finishes here."
        self.browser.summarize_page_offline()
        self.deliver(text)
        anchors = self.browser.show_ai_summary.call_args.kwargs["anchors"]
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].exact, text)

    def test_deleted_notes_disappear_from_library_immediately(self) -> None:
        browser = self.browser
        browser.library_index = LibraryIndex()
        self.addCleanup(browser.library_index.close)
        browser.refresh_notes_sidebar = Mock()
        browser.save_settings = Mock()
        browser.library_entries = lambda: [
            {"kind": "Note", "title": note["title"], "snippet": note["quote"]} for note in browser.notes
        ]
        browser.rebuild_library_index()
        self.assertTrue(browser.library_index.search("Saved quote"))
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(browser.delete_research_note(browser.notes[0]["id"]))
        self.assertFalse(browser.library_index.search("Saved quote"))

    def test_cleared_history_disappears_from_library_immediately(self) -> None:
        browser = self.browser
        browser.library_index = LibraryIndex()
        self.addCleanup(browser.library_index.close)
        browser.history = [{"url": SOURCE, "title": "Historical sentinel"}]
        browser._history_index = {SOURCE: browser.history[0]}
        browser._history_items = {SOURCE: object()}
        browser.history_sidebar = Mock()
        browser.history_db = Mock()
        browser.refresh_address_suggestions = Mock()
        browser.library_entries = lambda: [{"kind": "History", **entry} for entry in browser.history]
        browser.rebuild_library_index()
        self.assertTrue(browser.library_index.search("Historical sentinel"))
        with patch.object(QMessageBox, "information"):
            browser.clear_history()
        self.assertFalse(browser.library_index.search("Historical sentinel"))
        browser.history_db.clear.assert_called_once()


class FrameFilterIntegrationTests(unittest.TestCase):
    def test_frame_scopes_do_not_use_top_level_host(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||tracker.test^$domain=frame.test")
        interceptor = OctoRequestInterceptor(set())
        interceptor.ad_block_enabled = True
        interceptor.filter_rules = rules
        for initiator, blocked in (("https://frame.test/", True), ("https://other.test/", False), ("null", False)):
            with self.subTest(initiator=initiator):
                info = Mock()
                info.requestUrl.return_value = QUrl("https://tracker.test/script.js")
                info.firstPartyUrl.return_value = QUrl("https://top.test/")
                info.initiator.return_value = QUrl(initiator)
                info.resourceType.return_value = "script"
                interceptor.interceptRequest(info)
                self.assertEqual(info.block.called, blocked)


class QuoteDialogTests(unittest.TestCase):
    def test_actual_qt_report_shows_distinct_outcomes_and_source(self) -> None:
        app = QApplication.instance() or QApplication([])
        window = QMainWindow()
        captured: dict[str, str] = {}

        def inspect() -> None:
            dialog = app.activeModalWidget()
            if isinstance(dialog, QDialog):
                output = dialog.findChild(QPlainTextEdit)
                captured["text"] = output.toPlainText() if output else ""
                dialog.accept()

        QTimer.singleShot(20, inspect)
        OctoBrowse.show_quote_check_report(
            window, ReadablePage(text="Exact quote. Wrapped\nquote. Repeat. Repeat.", title="Evidence", url=SOURCE),
            [("Exact", "Exact quote.", None), ("Wrapped", "Wrapped quote.", None),
             ("Repeated", "Repeat.", None), ("Absent", "Removed quote.", None)],
        )
        window.deleteLater()
        text = captured.get("text", "")
        for expected in ("EXACT", "NORMALIZED", "AMBIGUOUS", "MISSING", SOURCE, "Text presence only"):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()

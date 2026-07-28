"""Manual offscreen-friendly smoke checks for the real Qt browser window."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import OCTO_BROWSER_NAME, OCTO_BROWSER_VERSION, OctoBrowse


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
    internal_url = QUrl("https://octobrowse.local/")
    browser.update_security_badge(internal_url, dashboard)
    if browser.security_badge.text() != "Octo":
        raise AssertionError("Generated dashboard did not receive app identity.")
    dashboard.setProperty("generated_page", False)
    browser.update_security_badge(internal_url, dashboard)
    if browser.security_badge.text() == "Octo":
        raise AssertionError("A URL without the generated-page marker was trusted.")

    browser.close()
    app.processEvents()
    print("Live profile isolation and MV3 inspector smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

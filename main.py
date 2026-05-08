#!/usr/bin/env python3
"""
OctoBrowse: a PyQt6/QtWebEngine desktop browser prototype.

The app keeps the original browsing, sidebar, AI, speech, page-tool, bookmark,
history, weather, news, and extension-lab features while consolidating the
experimental alpha improvements into one maintained entry point.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import html
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

try:
    import cv2
except ImportError:  # pragma: no cover - optional runtime feature
    cv2 = None

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime feature
    requests = None

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - optional runtime feature
    Fernet = None

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover - optional runtime feature
    gTTS = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional runtime feature
    OpenAI = None

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover - optional runtime feature
    sr = None

from PyQt6.QtCore import QSize, QStandardPaths, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QCalendarWidget,
)


AD_BLOCK_LIST = {
    "2mdn.net",
    "ad.doubleclick.net",
    "adform.net",
    "adnxs.com",
    "adservice.google.com",
    "adzerk.net",
    "ads.facebook.com",
    "ads.linkedin.com",
    "ads.pubmatic.com",
    "ads.twitter.com",
    "ads.youtube.com",
    "adsrvr.org",
    "advertising.com",
    "amazon-adsystem.com",
    "criteo.com",
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "openx.net",
    "outbrain.com",
    "pubmatic.com",
    "rubiconproject.com",
    "scorecardresearch.com",
    "taboola.com",
}

DEFAULT_HOMEPAGE = "https://www.google.com"
DEFAULT_OPENAI_MODEL = os.environ.get("OCTOBROWSE_OPENAI_MODEL", "gpt-5-mini")
OCTO_BROWSER_NAME = "Octo Browser"
OCTO_BROWSER_VERSION = "3.0"
OCTO_BROWSER_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) OctoBrowser/{OCTO_BROWSER_VERSION} "
    f"Chrome/126.0.0.0 Safari/537.36"
)
MAX_HISTORY_ITEMS = 500


@dataclass
class BrowserSettings:
    homepage: str = DEFAULT_HOMEPAGE
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_model: str = DEFAULT_OPENAI_MODEL
    weather_location: str = "London"
    weather_api_key: str = field(default_factory=lambda: os.environ.get("OPENWEATHER_API_KEY", ""))
    news_api_key: str = field(default_factory=lambda: os.environ.get("NEWS_API_KEY", ""))
    theme: str = "default"
    custom_theme: str | None = None
    ad_block_enabled: bool = False
    user_agent: str = OCTO_BROWSER_USER_AGENT


@dataclass
class BrowserCommand:
    label: str
    hint: str
    handler: Any


class SettingsStore:
    """JSON settings store with migration from the original cwd file."""

    def __init__(self) -> None:
        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if app_data:
            self.directory = Path(app_data)
        else:
            self.directory = Path.home() / ".octobrowse"
        self.path = self.directory / "settings.json"
        self.legacy_path = Path.cwd() / "octobrowse_settings.json"

    def load(
        self,
    ) -> tuple[BrowserSettings, list[str], list[str], list[dict[str, str]], list[str], list[str], list[str]]:
        data: dict[str, Any] = {}
        source = self.path if self.path.exists() else self.legacy_path
        if source.exists():
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}

        settings = BrowserSettings(
            homepage=str(data.get("homepage") or DEFAULT_HOMEPAGE),
            openai_api_key=str(
                data.get("openai_api_key")
                or data.get("openai_key")
                or os.environ.get("OPENAI_API_KEY", "")
            ),
            openai_model=str(data.get("openai_model") or DEFAULT_OPENAI_MODEL),
            weather_location=str(data.get("weather_location") or "London"),
            weather_api_key=str(data.get("weather_api_key") or os.environ.get("OPENWEATHER_API_KEY", "")),
            news_api_key=str(data.get("news_api_key") or os.environ.get("NEWS_API_KEY", "")),
            theme=str(data.get("theme") or "default"),
            custom_theme=data.get("custom_theme") or None,
            ad_block_enabled=bool(data.get("ad_block_enabled", False)),
            user_agent=str(data.get("user_agent") or OCTO_BROWSER_USER_AGENT),
        )
        history = self._unique_strings(data.get("history", []))[-MAX_HISTORY_ITEMS:]
        bookmarks = self._unique_strings(data.get("bookmarks", []))
        notes = self._coerce_notes(data.get("notes", []))
        todos = self._unique_strings(data.get("todos", []))
        session_tabs = self._unique_strings(data.get("session_tabs", []))
        reading_list = self._unique_strings(data.get("reading_list", []))
        return settings, history, bookmarks, notes, todos, session_tabs, reading_list

    def save(
        self,
        settings: BrowserSettings,
        history: list[str],
        bookmarks: list[str],
        notes: list[dict[str, str]],
        todos: list[str],
        session_tabs: list[str],
        reading_list: list[str],
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "homepage": settings.homepage,
            "openai_api_key": settings.openai_api_key,
            "openai_model": settings.openai_model,
            "weather_location": settings.weather_location,
            "weather_api_key": settings.weather_api_key,
            "news_api_key": settings.news_api_key,
            "theme": settings.theme,
            "custom_theme": settings.custom_theme,
            "ad_block_enabled": settings.ad_block_enabled,
            "user_agent": settings.user_agent,
            "history": history[-MAX_HISTORY_ITEMS:],
            "bookmarks": bookmarks,
            "notes": notes,
            "todos": todos,
            "session_tabs": session_tabs,
            "reading_list": reading_list,
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _unique_strings(values: Any) -> list[str]:
        result: list[str] = []
        if not isinstance(values, list):
            return result
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _coerce_notes(values: Any) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if not isinstance(values, list):
            return result
        for item in values:
            if isinstance(item, dict):
                url = str(item.get("url", "")).strip()
                note = str(item.get("note", "")).strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                url = str(item[0]).strip()
                note = str(item[1]).strip()
            else:
                continue
            if url and note:
                result.append({"url": url, "note": note})
        return result


class ApiFetchWorker(QThread):
    data_ready = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, kind: str, url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.url = url

    def run(self) -> None:
        if requests is None:
            self.failed.emit(self.kind, "Install the requests package.")
            return
        try:
            response = requests.get(self.url, timeout=6)
            response.raise_for_status()
            self.data_ready.emit(self.kind, response.json())
        except Exception as exc:  # pragma: no cover - network dependent
            self.failed.emit(self.kind, str(exc))


class OpenAIWorker(QThread):
    result = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(
        self,
        task: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self.api_key = api_key
        self.model = model
        self.messages = messages
        self.max_output_tokens = max_output_tokens

    def run(self) -> None:
        if OpenAI is None:
            self.failed.emit(self.task, "Install the openai package to use AI features.")
            return
        try:
            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(
                model=self.model,
                input=self.messages,
                max_output_tokens=self.max_output_tokens,
            )
            text = getattr(response, "output_text", "") or self._extract_output_text(response)
            if not text:
                raise RuntimeError("The model returned an empty response.")
            self.result.emit(self.task, text.strip())
        except Exception as exc:  # pragma: no cover - network dependent
            self.failed.emit(self.task, str(exc))

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks)


class AdBlockerInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, block_list: set[str]) -> None:
        super().__init__()
        self.block_list = {domain.lower() for domain in block_list}
        self.blocked_by_domain: Counter[str] = Counter()

    def interceptRequest(self, info: Any) -> None:
        host = info.requestUrl().host().lower()
        match = self._matching_domain(host)
        if match:
            self.blocked_by_domain[match] += 1
            info.block(True)

    def reset_stats(self) -> None:
        self.blocked_by_domain.clear()

    def total_blocked(self) -> int:
        return sum(self.blocked_by_domain.values())

    def _matching_domain(self, host: str) -> str | None:
        for domain in self.block_list:
            if host == domain or host.endswith(f".{domain}"):
                return domain
        return None


class PasswordManager:
    """Session-only encrypted password scratchpad."""

    def __init__(self) -> None:
        self.passwords: dict[str, str] = {}
        self.cipher = Fernet(Fernet.generate_key()) if Fernet is not None else None

    def available(self) -> bool:
        return self.cipher is not None

    def encrypt(self, password: str) -> str:
        if self.cipher is None:
            raise RuntimeError("Install cryptography to use the password manager.")
        return self.cipher.encrypt(password.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_password: str) -> str:
        if self.cipher is None:
            raise RuntimeError("Install cryptography to use the password manager.")
        return self.cipher.decrypt(encrypted_password.encode("utf-8")).decode("utf-8")

    def save_password(self, url: str, password: str) -> None:
        self.passwords[url] = self.encrypt(password)

    def get_password(self, url: str) -> str | None:
        encrypted = self.passwords.get(url)
        if not encrypted:
            return None
        return self.decrypt(encrypted)


class SettingsDialog(QDialog):
    def __init__(self, settings: BrowserSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)

        layout = QFormLayout(self)
        self.homepage_edit = QLineEdit(settings.homepage)
        self.openai_key_edit = QLineEdit(settings.openai_api_key)
        self.openai_model_edit = QLineEdit(settings.openai_model)
        self.user_agent_edit = QLineEdit(settings.user_agent)
        self.weather_location_edit = QLineEdit(settings.weather_location)
        self.weather_key_edit = QLineEdit(settings.weather_api_key)
        self.news_key_edit = QLineEdit(settings.news_api_key)

        for key_edit in (self.openai_key_edit, self.weather_key_edit, self.news_key_edit):
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("Homepage URL:", self.homepage_edit)
        layout.addRow("Browser Identity:", self.user_agent_edit)
        layout.addRow("OpenAI API Key:", self.openai_key_edit)
        layout.addRow("OpenAI Model:", self.openai_model_edit)
        layout.addRow("Weather Location:", self.weather_location_edit)
        layout.addRow("OpenWeather API Key:", self.weather_key_edit)
        layout.addRow("NewsAPI Key:", self.news_key_edit)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        layout.addRow(save_btn)

    def to_settings(self, current: BrowserSettings) -> BrowserSettings:
        homepage_text = self.homepage_edit.text().strip() or DEFAULT_HOMEPAGE
        homepage_url = QUrl.fromUserInput(homepage_text)
        if (
            not homepage_url.isValid()
            or homepage_url.scheme() not in {"http", "https", "file"}
            or (homepage_url.scheme() in {"http", "https"} and not homepage_url.host())
        ):
            homepage = DEFAULT_HOMEPAGE
        else:
            homepage = homepage_url.toString()
        return BrowserSettings(
            homepage=homepage,
            openai_api_key=self.openai_key_edit.text().strip(),
            openai_model=self.openai_model_edit.text().strip() or DEFAULT_OPENAI_MODEL,
            weather_location=self.weather_location_edit.text().strip() or "London",
            weather_api_key=self.weather_key_edit.text().strip(),
            news_api_key=self.news_key_edit.text().strip(),
            theme=current.theme,
            custom_theme=current.custom_theme,
            ad_block_enabled=current.ad_block_enabled,
            user_agent=self.user_agent_edit.text().strip() or OCTO_BROWSER_USER_AGENT,
        )


class CommandPalette(QDialog):
    def __init__(self, parent: "OctoBrowse") -> None:
        super().__init__(parent)
        self.browser = parent
        self.commands = parent.available_commands()
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        title = QLabel("Run a command")
        title.setObjectName("PaletteTitle")
        layout.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Type an action, tool, panel, or setting...")
        self.search.textChanged.connect(self.filter_commands)
        self.search.returnPressed.connect(self.run_selected)
        layout.addWidget(self.search)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(lambda _item: self.run_selected())
        layout.addWidget(self.results)

        self.filter_commands("")
        self.search.setFocus()

    def filter_commands(self, query: str) -> None:
        tokens = [token for token in query.lower().split() if token]
        self.results.clear()
        for index, command in enumerate(self.commands):
            haystack = f"{command.label} {command.hint}".lower()
            if all(token in haystack for token in tokens):
                item = QListWidgetItem(f"{command.label}    {command.hint}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def run_selected(self) -> None:
        item = self.results.currentItem()
        if not item:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        self.commands[index].handler()


class OctoBrowse(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(OCTO_BROWSER_NAME)
        self.setGeometry(100, 100, 1200, 800)

        self.store = SettingsStore()
        (
            self.settings,
            self.history,
            self.bookmarks,
            self.notes,
            self.todos,
            self.session_tabs,
            self.reading_list,
        ) = self.store.load()
        self.openai_api_key = self.settings.openai_api_key

        self.dark_mode = self.settings.theme == "dark"
        self.ad_block_enabled = self.settings.ad_block_enabled
        self.incognito_mode = False
        self.password_manager = PasswordManager()
        self.voice_recognizer = sr.Recognizer() if sr is not None else None
        self.chat_mode = False
        self.vpn_enabled = False
        self.default_user_agent = self.settings.user_agent or OCTO_BROWSER_USER_AGENT

        self.network_workers: list[ApiFetchWorker] = []
        self.ai_workers: list[OpenAIWorker] = []
        self.downloads: list[dict[str, str]] = []
        self.closed_tabs: list[dict[str, str]] = []
        self.private_profile: QWebEngineProfile | None = None
        self.profile = QWebEngineProfile.defaultProfile()
        self.apply_browser_identity(self.profile)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.profile.downloadRequested.connect(self.handle_download_requested)
        self.ad_block_interceptor = AdBlockerInterceptor(AD_BLOCK_LIST)
        self.apply_ad_block_to_profiles()

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_context_menu)

        self.notes_sidebar = QTextEdit()
        self.notes_sidebar.setPlaceholderText("Notes and AI chat")
        self.notes_sidebar.hide()

        self.calendar_sidebar = QCalendarWidget()
        self.calendar_sidebar.hide()

        self.todo_sidebar = QListWidget()
        self.todo_sidebar.hide()
        self.todo_sidebar.itemDoubleClicked.connect(self.remove_todo_item)

        self.history_sidebar = QListWidget()
        self.history_sidebar.hide()
        self.history_sidebar.itemDoubleClicked.connect(self.load_history_url)

        self.news_sidebar = QListWidget()
        self.news_sidebar.hide()
        self.news_sidebar.itemDoubleClicked.connect(self.load_news_url)

        self.downloads_sidebar = QListWidget()
        self.downloads_sidebar.hide()

        self.reading_sidebar = QListWidget()
        self.reading_sidebar.hide()
        self.reading_sidebar.itemDoubleClicked.connect(self.load_reading_item)
        self.reading_sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.reading_sidebar.customContextMenuRequested.connect(self.show_reading_context_menu)

        self.bookmarks_sidebar = QListWidget()
        self.bookmarks_sidebar.hide()
        self.bookmarks_sidebar.itemDoubleClicked.connect(self.load_bookmark)
        self.bookmarks_sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bookmarks_sidebar.customContextMenuRequested.connect(self.show_bookmarks_context_menu)

        self.history_sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_sidebar.customContextMenuRequested.connect(self.show_history_context_menu)

        self.extension_tab = QTextEdit()
        self.extension_tab.setPlaceholderText("Enter trusted OctoBrowse extension code here...")
        self.extension_tab.hide()

        self.side_panels = [
            self.notes_sidebar,
            self.calendar_sidebar,
            self.todo_sidebar,
            self.history_sidebar,
            self.news_sidebar,
            self.downloads_sidebar,
            self.reading_sidebar,
            self.bookmarks_sidebar,
            self.extension_tab,
        ]

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        for widget in (
            self.tabs,
            self.notes_sidebar,
            self.calendar_sidebar,
            self.todo_sidebar,
            self.history_sidebar,
            self.news_sidebar,
            self.downloads_sidebar,
            self.reading_sidebar,
            self.bookmarks_sidebar,
            self.extension_tab,
        ):
            self.splitter.addWidget(widget)
        self.setCentralWidget(self.splitter)
        self.splitter.setSizes([980, 260])

        self.create_toolbar()
        self.populate_sidebars()
        self.set_theme(self.settings.theme, persist=False)
        self.open_dashboard()
        self.restore_startup_tabs()

        QTimer.singleShot(0, self.update_weather)
        QTimer.singleShot(0, self.update_news)

    def create_toolbar(self) -> None:
        self.toolbar = QToolBar("Navigation")
        self.toolbar.setMovable(False)
        self.toolbar.setObjectName("BrowserToolbar")
        self.toolbar.setIconSize(QSize(18, 18))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(self.toolbar)

        self._add_action("Tab", "New Tab (Ctrl+T)", lambda: self.add_tab(QUrl(self.settings.homepage), "New Tab"), "Ctrl+T", QStyle.StandardPixmap.SP_FileIcon)
        self._add_action("Priv", "Open Private Tab (Ctrl+Shift+N)", self.open_private_tab, "Ctrl+Shift+N", QStyle.StandardPixmap.SP_DialogResetButton)
        self._add_action("Back", "Back (Backspace)", self.navigate_back, icon=QStyle.StandardPixmap.SP_ArrowBack)
        self._add_action("Fwd", "Forward", self.navigate_forward, icon=QStyle.StandardPixmap.SP_ArrowForward)
        self._add_action("Reload", "Refresh (F5)", self.refresh_page, "F5", QStyle.StandardPixmap.SP_BrowserReload)
        self._add_action("Home", "Open Homepage", self.go_home, icon=QStyle.StandardPixmap.SP_DirHomeIcon)

        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("AddressBar")
        self.url_bar.setPlaceholderText("Enter URL or search term... (Ctrl+L)")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.url_bar.setMinimumWidth(300)
        self.url_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toolbar.addWidget(self.url_bar)

        self.find_bar = QLineEdit()
        self.find_bar.setObjectName("FindBar")
        self.find_bar.setPlaceholderText("Find in page")
        self.find_bar.returnPressed.connect(self.find_in_page)
        self.find_bar.textChanged.connect(self.find_in_page)
        self.find_bar.hide()
        self.toolbar.addWidget(self.find_bar)

        self._add_action("Find", "Find in Page (Ctrl+F)", self.toggle_find_bar, "Ctrl+F", QStyle.StandardPixmap.SP_FileDialogContentsView)
        self._add_action("Prev", "Previous Find Match", self.find_previous)
        self._add_action("Next", "Next Find Match", self.find_in_page)
        self._add_action("Cmd", "Command Palette (Ctrl+K)", self.open_command_palette, "Ctrl+K", QStyle.StandardPixmap.SP_ComputerIcon)

        theme_menu = QMenu("Themes", self)
        self._add_menu_action(theme_menu, "Default", "Use the default theme", lambda: self.set_theme("default"))
        self._add_menu_action(theme_menu, "Dark", "Use the dark theme", lambda: self.set_theme("dark"))
        self._add_menu_action(theme_menu, "Blue", "Use the blue theme", lambda: self.set_theme("blue"))
        self._add_menu_action(theme_menu, "Custom", "Pick a custom window colour", lambda: self.set_theme("custom"))
        self.toolbar.addAction(theme_menu.menuAction())

        panels_menu = QMenu("Panels", self)
        self._add_menu_action(panels_menu, "Notes", "Show notes and AI chat", lambda: self.toggle_panel(self.notes_sidebar))
        self._add_menu_action(panels_menu, "Calendar", "Show calendar", lambda: self.toggle_panel(self.calendar_sidebar))
        self._add_menu_action(panels_menu, "Todo", "Show todo list", lambda: self.toggle_panel(self.todo_sidebar))
        self._add_menu_action(panels_menu, "History", "Show history", lambda: self.toggle_panel(self.history_sidebar), "Ctrl+H")
        self._add_menu_action(panels_menu, "News", "Show news", lambda: self.toggle_panel(self.news_sidebar))
        self._add_menu_action(panels_menu, "Downloads", "Show downloads", lambda: self.toggle_panel(self.downloads_sidebar), "Ctrl+J")
        self._add_menu_action(panels_menu, "Reading List", "Show reading list", lambda: self.toggle_panel(self.reading_sidebar))
        self._add_menu_action(panels_menu, "Bookmarks", "Show bookmarks", self.toggle_bookmarks)
        self._add_menu_action(panels_menu, "Extensions", "Show extension lab", self.toggle_extensions)
        self.toolbar.addAction(panels_menu.menuAction())

        tools_menu = QMenu("Tools", self)
        self._add_menu_action(tools_menu, "Privacy Report", "Show ad-block and privacy state", self.show_privacy_report)
        self._add_menu_action(tools_menu, "Page Insights", "Show word count and keywords", self.show_page_insights)
        self._add_menu_action(tools_menu, "Upscale Page", "Open a 2x screenshot preview", self.upscale_page)
        self._add_menu_action(tools_menu, "Read Aloud", "Read page text aloud", self.read_aloud)
        self._add_menu_action(tools_menu, "Save Screenshot", "Save current viewport as PNG", self.save_screenshot)
        self._add_menu_action(tools_menu, "Duplicate Tab", "Open current page again", self.duplicate_current_tab)
        self._add_menu_action(tools_menu, "Copy URL", "Copy current URL to clipboard", self.copy_current_url)
        self._add_menu_action(tools_menu, "Copy Markdown Link", "Copy current page as a Markdown link", self.copy_markdown_link)
        self._add_menu_action(tools_menu, "Site Info", "Show current site details", self.show_site_info)
        self._add_menu_action(tools_menu, "Tab Overview", "Open a page listing current tabs", self.open_tab_overview)
        self._add_menu_action(tools_menu, "Browser Identity", "Show what sites should see", self.open_browser_identity_page)
        self._add_menu_action(tools_menu, "Test Browser Identity Online", "Open a browser detection site", self.open_browser_identity_test)
        self._add_menu_action(tools_menu, "Voice Command", "Control browser with speech", self.voice_command)
        self._add_menu_action(tools_menu, "Change User Agent", "Set a custom user agent", self.change_user_agent)
        self._add_menu_action(tools_menu, "Session Passwords", "Open session password scratchpad", self.manage_passwords)
        self._add_menu_action(tools_menu, "Run Extension", "Run constrained extension code", self.run_extension)
        self._add_menu_action(tools_menu, "Run Trusted Extension", "Run extension with full Python access", self.run_trusted_extension)
        self.toolbar.addAction(tools_menu.menuAction())

        self._add_action("Block", "Toggle Ad Block", self.toggle_ad_block, icon=QStyle.StandardPixmap.SP_MessageBoxWarning)
        self._add_action("Mark", "Add Bookmark (Ctrl+D)", self.add_bookmark, "Ctrl+D", QStyle.StandardPixmap.SP_DialogSaveButton)
        self._add_action("Settings", "Settings", self.open_settings, icon=QStyle.StandardPixmap.SP_FileDialogDetailedView)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("LoadProgress")
        self.progress_bar.hide()
        self.toolbar.addWidget(self.progress_bar)

        self.weather_widget = QLabel("Weather: Loading...")
        self.weather_widget.setObjectName("WeatherBadge")
        self.toolbar.addWidget(self.weather_widget)

        self.setup_menus()
        self.setup_workspace_rail()
        self.setup_status_bar()
        self.apply_browser_chrome_style()

    def _add_action(
        self,
        text: str,
        tooltip: str,
        handler: Any,
        shortcut: str | None = None,
        icon: QStyle.StandardPixmap | None = None,
    ) -> QAction:
        action = QAction(text, self)
        action.setToolTip(tooltip)
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(handler)
        self.toolbar.addAction(action)
        return action

    def _add_menu_action(
        self,
        menu: QMenu,
        text: str,
        tooltip: str,
        handler: Any,
        shortcut: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        action.setToolTip(tooltip)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(handler)
        menu.addAction(action)
        self.addAction(action)
        return action

    def setup_workspace_rail(self) -> None:
        self.workspace_rail = QToolBar("Workspace")
        self.workspace_rail.setObjectName("WorkspaceRail")
        self.workspace_rail.setMovable(False)
        self.workspace_rail.setOrientation(Qt.Orientation.Vertical)
        self.workspace_rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.workspace_rail)

        self._add_rail_action("Dash", "Open dashboard", self.open_dashboard)
        self._add_rail_action("Notes", "Show notes and AI chat", lambda: self.toggle_panel(self.notes_sidebar))
        self._add_rail_action("Tasks", "Show todo list", lambda: self.toggle_panel(self.todo_sidebar))
        self._add_rail_action("Hist", "Show history", lambda: self.toggle_panel(self.history_sidebar))
        self._add_rail_action("News", "Show news", lambda: self.toggle_panel(self.news_sidebar))
        self._add_rail_action("Down", "Show downloads", lambda: self.toggle_panel(self.downloads_sidebar))
        self._add_rail_action("Read", "Show reading list", lambda: self.toggle_panel(self.reading_sidebar))
        self._add_rail_action("Marks", "Show bookmarks", self.toggle_bookmarks)
        self._add_rail_action("Ext", "Show extension lab", self.toggle_extensions)

    def _add_rail_action(self, text: str, tooltip: str, handler: Any) -> QAction:
        action = QAction(text, self)
        action.setToolTip(tooltip)
        action.triggered.connect(handler)
        self.workspace_rail.addAction(action)
        return action

    def setup_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        self._add_menu_action(file_menu, "New Tab", "Open a new tab", lambda: self.add_tab(QUrl(self.settings.homepage), "New Tab"), "Ctrl+T")
        self._add_menu_action(file_menu, "Private Tab", "Open a private tab", self.open_private_tab, "Ctrl+Shift+N")
        self._add_menu_action(file_menu, "Dashboard", "Open the OctoBrowse dashboard", self.open_dashboard)
        self._add_menu_action(file_menu, "Restore Saved Tabs", "Open tabs from the last saved session", self.restore_saved_tabs)
        self._add_menu_action(file_menu, "Reopen Closed Tab", "Restore the most recently closed tab", self.reopen_closed_tab, "Ctrl+Shift+T")
        self._add_menu_action(file_menu, "Save Page As...", "Save the current page as HTML", self.save_page)
        self._add_menu_action(file_menu, "View Source", "View page source", self.view_page_source)

        view_menu = menu_bar.addMenu("View")
        self._add_menu_action(view_menu, "Command Palette", "Search commands", self.open_command_palette, "Ctrl+K")
        self._add_menu_action(view_menu, "Find in Page", "Search text on the current page", self.toggle_find_bar, "Ctrl+F")
        self._add_menu_action(view_menu, "Reader View", "Open current page text in a clean reader tab", self.open_reader_view)
        self._add_menu_action(view_menu, "Page Insights", "Show page reading metrics", self.show_page_insights)
        self._add_menu_action(view_menu, "Dashboard", "Open workspace dashboard", self.open_dashboard)
        self._add_menu_action(view_menu, "Zoom In", "Increase zoom", self.zoom_in, "Ctrl++")
        self._add_menu_action(view_menu, "Zoom Out", "Decrease zoom", self.zoom_out, "Ctrl+-")
        self._add_menu_action(view_menu, "Fullscreen", "Toggle fullscreen", self.toggle_fullscreen, "F11")

        data_menu = menu_bar.addMenu("Data")
        self._add_menu_action(data_menu, "Add Bookmark", "Bookmark current page", self.add_bookmark, "Ctrl+D")
        self._add_menu_action(data_menu, "Add to Reading List", "Save current page for later", self.add_to_reading_list)
        self._add_menu_action(data_menu, "Add Note", "Attach a note to the current page", self.add_note_for_page)
        self._add_menu_action(data_menu, "Add Task", "Add a todo item", self.add_todo_item)
        self._add_menu_action(data_menu, "Downloads", "Show download panel", lambda: self.toggle_panel(self.downloads_sidebar), "Ctrl+J")
        self._add_menu_action(data_menu, "Clear History", "Clear browser history", self.clear_history)
        self._add_menu_action(data_menu, "Clear Browser Data", "Clear history, cookies, cache, and block stats", self.clear_browser_data)

        ai_menu = menu_bar.addMenu("AI")
        self._add_menu_action(ai_menu, "Summarize Page", "Summarize readable page text", self.summarize_page)
        self._add_menu_action(ai_menu, "Ask About Page", "Open page-aware chat", self.open_chatbot)

    def setup_status_bar(self) -> None:
        self.status_state = QLabel("Ready")
        self.status_privacy = QLabel()
        self.status_blocked = QLabel()
        self.status_zoom = QLabel()
        self.statusBar().addWidget(self.status_state, 1)
        self.statusBar().addPermanentWidget(self.status_privacy)
        self.statusBar().addPermanentWidget(self.status_blocked)
        self.statusBar().addPermanentWidget(self.status_zoom)
        self.update_status_badges()

    def apply_browser_chrome_style(self) -> None:
        if self.dark_mode:
            base_bg = "#111827"
            toolbar_bg = "#172033"
            panel_bg = "#0f172a"
            field_bg = "#1f2937"
            text = "#f8fafc"
            subtle = "#9ca3af"
            border = "#334155"
            accent = "#60a5fa"
            tab_bg = "#1f2937"
            selected_tab = "#0f172a"
            find_bg = "#243145"
        else:
            base_bg = "#f8fafc"
            toolbar_bg = "#f8fafc"
            panel_bg = "#ffffff"
            field_bg = "#ffffff"
            text = "#0f172a"
            subtle = "#536174"
            border = "#cfd7e3"
            accent = "#2563eb"
            tab_bg = "#eef2f7"
            selected_tab = "#ffffff"
            find_bg = "#fffef3"

        self.chrome_stylesheet = f"""
            QMainWindow {{
                background: {base_bg};
                color: {text};
            }}
            QMenuBar, QMenu {{
                background: {panel_bg};
                color: {text};
                border: 1px solid {border};
            }}
            QMenuBar::item:selected, QMenu::item:selected {{
                background: {accent};
                color: #ffffff;
            }}
            QToolBar#BrowserToolbar {{
                spacing: 6px;
                padding: 6px 8px;
                border-bottom: 1px solid {border};
                background: {toolbar_bg};
            }}
            QToolBar#BrowserToolbar QToolButton {{
                min-height: 28px;
                padding: 4px 7px;
                border: 1px solid transparent;
                border-radius: 7px;
                color: {text};
            }}
            QToolBar#BrowserToolbar QToolButton:hover {{
                border-color: {border};
                background: {field_bg};
            }}
            QToolBar#WorkspaceRail {{
                spacing: 4px;
                padding: 8px 5px;
                background: {panel_bg};
                border-right: 1px solid {border};
            }}
            QToolBar#WorkspaceRail QToolButton {{
                min-width: 50px;
                min-height: 32px;
                padding: 5px 6px;
                border: 1px solid transparent;
                border-radius: 7px;
                color: {text};
            }}
            QToolBar#WorkspaceRail QToolButton:hover {{
                background: {base_bg};
                border-color: {border};
            }}
            QLineEdit#AddressBar {{
                min-width: 280px;
                max-width: 760px;
                padding: 7px 11px;
                border: 1px solid {border};
                border-radius: 8px;
                background: {field_bg};
                color: {text};
                selection-background-color: {accent};
            }}
            QLineEdit#FindBar {{
                max-width: 180px;
                padding: 6px 9px;
                border: 1px solid {border};
                border-radius: 7px;
                background: {find_bg};
                color: {text};
            }}
            QProgressBar#LoadProgress {{
                max-width: 110px;
                max-height: 10px;
                border: 1px solid {border};
                border-radius: 5px;
                background: {base_bg};
            }}
            QProgressBar#LoadProgress::chunk {{
                border-radius: 5px;
                background: {accent};
            }}
            QLabel#WeatherBadge {{
                padding: 3px 8px;
                border: 1px solid {border};
                border-radius: 7px;
                background: {field_bg};
                color: {text};
            }}
            QTabWidget::pane {{
                border-top: 1px solid {border};
            }}
            QTabBar::tab {{
                min-width: 96px;
                max-width: 220px;
                padding: 7px 12px;
                border: 1px solid {border};
                border-bottom: none;
                background: {tab_bg};
                color: {text};
            }}
            QTabBar::tab:selected {{
                background: {selected_tab};
                color: {text};
            }}
            QListWidget, QTextEdit, QPlainTextEdit {{
                border: 1px solid {border};
                background: {panel_bg};
                color: {text};
                selection-background-color: {accent};
            }}
            QStatusBar {{
                background: {panel_bg};
                color: {subtle};
                border-top: 1px solid {border};
            }}
            QLabel#PaletteTitle {{
                font-size: 18px;
                font-weight: 600;
                color: {text};
            }}
            """
        self.refresh_app_stylesheet()

    def refresh_app_stylesheet(self) -> None:
        self.setStyleSheet(
            getattr(self, "window_theme_stylesheet", "") + getattr(self, "chrome_stylesheet", "")
        )

    def set_status(self, message: str) -> None:
        if hasattr(self, "status_state"):
            self.status_state.setText(message)

    def update_status_badges(self) -> None:
        if not hasattr(self, "status_privacy"):
            return
        browser = self.current_browser()
        private = bool(browser and browser.property("private"))
        zoom = browser.zoomFactor() if browser else 1.0
        self.status_privacy.setText("Private tab" if private else "Standard tab")
        self.status_blocked.setText(
            f"Ad block {'on' if self.ad_block_enabled else 'off'} | {self.ad_block_interceptor.total_blocked()} blocked"
        )
        self.status_zoom.setText(f"Zoom {int(zoom * 100)}%")

    def available_commands(self) -> list[BrowserCommand]:
        return [
            BrowserCommand("Open dashboard", "workspace overview", self.open_dashboard),
            BrowserCommand("Restore saved tabs", "last session", self.restore_saved_tabs),
            BrowserCommand("New tab", "Ctrl+T", lambda: self.add_tab(QUrl(self.settings.homepage), "New Tab")),
            BrowserCommand("Private tab", "Ctrl+Shift+N", self.open_private_tab),
            BrowserCommand("Go home", "homepage", self.go_home),
            BrowserCommand("Find in page", "Ctrl+F", self.toggle_find_bar),
            BrowserCommand("Reader view", "clean readable page", self.open_reader_view),
            BrowserCommand("Page insights", "word count keywords", self.show_page_insights),
            BrowserCommand("Save screenshot", "PNG viewport", self.save_screenshot),
            BrowserCommand("Duplicate tab", "open current page again", self.duplicate_current_tab),
            BrowserCommand("Reopen closed tab", "Ctrl+Shift+T", self.reopen_closed_tab),
            BrowserCommand("Copy current URL", "clipboard", self.copy_current_url),
            BrowserCommand("Copy markdown link", "title and URL", self.copy_markdown_link),
            BrowserCommand("Site info", "scheme host privacy zoom", self.show_site_info),
            BrowserCommand("Tab overview", "current tabs", self.open_tab_overview),
            BrowserCommand("Browser identity", "user agent navigator brands", self.open_browser_identity_page),
            BrowserCommand("Test browser identity online", "what browser site", self.open_browser_identity_test),
            BrowserCommand("Summarize page", "OpenAI", self.summarize_page),
            BrowserCommand("Ask about page", "AI chat", self.open_chatbot),
            BrowserCommand("Toggle ad block", "privacy", self.toggle_ad_block),
            BrowserCommand("Privacy report", "blocked requests", self.show_privacy_report),
            BrowserCommand("Add bookmark", "Ctrl+D", self.add_bookmark),
            BrowserCommand("Add to reading list", "read later", self.add_to_reading_list),
            BrowserCommand("Show bookmarks", "panel", self.toggle_bookmarks),
            BrowserCommand("Show history", "panel", lambda: self.toggle_panel(self.history_sidebar)),
            BrowserCommand("Show notes", "panel", lambda: self.toggle_panel(self.notes_sidebar)),
            BrowserCommand("Show todos", "panel", lambda: self.toggle_panel(self.todo_sidebar)),
            BrowserCommand("Show news", "panel", lambda: self.toggle_panel(self.news_sidebar)),
            BrowserCommand("Show downloads", "panel Ctrl+J", lambda: self.toggle_panel(self.downloads_sidebar)),
            BrowserCommand("Show reading list", "panel", lambda: self.toggle_panel(self.reading_sidebar)),
            BrowserCommand("Show extensions", "panel", self.toggle_extensions),
            BrowserCommand("Run trusted extension", "full Python access", self.run_trusted_extension),
            BrowserCommand("Add note", "current page", self.add_note_for_page),
            BrowserCommand("Add task", "todo", self.add_todo_item),
            BrowserCommand("Read aloud", "text to speech", self.read_aloud),
            BrowserCommand("Upscale page", "image preview", self.upscale_page),
            BrowserCommand("Settings", "keys and homepage", self.open_settings),
            BrowserCommand("Clear browser data", "history cookies cache", self.clear_browser_data),
        ]

    def open_command_palette(self) -> None:
        CommandPalette(self).exec()

    def duplicate_current_tab(self) -> None:
        browser = self.current_browser()
        if browser:
            self.add_tab(browser.url(), "Duplicate", private=bool(browser.property("private")))

    def copy_current_url(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        QApplication.clipboard().setText(browser.url().toString())
        self.set_status("Copied URL")

    def copy_markdown_link(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        title = self.tabs.tabText(self.tabs.currentIndex()).replace("Private - ", "").strip() or "Link"
        url = browser.url().toString()
        safe_title = title.replace("[", "\\[").replace("]", "\\]")
        QApplication.clipboard().setText(f"[{safe_title}]({url})")
        self.set_status("Copied Markdown link")

    def open_tab_overview(self) -> None:
        rows: list[str] = []
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if not isinstance(widget, QWebEngineView):
                continue
            title = html.escape(self.tabs.tabText(index))
            url = widget.url().toString()
            safe_url = html.escape(url, quote=True)
            mode = "Private" if widget.property("private") else "Standard"
            rows.append(f"<tr><td>{index + 1}</td><td>{title}</td><td>{mode}</td><td><a href=\"{safe_url}\">{safe_url}</a></td></tr>")
        table = "\n".join(rows) or "<tr><td colspan='4'>No open tabs.</td></tr>"
        overview_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Tab Overview</title>
<style>
body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f7f9fc; color: #142033; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 34px 24px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9e1ec; }}
th, td {{ border-bottom: 1px solid #e2e8f0; padding: 10px 12px; text-align: left; vertical-align: top; }}
th {{ background: #edf2f7; }}
a {{ color: #0f5dcc; overflow-wrap: anywhere; }}
</style>
</head>
<body>
<main>
<h1>Tab Overview</h1>
<p>{len(rows)} open tabs. Private tabs are not included in session restore.</p>
<table><thead><tr><th>#</th><th>Title</th><th>Mode</th><th>URL</th></tr></thead><tbody>{table}</tbody></table>
</main>
</body>
</html>"""
        self.add_html_tab(overview_html, "Tab Overview", private=False)

    def show_site_info(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url()
        lines = [
            f"URL: {url.toString()}",
            f"Scheme: {url.scheme() or 'unknown'}",
            f"Host: {url.host() or 'local page'}",
            f"Private tab: {'yes' if browser.property('private') else 'no'}",
            f"Zoom: {int(browser.zoomFactor() * 100)}%",
            f"Ad block: {'on' if self.ad_block_enabled else 'off'}",
            f"Blocked this session: {self.ad_block_interceptor.total_blocked()}",
            f"HTTP user agent: {self.profile.httpUserAgent()}",
        ]
        QMessageBox.information(self, "Site Info", "\n".join(lines))

    def open_browser_identity_page(self) -> None:
        user_agent = html.escape(self.settings.user_agent or OCTO_BROWSER_USER_AGENT)
        name = html.escape(OCTO_BROWSER_NAME)
        version = html.escape(OCTO_BROWSER_VERSION)
        identity_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Browser Identity</title>
<style>
body {{
  margin: 0;
  font-family: Segoe UI, Arial, sans-serif;
  background: #f6f8fb;
  color: #152033;
}}
main {{
  max-width: 960px;
  margin: 0 auto;
  padding: 36px 24px;
}}
h1 {{ margin-bottom: 4px; }}
.sub {{ color: #64748b; margin-bottom: 22px; }}
.panel {{
  background: #fff;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  padding: 18px;
  margin: 14px 0;
}}
code, pre {{
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #eef3f8;
  border-radius: 6px;
  padding: 10px;
  display: block;
}}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
</style>
</head>
<body>
<main>
  <h1>{name}</h1>
  <div class="sub">Identity sent to sites by OctoBrowser {version}</div>
  <section class="panel">
    <h2>HTTP User-Agent</h2>
    <code>{user_agent}</code>
  </section>
  <section class="grid">
    <div class="panel"><h2>Navigator</h2><pre id="nav"></pre></div>
    <div class="panel"><h2>User-Agent Client Hints</h2><pre id="hints"></pre></div>
  </section>
</main>
<script>
(async () => {{
  document.getElementById('nav').textContent = JSON.stringify({{
    appName: navigator.appName,
    appCodeName: navigator.appCodeName,
    userAgent: navigator.userAgent,
    vendor: navigator.vendor,
    platform: navigator.platform,
    octoBrowser: window.octoBrowser || null
  }}, null, 2);
  let hints = null;
  if (navigator.userAgentData) {{
    hints = await navigator.userAgentData.getHighEntropyValues([
      'brands', 'fullVersionList', 'platform', 'platformVersion', 'architecture', 'bitness', 'uaFullVersion'
    ]);
  }}
  document.getElementById('hints').textContent = JSON.stringify(hints, null, 2);
}})();
</script>
</body>
</html>"""
        self.add_html_tab(identity_html, "Browser Identity", private=False)

    def open_browser_identity_test(self) -> None:
        self.add_tab(QUrl("https://www.whatismybrowser.com/"), "Identity Test", private=False)

    def populate_sidebars(self) -> None:
        for url in self.history:
            self.history_sidebar.addItem(QListWidgetItem(url))
        for bookmark in self.bookmarks:
            self.bookmarks_sidebar.addItem(QListWidgetItem(bookmark))
        for url in self.reading_list:
            self.reading_sidebar.addItem(QListWidgetItem(url))
        for todo in self.todos:
            self.todo_sidebar.addItem(QListWidgetItem(todo))
        for note in self.notes:
            self.notes_sidebar.append(f"Note for {note['url']}:\n{note['note']}\n")

    def current_browser(self) -> QWebEngineView | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, QWebEngineView) else None

    def profile_for_tab(self, private: bool) -> QWebEngineProfile:
        if not private:
            return self.profile
        if self.private_profile is None:
            self.private_profile = QWebEngineProfile(self)
            self.apply_browser_identity(self.private_profile)
            self.private_profile.downloadRequested.connect(self.handle_download_requested)
            if self.ad_block_enabled:
                self.private_profile.setUrlRequestInterceptor(self.ad_block_interceptor)
        return self.private_profile

    def apply_browser_identity(self, profile: QWebEngineProfile) -> None:
        user_agent = self.settings.user_agent or OCTO_BROWSER_USER_AGENT
        self.default_user_agent = user_agent
        profile.setHttpUserAgent(user_agent)
        self.install_identity_script(profile, user_agent)

    def install_identity_script(self, profile: QWebEngineProfile, user_agent: str) -> None:
        major_version = OCTO_BROWSER_VERSION.split(".", 1)[0]
        identity = {
            "name": OCTO_BROWSER_NAME,
            "version": OCTO_BROWSER_VERSION,
            "majorVersion": major_version,
            "userAgent": user_agent,
            "vendor": "OctoBrowse",
            "platform": "Windows",
        }
        source = f"""
(() => {{
  const identity = {json.dumps(identity)};
  const brands = [
    {{ brand: identity.name, version: identity.majorVersion }},
    {{ brand: "OctoBrowser", version: identity.majorVersion }},
    {{ brand: "Chromium", version: "126" }}
  ];
  const fullVersionList = [
    {{ brand: identity.name, version: identity.version }},
    {{ brand: "OctoBrowser", version: identity.version }},
    {{ brand: "Chromium", version: "126.0.0.0" }}
  ];
  const defineNavigator = (name, getter) => {{
    try {{
      Object.defineProperty(Navigator.prototype, name, {{ get: getter, configurable: true }});
    }} catch (_err) {{
      try {{ Object.defineProperty(navigator, name, {{ get: getter, configurable: true }}); }} catch (_err2) {{}}
    }}
  }};
  defineNavigator("userAgent", () => identity.userAgent);
  defineNavigator("appName", () => identity.name);
  defineNavigator("appCodeName", () => "OctoBrowser");
  defineNavigator("vendor", () => identity.vendor);
  defineNavigator("platform", () => "Win32");
  defineNavigator("userAgentData", () => ({{
    brands,
    mobile: false,
    platform: identity.platform,
    getHighEntropyValues: async (hints = []) => {{
      const values = {{
        brands,
        mobile: false,
        platform: identity.platform,
        architecture: "x86",
        bitness: "64",
        model: "",
        platformVersion: "15.0.0",
        uaFullVersion: identity.version,
        fullVersionList
      }};
      const out = {{}};
      for (const hint of hints) {{
        if (Object.prototype.hasOwnProperty.call(values, hint)) out[hint] = values[hint];
      }}
      return out;
    }},
    toJSON: () => ({{ brands, mobile: false, platform: identity.platform }})
  }}));
  Object.defineProperty(window, "octoBrowser", {{
    value: Object.freeze({{ name: identity.name, version: identity.version, userAgent: identity.userAgent }}),
    configurable: true
  }});
}})();
"""
        script = QWebEngineScript()
        script.setName("OctoBrowserIdentity")
        script.setSourceCode(source)
        script.setRunsOnSubFrames(True)
        try:
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        except AttributeError:
            script.setInjectionPoint(2)
        try:
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        except AttributeError:
            script.setWorldId(0)

        scripts = profile.scripts()
        try:
            for old_script in scripts.findScripts("OctoBrowserIdentity"):
                scripts.remove(old_script)
        except Exception:
            try:
                old_script = scripts.findScript("OctoBrowserIdentity")
                scripts.remove(old_script)
            except Exception:
                pass
        scripts.insert(script)

    def apply_ad_block_to_profiles(self) -> None:
        interceptor = self.ad_block_interceptor if self.ad_block_enabled else None
        self.profile.setUrlRequestInterceptor(interceptor)
        if self.private_profile is not None:
            self.private_profile.setUrlRequestInterceptor(interceptor)

    def add_tab(self, url: QUrl, title: str, private: bool | None = None) -> None:
        is_private = self.incognito_mode if private is None else private
        browser = QWebEngineView()
        browser.setProperty("private", is_private)
        browser.setPage(QWebEnginePage(self.profile_for_tab(is_private), browser))
        browser.load(url)

        display_title = f"Private - {title}" if is_private else title
        index = self.tabs.addTab(browser, display_title)
        self.tabs.setCurrentIndex(index)

        browser.urlChanged.connect(lambda new_url, browser=browser: self.update_url_bar(new_url, browser))
        browser.loadProgress.connect(lambda progress, browser=browser: self.update_progress_bar(progress, browser))
        browser.loadFinished.connect(lambda _ok, browser=browser: self.on_load_finished(browser))
        browser.titleChanged.connect(lambda page_title, browser=browser: self.update_tab_title(browser, page_title))
        self.update_status_badges()
        self.set_status("Opened private tab" if is_private else "Opened tab")

    def restore_startup_tabs(self) -> None:
        restored = self.restore_saved_tabs(select_first=False)
        if not restored:
            self.add_tab(QUrl(self.settings.homepage), "Home", private=False)
            self.tabs.setCurrentIndex(0)

    def restore_saved_tabs(self, select_first: bool = True) -> int:
        restored = 0
        for url in self.session_tabs[:8]:
            if self.is_internal_url(url):
                continue
            self.add_tab(QUrl(url), "Restored", private=False)
            restored += 1
        if restored and not select_first:
            self.tabs.setCurrentIndex(0)
        if select_first:
            self.set_status(f"Restored {restored} tab{'s' if restored != 1 else ''}")
        return restored

    def get_session_tabs(self) -> list[str]:
        urls: list[str] = []
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if not isinstance(widget, QWebEngineView) or widget.property("private"):
                continue
            url = widget.url().toString()
            if url and not self.is_internal_url(url) and url not in urls:
                urls.append(url)
        return urls[:12]

    def is_internal_url(self, url: str) -> bool:
        return (
            not url
            or url.startswith("about:")
            or url.startswith("data:")
            or "octobrowse.local" in url
        )

    def update_tab_title(self, browser: QWebEngineView, title: str) -> None:
        index = self.tabs.indexOf(browser)
        if index == -1:
            return
        cleaned = title.strip() or "New Tab"
        if browser.property("private"):
            cleaned = f"Private - {cleaned}"
        if len(cleaned) > 32:
            cleaned = f"{cleaned[:29]}..."
        self.tabs.setTabText(index, cleaned)
        self.tabs.setTabToolTip(index, browser.url().toString())

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, QWebEngineView) and not widget.property("private"):
            url = widget.url().toString()
            if not self.is_internal_url(url):
                self.closed_tabs.append({"url": url, "title": self.tabs.tabText(index) or "Closed Tab"})
                self.closed_tabs = self.closed_tabs[-20:]
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)
            if widget is not None:
                widget.deleteLater()
        elif self.tabs.count() == 1:
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget is not None:
                widget.deleteLater()
            self.open_dashboard()
        self.save_settings()
        self.update_status_badges()

    def reopen_closed_tab(self) -> None:
        if not self.closed_tabs:
            self.set_status("No closed tabs")
            return
        tab = self.closed_tabs.pop()
        self.add_tab(QUrl(tab["url"]), tab.get("title", "Reopened"), private=False)
        self.set_status("Reopened closed tab")

    def on_tab_changed(self, _index: int) -> None:
        browser = self.current_browser()
        if not browser:
            return
        self.url_bar.setText(browser.url().toString())
        self.progress_bar.hide()
        self.update_status_badges()
        self.set_status("Ready")

    def open_private_tab(self) -> None:
        self.add_tab(QUrl(self.settings.homepage), "Private", private=True)

    def toggle_incognito_mode(self) -> None:
        self.incognito_mode = not self.incognito_mode
        if self.incognito_mode:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self.open_private_tab()
            QMessageBox.information(
                self,
                "Private Mode",
                "Private mode is enabled. New tabs use an off-the-record profile and history is paused.",
            )
        else:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            QMessageBox.information(self, "Private Mode", "Private mode is disabled for new tabs.")

    def navigate_back(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.back()

    def navigate_forward(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.forward()

    def refresh_page(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.reload()
            self.set_status("Reloading")

    def go_home(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.setUrl(self.build_url(self.settings.homepage))

    def navigate_to_url(self) -> None:
        url_text = self.url_bar.text().strip()
        if not url_text:
            return
        if self.handle_octo_command(url_text):
            return
        browser = self.current_browser()
        if browser:
            browser.setUrl(self.build_url(url_text))
            self.set_status("Navigating")

    def handle_octo_command(self, url_text: str) -> bool:
        command = url_text.strip().lower()
        if not command.startswith("octo:"):
            return False
        target = command.split(":", 1)[1].strip()
        actions = {
            "dashboard": self.open_dashboard,
            "home": self.go_home,
            "identity": self.open_browser_identity_page,
            "tabs": self.open_tab_overview,
            "downloads": lambda: self.toggle_panel(self.downloads_sidebar),
            "history": lambda: self.toggle_panel(self.history_sidebar),
            "bookmarks": self.toggle_bookmarks,
            "reading": lambda: self.toggle_panel(self.reading_sidebar),
            "settings": self.open_settings,
        }
        action = actions.get(target)
        if action is None:
            self.set_status(f"Unknown Octo command: {target}")
            return True
        action()
        return True

    def toggle_find_bar(self) -> None:
        self.find_bar.setVisible(not self.find_bar.isVisible())
        if self.find_bar.isVisible():
            self.find_bar.setFocus()
            self.find_bar.selectAll()
        else:
            browser = self.current_browser()
            if browser:
                browser.page().findText("")

    def find_in_page(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.page().findText(self.find_bar.text())

    def find_previous(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.page().findText(self.find_bar.text(), QWebEnginePage.FindFlag.FindBackward)

    def build_url(self, url_text: str) -> QUrl:
        lowered = url_text.lower()
        bang_url = self.build_bang_url(url_text)
        if bang_url is not None:
            return bang_url
        if lowered.startswith(("http://", "https://", "file://")):
            return QUrl(url_text)
        if " " not in url_text and ("." in url_text or ":" in url_text or lowered == "localhost"):
            candidate = QUrl.fromUserInput(url_text)
            if candidate.isValid():
                return candidate
        return QUrl(f"https://www.google.com/search?q={quote_plus(url_text)}")

    def build_bang_url(self, url_text: str) -> QUrl | None:
        bangs = {
            "!ddg": "https://duckduckgo.com/?q={query}",
            "!yt": "https://www.youtube.com/results?search_query={query}",
            "!gh": "https://github.com/search?q={query}",
            "!w": "https://en.wikipedia.org/w/index.php?search={query}",
            "!maps": "https://www.google.com/maps/search/{query}",
            "!news": "https://news.google.com/search?q={query}",
            "!pypi": "https://pypi.org/search/?q={query}",
            "!mdn": "https://developer.mozilla.org/en-US/search?q={query}",
        }
        command, _, query = url_text.partition(" ")
        command = command.lower()
        if command not in bangs:
            return None
        return QUrl(bangs[command].format(query=quote_plus(query.strip())))

    def add_html_tab(self, html_text: str, title: str, private: bool = False) -> None:
        browser = QWebEngineView()
        browser.setProperty("private", private)
        browser.setPage(QWebEnginePage(self.profile_for_tab(private), browser))
        browser.setHtml(html_text, QUrl("https://octobrowse.local/"))
        index = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(index)
        browser.urlChanged.connect(lambda new_url, browser=browser: self.update_url_bar(new_url, browser))
        browser.loadProgress.connect(lambda progress, browser=browser: self.update_progress_bar(progress, browser))
        browser.loadFinished.connect(lambda _ok, browser=browser: self.on_load_finished(browser))
        browser.titleChanged.connect(lambda page_title, browser=browser: self.update_tab_title(browser, page_title))
        self.update_status_badges()

    def open_dashboard(self) -> None:
        self.add_html_tab(self.build_dashboard_html(), "Dashboard", private=False)

    def build_dashboard_html(self) -> str:
        history_links = self._dashboard_links(self.history[-8:])
        bookmark_links = self._dashboard_links(self.bookmarks[:10])
        notes_count = len(self.notes)
        todo_count = len(self.todos)
        reading_count = len(self.reading_list)
        blocked = self.ad_block_interceptor.total_blocked()
        downloads_count = len(self.downloads)
        saved_tabs_count = len(self.session_tabs)
        weather = html.escape(self.weather_widget.text() if hasattr(self, "weather_widget") else "Weather unavailable")
        browser_identity = html.escape((self.settings.user_agent or OCTO_BROWSER_USER_AGENT).split(") ", 1)[-1])
        return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>OctoBrowse Dashboard</title>
<style>
body {{
  margin: 0;
  font-family: Segoe UI, Arial, sans-serif;
  color: #172033;
  background: #f4f7fb;
}}
main {{
  max-width: 1120px;
  margin: 0 auto;
  padding: 34px 24px 48px;
}}
h1 {{ margin: 0 0 6px; font-size: 38px; }}
.sub {{ color: #536174; margin-bottom: 24px; }}
.grid {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 14px; }}
.metric, .panel {{
  background: #ffffff;
  border: 1px solid #dce3ec;
  border-radius: 8px;
  padding: 16px;
}}
.metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
.wide {{ margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
a {{ color: #0f5dcc; text-decoration: none; }}
li {{ margin: 8px 0; }}
.empty {{ color: #6b7280; }}
</style>
</head>
<body>
<main>
  <h1>OctoBrowse</h1>
  <div class="sub">Workspace dashboard for quick return, privacy awareness, and page work.</div>
  <section class="grid">
    <div class="metric">History<strong>{len(self.history)}</strong></div>
    <div class="metric">Bookmarks<strong>{len(self.bookmarks)}</strong></div>
    <div class="metric">Todos<strong>{todo_count}</strong></div>
    <div class="metric">Blocked<strong>{blocked}</strong></div>
    <div class="metric">Reading<strong>{reading_count}</strong></div>
    <div class="metric">Saved Tabs<strong>{saved_tabs_count}</strong></div>
  </section>
  <section class="wide">
    <div class="panel"><h2>Recent</h2>{history_links}</div>
    <div class="panel"><h2>Bookmarks</h2>{bookmark_links}</div>
  </section>
  <section class="wide">
    <div class="panel"><h2>Session</h2><p>{weather}</p><p>{notes_count} saved notes in this workspace.</p><p>Identity: {browser_identity}</p></div>
    <div class="panel"><h2>Shortcuts</h2><p>Ctrl+K command palette</p><p>Ctrl+F find in page</p><p>Ctrl+D bookmark</p><p>Ctrl+J downloads</p><p>Ctrl+Shift+T reopen tab</p></div>
  </section>
</main>
</body>
</html>"""

    def _dashboard_links(self, urls: list[str]) -> str:
        if not urls:
            return '<p class="empty">Nothing saved yet.</p>'
        items = []
        for url in urls:
            safe_url = html.escape(url, quote=True)
            label = html.escape(url.replace("https://", "").replace("http://", "")[:72])
            items.append(f'<li><a href="{safe_url}">{label}</a></li>')
        return f"<ul>{''.join(items)}</ul>"

    def open_reader_view(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        browser.page().toPlainText(lambda text: self.show_reader_tab(text, browser.url().toString(), bool(browser.property("private"))))

    def show_reader_tab(self, text: str, url: str, private: bool) -> None:
        cleaned = self.clean_page_text(text)
        if not cleaned:
            QMessageBox.information(self, "Reader View", "There is no readable text on this page.")
            return
        words = cleaned.split()
        minutes = max(1, round(len(words) / 220))
        paragraphs = [paragraph for paragraph in cleaned.split("\n\n") if paragraph.strip()][:80]
        body = "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
        keywords = ", ".join(self.extract_keywords(cleaned, limit=8))
        safe_url = html.escape(url)
        reader_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Reader View</title>
<style>
body {{
  margin: 0;
  font-family: Georgia, Cambria, serif;
  color: #151922;
  background: #fbfbf8;
}}
article {{
  max-width: 780px;
  margin: 0 auto;
  padding: 44px 24px 64px;
  line-height: 1.72;
  font-size: 19px;
}}
h1 {{ font-family: Segoe UI, Arial, sans-serif; font-size: 32px; margin-bottom: 4px; }}
.meta {{ font-family: Segoe UI, Arial, sans-serif; color: #667085; font-size: 14px; margin-bottom: 28px; }}
p {{ margin: 0 0 20px; }}
</style>
</head>
<body>
<article>
  <h1>Reader View</h1>
  <div class="meta">{len(words)} words | about {minutes} min | {keywords}<br>{safe_url}</div>
  {body}
</article>
</body>
</html>"""
        self.add_html_tab(reader_html, "Reader View", private=private)

    def show_page_insights(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        browser.page().toPlainText(lambda text: self.display_page_insights(text, browser.url().toString()))

    def display_page_insights(self, text: str, url: str) -> None:
        cleaned = self.clean_page_text(text)
        words = cleaned.split()
        minutes = max(1, round(len(words) / 220)) if words else 0
        keywords = ", ".join(self.extract_keywords(cleaned, limit=10)) or "None"
        lines = [
            f"URL: {url}",
            f"Words: {len(words)}",
            f"Estimated read time: {minutes} min",
            f"Top terms: {keywords}",
            f"Ad-blocked requests this session: {self.ad_block_interceptor.total_blocked()}",
        ]
        QMessageBox.information(self, "Page Insights", "\n".join(lines))

    def clean_page_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines()]
        blocks: list[str] = []
        buffer: list[str] = []
        for line in lines:
            if line:
                buffer.append(line)
            elif buffer:
                blocks.append(" ".join(buffer))
                buffer = []
        if buffer:
            blocks.append(" ".join(buffer))
        return "\n\n".join(blocks)

    def extract_keywords(self, text: str, limit: int = 8) -> list[str]:
        stop_words = {
            "about", "after", "again", "also", "because", "before", "between", "could", "every",
            "from", "have", "into", "more", "most", "other", "over", "page", "some", "such",
            "than", "that", "their", "there", "these", "this", "through", "when", "where", "which",
            "with", "would", "your",
        }
        words = [
            word.strip(".,:;!?()[]{}\"'").lower()
            for word in text.split()
            if len(word.strip(".,:;!?()[]{}\"'")) > 3
        ]
        counts = Counter(word for word in words if word and word not in stop_words)
        return [word for word, _count in counts.most_common(limit)]

    def update_url_bar(self, url: QUrl, browser: QWebEngineView) -> None:
        if browser != self.current_browser():
            return
        text = url.toString()
        self.url_bar.setText(text)
        if not self.incognito_mode and not browser.property("private") and not self.is_internal_url(text):
            self.add_to_history(text)
        self.update_status_badges()

    def add_to_history(self, url: str) -> None:
        if self.is_internal_url(url) or url in self.history:
            return
        self.history.append(url)
        self.history = self.history[-MAX_HISTORY_ITEMS:]
        self.history_sidebar.addItem(QListWidgetItem(url))
        self.save_settings()

    def load_history_url(self, item: QListWidgetItem) -> None:
        self.url_bar.setText(item.text())
        self.navigate_to_url()

    def clear_history(self) -> None:
        self.history.clear()
        self.history_sidebar.clear()
        self.save_settings()
        QMessageBox.information(self, "History Cleared", "Browsing history has been cleared.")

    def clear_browser_data(self) -> None:
        self.history.clear()
        self.history_sidebar.clear()
        self.profile.clearHttpCache()
        self.profile.cookieStore().deleteAllCookies()
        if self.private_profile is not None:
            self.private_profile.clearHttpCache()
            self.private_profile.cookieStore().deleteAllCookies()
        self.ad_block_interceptor.reset_stats()
        self.save_settings()
        QMessageBox.information(self, "Browser Data", "History, cookies, cache, and privacy stats were cleared.")

    def update_progress_bar(self, progress: int, browser: QWebEngineView) -> None:
        if browser == self.current_browser():
            self.progress_bar.setValue(progress)
            self.progress_bar.setVisible(progress < 100)

    def on_load_finished(self, browser: QWebEngineView) -> None:
        if browser == self.current_browser():
            self.progress_bar.hide()
            self.set_status("Ready")
            self.update_status_badges()
        if self.dark_mode:
            self.apply_dark_mode(browser)

    def toggle_dark_mode(self) -> None:
        self.set_theme("default" if self.dark_mode else "dark")

    def apply_dark_mode(self, browser: QWebEngineView) -> None:
        css = """
            html, body {
                background-color: #121212 !important;
                color: #e0e0e0 !important;
            }
            a { color: #8ab4f8 !important; }
            header, footer, nav, aside, section, main {
                background-color: #1f1f1f !important;
                color: #e0e0e0 !important;
            }
        """ if self.dark_mode else ""
        js = f"""
            (function() {{
                var style = document.getElementById('octobrowse-dark-mode-style');
                if (!style) {{
                    style = document.createElement('style');
                    style.id = 'octobrowse-dark-mode-style';
                    document.head.appendChild(style);
                }}
                style.textContent = `{css}`;
            }})();
        """
        browser.page().runJavaScript(js)

    def set_theme(self, theme: str, persist: bool = True) -> None:
        if theme == "custom":
            if not persist and self.settings.custom_theme:
                self.apply_custom_theme(QColor(self.settings.custom_theme))
            elif persist:
                self.create_custom_theme()
            elif self.settings.custom_theme:
                self.apply_custom_theme(QColor(self.settings.custom_theme))
            else:
                self.set_theme("default", persist=False)
            return

        self.settings.theme = theme if theme in {"default", "dark", "blue"} else "default"
        self.dark_mode = self.settings.theme == "dark"
        if self.settings.theme == "dark":
            self.window_theme_stylesheet = "QMainWindow { background-color: #121212; color: #e0e0e0; }"
        elif self.settings.theme == "blue":
            self.window_theme_stylesheet = "QMainWindow { background-color: #e6f3ff; color: #202124; }"
        else:
            self.window_theme_stylesheet = ""
        if hasattr(self, "chrome_stylesheet"):
            self.apply_browser_chrome_style()
        else:
            self.refresh_app_stylesheet()

        for index in range(self.tabs.count()):
            browser = self.tabs.widget(index)
            if isinstance(browser, QWebEngineView):
                self.apply_dark_mode(browser)
        if persist:
            self.save_settings()

    def create_custom_theme(self) -> None:
        color = QColorDialog.getColor(QColor(self.settings.custom_theme or "#ffffff"), self)
        if not color.isValid():
            return
        self.apply_custom_theme(color)
        self.save_settings()

    def apply_custom_theme(self, color: QColor) -> None:
        self.settings.theme = "custom"
        self.settings.custom_theme = color.name()
        self.dark_mode = color.lightness() < 128
        foreground = "#f7f7f7" if self.dark_mode else "#202124"
        self.window_theme_stylesheet = (
            f"QMainWindow {{ background-color: {self.settings.custom_theme}; color: {foreground}; }}"
        )
        if hasattr(self, "chrome_stylesheet"):
            self.apply_browser_chrome_style()
        else:
            self.refresh_app_stylesheet()
        for index in range(self.tabs.count()):
            browser = self.tabs.widget(index)
            if isinstance(browser, QWebEngineView):
                self.apply_dark_mode(browser)

    def upscale_page(self) -> None:
        if cv2 is None:
            QMessageBox.critical(self, "Upscale Page", "Install opencv-python to use page upscaling.")
            return
        browser = self.current_browser()
        if not browser:
            return
        screenshot_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                screenshot_path = temp_file.name
            browser.grab().save(screenshot_path)
            image = cv2.imread(screenshot_path)
            if image is None:
                raise ValueError("Screenshot capture failed.")
            upscaled = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                upscaled_path = temp_file.name
            cv2.imwrite(upscaled_path, upscaled)
            self.add_tab(QUrl.fromLocalFile(upscaled_path), "Upscaled", private=bool(browser.property("private")))
        except Exception as exc:
            QMessageBox.critical(self, "Upscale Page", f"Failed to upscale: {exc}")
        finally:
            if screenshot_path:
                Path(screenshot_path).unlink(missing_ok=True)

    def save_screenshot(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        default_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation) or str(Path.home())
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            str(Path(default_dir) / "octobrowse-screenshot.png"),
            "PNG Images (*.png)",
        )
        if not file_path:
            return
        if browser.grab().save(file_path):
            self.set_status(f"Saved screenshot: {Path(file_path).name}")
        else:
            QMessageBox.critical(self, "Save Screenshot", "Could not save the screenshot.")

    def zoom_in(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.setZoomFactor(min(browser.zoomFactor() + 0.1, 3.0))
            self.update_status_badges()

    def zoom_out(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.setZoomFactor(max(browser.zoomFactor() - 0.1, 0.25))
            self.update_status_badges()

    def read_aloud(self) -> None:
        if gTTS is None:
            QMessageBox.critical(self, "Read Aloud", "Install gTTS to use text-to-speech.")
            return
        browser = self.current_browser()
        if browser:
            browser.page().toPlainText(lambda text: self.speak_text(text[:1500]))

    def speak_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            QMessageBox.information(self, "Read Aloud", "There is no readable text on this page.")
            return
        try:
            tts = gTTS(text, lang="en", slow=False)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                output_file = temp_file.name
            tts.save(output_file)
            if os.name == "nt":
                os.startfile(output_file)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["afplay", output_file])
            else:
                subprocess.Popen(["xdg-open", output_file])
            QTimer.singleShot(15000, lambda path=output_file: Path(path).unlink(missing_ok=True))
        except Exception as exc:
            QMessageBox.critical(self, "Read Aloud", f"Text-to-speech failed: {exc}")

    def toggle_ad_block(self) -> None:
        self.ad_block_enabled = not self.ad_block_enabled
        self.apply_ad_block_to_profiles()
        status = "enabled" if self.ad_block_enabled else "disabled"
        self.update_status_badges()
        self.save_settings()
        QMessageBox.information(self, "Ad Block", f"Ad block {status}.")

    def show_privacy_report(self) -> None:
        blocked = self.ad_block_interceptor.total_blocked()
        top_domains = self.ad_block_interceptor.blocked_by_domain.most_common(8)
        lines = [
            f"Ad block: {'on' if self.ad_block_enabled else 'off'}",
            f"Blocked requests this session: {blocked}",
            f"History entries: {len(self.history)}",
            f"Bookmarks: {len(self.bookmarks)}",
            f"Current tab: {'private' if self.current_browser() and self.current_browser().property('private') else 'standard'}",
        ]
        if top_domains:
            lines.append("")
            lines.extend(f"{domain}: {count}" for domain, count in top_domains)
        QMessageBox.information(self, "Privacy Report", "\n".join(lines))

    def summarize_page(self) -> None:
        if not self.ensure_openai_key():
            return
        browser = self.current_browser()
        if browser:
            browser.page().toPlainText(lambda text: self.generate_summary(text[:8000]))

    def ensure_openai_key(self) -> bool:
        if self.openai_api_key:
            return True
        key, ok = QInputDialog.getText(self, "OpenAI API Key", "Enter your OpenAI API key:")
        if not ok or not key.strip():
            QMessageBox.critical(self, "OpenAI", "OpenAI API key is required for this feature.")
            return False
        self.openai_api_key = key.strip()
        self.settings.openai_api_key = self.openai_api_key
        self.save_settings()
        return True

    def generate_summary(self, text: str) -> None:
        text = text.strip()
        if not text:
            QMessageBox.information(self, "Summary", "There is no readable text on this page.")
            return
        messages = [
            {
                "role": "developer",
                "content": "Summarize browser page text clearly. Keep it concise, factual, and useful.",
            },
            {
                "role": "user",
                "content": f"Summarize this page in five bullets and include one suggested next action:\n\n{text}",
            },
        ]
        self.start_openai_worker("summary", messages, max_output_tokens=260)

    def open_chatbot(self) -> None:
        self.chat_mode = True
        self.notes_sidebar.show()
        self.notes_sidebar.setFocus()
        self.notes_sidebar.append("Ask about the current page on a new line, then press Enter.\n")
        self.set_status("Page chat mode")

    def process_chatbot_query(self, query: str) -> None:
        query = query.strip()
        if not query or not self.ensure_openai_key():
            return
        browser = self.current_browser()
        if browser:
            browser.page().toPlainText(lambda text: self.generate_chatbot_response(query, text[:8000]))

    def generate_chatbot_response(self, query: str, page_text: str) -> None:
        messages = [
            {
                "role": "developer",
                "content": "Answer questions about the current browser page. Say when the page text is insufficient.",
            },
            {
                "role": "user",
                "content": f"Page text:\n{page_text}\n\nQuestion: {query}",
            },
        ]
        self.start_openai_worker("chat", messages, max_output_tokens=320)

    def start_openai_worker(
        self,
        task: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
    ) -> None:
        worker = OpenAIWorker(
            task=task,
            api_key=self.openai_api_key,
            model=self.settings.openai_model or DEFAULT_OPENAI_MODEL,
            messages=messages,
            max_output_tokens=max_output_tokens,
            parent=self,
        )
        worker.result.connect(self.handle_openai_result)
        worker.failed.connect(self.handle_openai_error)
        worker.finished.connect(lambda worker=worker: self.cleanup_ai_worker(worker))
        self.ai_workers.append(worker)
        worker.start()

    def cleanup_ai_worker(self, worker: OpenAIWorker) -> None:
        if worker in self.ai_workers:
            self.ai_workers.remove(worker)

    def handle_openai_result(self, task: str, text: str) -> None:
        if task == "chat":
            self.notes_sidebar.append(f"\nAI:\n{text}\n")
        else:
            QMessageBox.information(self, "Summary", text)

    def handle_openai_error(self, task: str, error: str) -> None:
        target = self.notes_sidebar if task == "chat" else None
        if target is not None:
            target.append(f"\nAI error: {error}\n")
        else:
            QMessageBox.critical(self, "OpenAI", f"Failed to generate summary: {error}")

    def voice_command(self) -> None:
        if sr is None or self.voice_recognizer is None:
            QMessageBox.critical(self, "Voice Command", "Install SpeechRecognition and PyAudio to use voice commands.")
            return
        try:
            with sr.Microphone() as source:
                QMessageBox.information(self, "Voice Command", "Listening...")
                audio = self.voice_recognizer.listen(source, timeout=5)
                command = self.voice_recognizer.recognize_google(audio)
                QMessageBox.information(self, "Voice Command", f"You said: {command}")
                self.process_voice_command(command)
        except sr.UnknownValueError:
            QMessageBox.critical(self, "Voice Command", "Could not understand audio.")
        except sr.RequestError:
            QMessageBox.critical(self, "Voice Command", "Speech recognition service unavailable.")
        except Exception as exc:
            QMessageBox.critical(self, "Voice Command", f"Voice command error: {exc}")

    def process_voice_command(self, command: str) -> None:
        normalized = command.lower()
        if "go to" in normalized:
            self.url_bar.setText(command.lower().replace("go to", "", 1).strip())
            self.navigate_to_url()
        elif "refresh" in normalized:
            self.refresh_page()
        elif "back" in normalized:
            self.navigate_back()
        elif "forward" in normalized:
            self.navigate_forward()
        elif "zoom in" in normalized:
            self.zoom_in()
        elif "zoom out" in normalized:
            self.zoom_out()
        elif "read aloud" in normalized:
            self.read_aloud()
        elif "summarize" in normalized or "summarise" in normalized:
            self.summarize_page()
        elif "new tab" in normalized:
            self.add_tab(QUrl(self.settings.homepage), "New Tab")
        elif "private tab" in normalized:
            self.open_private_tab()
        elif "close tab" in normalized:
            self.close_tab(self.tabs.currentIndex())
        else:
            QMessageBox.information(self, "Voice Command", "Command not recognized.")

    def change_user_agent(self) -> None:
        user_agent, ok = QInputDialog.getText(
            self,
            "Change User Agent",
            "Enter the browser identity user agent:",
            text=self.settings.user_agent or OCTO_BROWSER_USER_AGENT,
        )
        if ok and user_agent.strip():
            user_agent = user_agent.strip()
            self.settings.user_agent = user_agent
            self.apply_browser_identity(self.profile)
            if self.private_profile is not None:
                self.apply_browser_identity(self.private_profile)
            self.save_settings()
            QMessageBox.information(self, "Browser Identity", f"Browser identity changed to:\n{user_agent}")

    def update_weather(self) -> None:
        if not self.settings.weather_api_key:
            self.weather_widget.setText("Weather: set API key")
            return
        location = quote_plus(self.settings.weather_location)
        url = (
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q={location}&appid={self.settings.weather_api_key}&units=metric"
        )
        self.start_api_worker("weather", url)

    def update_news(self) -> None:
        if not self.settings.news_api_key:
            self.news_sidebar.clear()
            self.news_sidebar.addItem(QListWidgetItem("News: set API key"))
            return
        url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={self.settings.news_api_key}"
        self.start_api_worker("news", url)

    def start_api_worker(self, kind: str, url: str) -> None:
        worker = ApiFetchWorker(kind, url, self)
        worker.data_ready.connect(self.handle_api_data)
        worker.failed.connect(self.handle_api_error)
        worker.finished.connect(lambda worker=worker: self.cleanup_api_worker(worker))
        self.network_workers.append(worker)
        worker.start()

    def cleanup_api_worker(self, worker: ApiFetchWorker) -> None:
        if worker in self.network_workers:
            self.network_workers.remove(worker)

    def handle_api_data(self, kind: str, data: object) -> None:
        if kind == "weather" and isinstance(data, dict):
            try:
                temp = data["main"]["temp"]
                condition = data["weather"][0]["description"]
                self.weather_widget.setText(f"Weather: {temp} C, {condition}")
            except (KeyError, IndexError, TypeError):
                self.weather_widget.setText("Weather: Unavailable")
        elif kind == "news" and isinstance(data, dict):
            self.news_sidebar.clear()
            articles = data.get("articles", [])
            if not isinstance(articles, list) or not articles:
                self.news_sidebar.addItem(QListWidgetItem("News: Unavailable"))
                return
            for article in articles[:8]:
                if not isinstance(article, dict):
                    continue
                title = str(article.get("title") or "No Title")
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, article.get("url") or "")
                self.news_sidebar.addItem(item)

    def handle_api_error(self, kind: str, _error: str) -> None:
        if kind == "weather":
            self.weather_widget.setText("Weather: Unavailable")
        elif kind == "news":
            self.news_sidebar.clear()
            self.news_sidebar.addItem(QListWidgetItem("News: Unavailable"))

    def load_news_url(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.ItemDataRole.UserRole)
        if url:
            self.add_tab(QUrl(str(url)), item.text())

    def handle_download_requested(self, download: Any) -> None:
        default_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())
        suggested_name = download.downloadFileName() or "download"
        suggested_path = str(Path(default_dir) / suggested_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Download", suggested_path)
        if not file_path:
            download.cancel()
            self.set_status("Download cancelled")
            return

        target = Path(file_path)
        download.setDownloadDirectory(str(target.parent))
        download.setDownloadFileName(target.name)
        item = QListWidgetItem(f"Downloading: {target.name}")
        item.setToolTip(str(target))
        self.downloads_sidebar.addItem(item)
        self.downloads_sidebar.show()
        self.downloads.append({"file": str(target), "status": "downloading"})
        self.set_status(f"Downloading {target.name}")

        try:
            download.receivedBytesChanged.connect(lambda item=item, download=download: self.update_download_progress(download, item))
            download.stateChanged.connect(lambda _state, item=item, download=download: self.update_download_state(download, item))
        except Exception:
            pass
        download.accept()

    def update_download_progress(self, download: Any, item: QListWidgetItem) -> None:
        received = max(0, int(download.receivedBytes()))
        total = max(0, int(download.totalBytes()))
        filename = download.downloadFileName() or "download"
        if total:
            percent = int((received / total) * 100)
            item.setText(f"Downloading: {filename} ({percent}%)")
            self.set_status(f"Downloading {filename} ({percent}%)")
        else:
            item.setText(f"Downloading: {filename} ({received // 1024} KB)")

    def update_download_state(self, download: Any, item: QListWidgetItem) -> None:
        state_name = getattr(download.state(), "name", str(download.state()))
        filename = download.downloadFileName() or "download"
        if "Completed" in state_name:
            item.setText(f"Complete: {filename}")
            self.set_status(f"Downloaded {filename}")
        elif "Cancelled" in state_name:
            item.setText(f"Cancelled: {filename}")
            self.set_status("Download cancelled")
        elif "Interrupted" in state_name:
            item.setText(f"Failed: {filename}")
            self.set_status("Download failed")

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_weather = (self.settings.weather_api_key, self.settings.weather_location)
        old_news_key = self.settings.news_api_key
        self.settings = dialog.to_settings(self.settings)
        self.openai_api_key = self.settings.openai_api_key
        self.save_settings()
        if (self.settings.weather_api_key, self.settings.weather_location) != old_weather:
            self.update_weather()
        if self.settings.news_api_key != old_news_key:
            self.update_news()

    def show_context_menu(self, position: Any) -> None:
        tab_index = self.tabs.tabBar().tabAt(self.tabs.tabBar().mapFrom(self.tabs, position))
        if tab_index >= 0:
            self.tabs.setCurrentIndex(tab_index)
        menu = QMenu(self)
        reload_action = QAction("Reload Tab", self)
        reload_action.triggered.connect(self.refresh_page)
        menu.addAction(reload_action)

        duplicate_action = QAction("Duplicate Tab", self)
        duplicate_action.triggered.connect(self.duplicate_current_tab)
        menu.addAction(duplicate_action)

        close_action = QAction("Close Tab", self)
        close_action.triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))
        menu.addAction(close_action)
        menu.addSeparator()

        save_action = QAction("Save Page As...", self)
        save_action.triggered.connect(self.save_page)
        menu.addAction(save_action)

        view_source_action = QAction("View Page Source", self)
        view_source_action.triggered.connect(self.view_page_source)
        menu.addAction(view_source_action)

        open_tab_action = QAction("Open Current Page in New Tab", self)
        open_tab_action.triggered.connect(self.open_in_new_tab)
        menu.addAction(open_tab_action)

        reader_action = QAction("Open Reader View", self)
        reader_action.triggered.connect(self.open_reader_view)
        menu.addAction(reader_action)

        insights_action = QAction("Page Insights", self)
        insights_action.triggered.connect(self.show_page_insights)
        menu.addAction(insights_action)

        bookmark_action = QAction("Add Bookmark", self)
        bookmark_action.triggered.connect(self.add_bookmark)
        menu.addAction(bookmark_action)

        menu.exec(self.tabs.mapToGlobal(position))

    def save_page(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Page As", "", "HTML Files (*.html)")
        if file_path:
            browser.page().toHtml(lambda html: self.write_html(file_path, html))

    def write_html(self, file_path: str, html: str) -> None:
        try:
            Path(file_path).write_text(html, encoding="utf-8")
            QMessageBox.information(self, "Save Page", "Page saved successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Save Page", f"Failed to save page: {exc}")

    def view_page_source(self) -> None:
        browser = self.current_browser()
        if browser:
            browser.page().toHtml(self.show_source_code)

    def show_source_code(self, html: str) -> None:
        source_window = QDialog(self)
        source_window.setWindowTitle("Page Source")
        source_window.setModal(True)
        source_window.resize(900, 650)
        layout = QVBoxLayout(source_window)
        source_edit = QPlainTextEdit()
        source_edit.setPlainText(html)
        source_edit.setReadOnly(True)
        layout.addWidget(source_edit)
        source_window.exec()

    def open_in_new_tab(self) -> None:
        browser = self.current_browser()
        if browser:
            self.add_tab(browser.url(), "New Tab", private=bool(browser.property("private")))

    def toggle_panel(self, widget: QWidget) -> None:
        should_show = not widget.isVisible()
        for panel in self.side_panels:
            panel.hide()
        widget.setVisible(should_show)
        if should_show:
            self.splitter.setSizes([900, 300])
            self.set_status("Panel opened")
        else:
            self.set_status("Panel closed")

    def toggle_extensions(self) -> None:
        self.toggle_panel(self.extension_tab)

    def run_extension(self) -> None:
        code = self.extension_tab.toPlainText().strip()
        if not code:
            return
        output: list[str] = []

        def safe_print(*args: object, sep: str = " ", end: str = "\n") -> None:
            output.append(sep.join(str(arg) for arg in args) + end.rstrip("\n"))

        safe_builtins = {
            "Exception": Exception,
            "False": False,
            "True": True,
            "None": None,
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "print": safe_print,
            "range": range,
            "round": round,
            "str": str,
            "sum": sum,
            "tuple": tuple,
        }
        env = {
            "__builtins__": safe_builtins,
            "browser": self,
            "current_tab": self.current_browser(),
            "QUrl": QUrl,
        }
        try:
            exec(compile(code, "<octobrowse-extension>", "exec"), env, env)
            message = "\n".join(line for line in output if line) or "Extension executed successfully."
            QMessageBox.information(self, "Extension", message[:4000])
        except Exception as exc:
            QMessageBox.critical(self, "Extension", f"Failed to run extension: {exc}")

    def run_trusted_extension(self) -> None:
        code = self.extension_tab.toPlainText().strip()
        if not code:
            return
        answer = QMessageBox.warning(
            self,
            "Trusted Extension",
            "This runs extension code with full Python access, matching the original prototype behavior. Only run code you wrote or fully trust.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            exec(
                compile(code, "<octobrowse-trusted-extension>", "exec"),
                {"browser": self, "current_tab": self.current_browser(), "__builtins__": __builtins__},
                {},
            )
            QMessageBox.information(self, "Trusted Extension", "Extension executed successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Trusted Extension", f"Failed to run extension: {exc}")

    def add_note_for_page(self) -> None:
        self.chat_mode = False
        browser = self.current_browser()
        if not browser:
            return
        note, ok = QInputDialog.getText(self, "Add Note", "Enter your note:")
        if ok and note.strip():
            url = browser.url().toString()
            entry = {"url": url, "note": note.strip()}
            self.notes.append(entry)
            self.notes_sidebar.append(f"Note for {url}:\n{entry['note']}\n")
            self.save_settings()

    def add_todo_item(self) -> None:
        task, ok = QInputDialog.getText(self, "Add Task", "Enter a task:")
        if ok and task.strip():
            text = task.strip()
            self.todos.append(text)
            self.todo_sidebar.addItem(QListWidgetItem(text))
            self.todo_sidebar.show()
            self.save_settings()

    def remove_todo_item(self, item: QListWidgetItem) -> None:
        row = self.todo_sidebar.row(item)
        if row >= 0:
            self.todo_sidebar.takeItem(row)
        try:
            self.todos.remove(item.text())
        except ValueError:
            pass
        self.save_settings()

    def toggle_bookmarks(self) -> None:
        self.toggle_panel(self.bookmarks_sidebar)

    def add_bookmark(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        if url in self.bookmarks:
            QMessageBox.information(self, "Bookmark Exists", "This bookmark already exists.")
            return
        self.bookmarks.append(url)
        self.bookmarks_sidebar.addItem(QListWidgetItem(url))
        self.save_settings()
        QMessageBox.information(self, "Bookmark Added", f"Bookmark added: {url}")

    def add_to_reading_list(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        if self.is_internal_url(url):
            self.set_status("Internal pages are not added to the reading list")
            return
        if url in self.reading_list:
            self.set_status("Already in reading list")
            return
        self.reading_list.append(url)
        self.reading_sidebar.addItem(QListWidgetItem(url))
        self.save_settings()
        self.set_status("Added to reading list")

    def load_reading_item(self, item: QListWidgetItem) -> None:
        self.add_tab(QUrl(item.text()), "Reading")

    def show_reading_context_menu(self, position: Any) -> None:
        item = self.reading_sidebar.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self.load_reading_item(item))
        menu.addAction(open_action)
        remove_action = QAction("Remove Reading Item", self)
        remove_action.triggered.connect(lambda: self.remove_reading_item(item))
        menu.addAction(remove_action)
        menu.exec(self.reading_sidebar.mapToGlobal(position))

    def remove_reading_item(self, item: QListWidgetItem) -> None:
        url = item.text()
        row = self.reading_sidebar.row(item)
        if row >= 0:
            self.reading_sidebar.takeItem(row)
        if url in self.reading_list:
            self.reading_list.remove(url)
        self.save_settings()
        self.set_status("Reading item removed")

    def load_bookmark(self, item: QListWidgetItem) -> None:
        self.url_bar.setText(item.text())
        self.navigate_to_url()

    def show_bookmarks_context_menu(self, position: Any) -> None:
        item = self.bookmarks_sidebar.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self.load_bookmark(item))
        menu.addAction(open_action)
        new_tab_action = QAction("Open in New Tab", self)
        new_tab_action.triggered.connect(lambda: self.add_tab(QUrl(item.text()), "Bookmark"))
        menu.addAction(new_tab_action)
        remove_action = QAction("Remove Bookmark", self)
        remove_action.triggered.connect(lambda: self.remove_bookmark(item))
        menu.addAction(remove_action)
        menu.exec(self.bookmarks_sidebar.mapToGlobal(position))

    def remove_bookmark(self, item: QListWidgetItem) -> None:
        url = item.text()
        row = self.bookmarks_sidebar.row(item)
        if row >= 0:
            self.bookmarks_sidebar.takeItem(row)
        if url in self.bookmarks:
            self.bookmarks.remove(url)
        self.save_settings()
        self.set_status("Bookmark removed")

    def show_history_context_menu(self, position: Any) -> None:
        item = self.history_sidebar.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self.load_history_url(item))
        menu.addAction(open_action)
        new_tab_action = QAction("Open in New Tab", self)
        new_tab_action.triggered.connect(lambda: self.add_tab(QUrl(item.text()), "History"))
        menu.addAction(new_tab_action)
        remove_action = QAction("Remove History Entry", self)
        remove_action.triggered.connect(lambda: self.remove_history_entry(item))
        menu.addAction(remove_action)
        menu.exec(self.history_sidebar.mapToGlobal(position))

    def remove_history_entry(self, item: QListWidgetItem) -> None:
        url = item.text()
        row = self.history_sidebar.row(item)
        if row >= 0:
            self.history_sidebar.takeItem(row)
        if url in self.history:
            self.history.remove(url)
        self.save_settings()
        self.set_status("History entry removed")

    def manage_passwords(self) -> None:
        if not self.password_manager.available():
            QMessageBox.critical(self, "Passwords", "Install cryptography to use the password manager.")
            return
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        password = self.password_manager.get_password(url) or ""

        dialog = QDialog(self)
        dialog.setWindowTitle("Session Password")
        layout = QFormLayout(dialog)
        password_input = QLineEdit(password)
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Password:", password_input)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(lambda: self.save_session_password(url, password_input.text(), dialog))
        layout.addRow(save_btn)
        dialog.exec()

    def save_session_password(self, url: str, password: str, dialog: QDialog) -> None:
        try:
            self.password_manager.save_password(url, password)
            dialog.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Passwords", str(exc))

    def save_settings(self) -> None:
        self.settings.openai_api_key = self.openai_api_key
        self.settings.ad_block_enabled = self.ad_block_enabled
        try:
            self.store.save(
                self.settings,
                self.history,
                self.bookmarks,
                self.notes,
                self.todos,
                self.get_session_tabs(),
                self.reading_list,
            )
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape and self.find_bar.isVisible():
            self.toggle_find_bar()
        elif event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_F5:
            self.refresh_page()
        elif event.key() == Qt.Key.Key_Backspace:
            self.navigate_back()
        elif event.key() == Qt.Key.Key_L and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.url_bar.setFocus()
            self.url_bar.selectAll()
        elif event.key() == Qt.Key.Key_K and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.open_command_palette()
        elif event.key() == Qt.Key.Key_F and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.toggle_find_bar()
        elif event.key() == Qt.Key.Key_D and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.add_bookmark()
        elif event.key() == Qt.Key.Key_H and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.toggle_panel(self.history_sidebar)
        elif event.key() == Qt.Key.Key_J and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.toggle_panel(self.downloads_sidebar)
        elif event.key() == Qt.Key.Key_T and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.add_tab(QUrl(self.settings.homepage), "New Tab")
        elif event.key() == Qt.Key.Key_T and event.modifiers() == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            self.reopen_closed_tab()
        elif event.key() == Qt.Key.Key_W and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.close_tab(self.tabs.currentIndex())
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_Minus and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.zoom_out()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.notes_sidebar.hasFocus() and self.chat_mode:
            query = self.notes_sidebar.toPlainText().splitlines()[-1] if self.notes_sidebar.toPlainText() else ""
            if query.strip():
                self.process_chatbot_query(query)
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: Any) -> None:
        self.save_settings()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(OCTO_BROWSER_NAME)
    app.setOrganizationName("OctoBrowse")
    browser = OctoBrowse()
    browser.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

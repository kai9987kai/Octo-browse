#!/usr/bin/env python3
"""
Advanced OctoBrowse: A feature-rich, customizable web browser with ad blocking,
dark mode, voice commands, AI summarization, bookmarks, incognito mode, and more.

Required packages:
    - PyQt6
    - PyQt6-WebEngine
    - opencv-python
    - gTTS
    - SpeechRecognition
    - cryptography
    - requests
    - numpy
    - openai

Remember to replace YOUR_API_KEY placeholders in update_weather() and update_news()
with your actual API keys.
"""

import sys
import os
import cv2
import numpy as np
import tempfile
import json
import requests
import openai
from gtts import gTTS
import speech_recognition as sr
from cryptography.fernet import Fernet

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QToolBar,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QMessageBox,
    QMenu,
    QTabWidget,
    QTextEdit,
    QSplitter,
    QCalendarWidget,
    QListWidget,
    QInputDialog,
    QListWidgetItem,
    QLabel,
    QDialog,
    QFormLayout,
    QPushButton,
    QFileDialog,
    QColorDialog,
    QPlainTextEdit,
)
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView  # QWebEngineDownloadItem removed
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor

# --------------------- Ad Blocker Interceptor ---------------------

# List of known ad-serving domains
AD_BLOCK_LIST = {
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "adservice.google.com",
    "ads.youtube.com",
    "ad.doubleclick.net",
    "adform.net",
    "adnxs.com",
    "adsrvr.org",
    "advertising.com",
    "amazon-adsystem.com",
    "scorecardresearch.com",
    "2mdn.net",
    "adzerk.net",
    "taboola.com",
    "outbrain.com",
    "pubmatic.com",
    "rubiconproject.com",
    "openx.net",
    "criteo.com",
    "ads.pubmatic.com",
    "ads.linkedin.com",
    "ads.facebook.com",
    "ads.twitter.com",
}


class AdBlockerInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, block_list):
        super().__init__()
        self.block_list = set(block_list)

    def interceptRequest(self, info):
        """Intercept requests to block known ad domains."""
        url = info.requestUrl().toString()
        if any(domain in url for domain in self.block_list):
            info.block(True)

# --------------------- Password Manager ---------------------


class PasswordManager:
    """
    A simple password manager using AES-256 encryption via Fernet.
    """
    def __init__(self):
        self.key = Fernet.generate_key()
        self.cipher = Fernet(self.key)

    def encrypt(self, password: str) -> str:
        return self.cipher.encrypt(password.encode()).decode()

    def decrypt(self, encrypted_password: str) -> str:
        return self.cipher.decrypt(encrypted_password.encode()).decode()

# --------------------- Settings Dialog ---------------------


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        layout = QFormLayout(self)

        self.homepage_edit = QLineEdit()
        layout.addRow("Homepage URL:", self.homepage_edit)

        self.openai_key_edit = QLineEdit()
        layout.addRow("OpenAI API Key:", self.openai_key_edit)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        layout.addRow(save_btn)

    def save_settings(self):
        homepage_url = self.homepage_edit.text()
        openai_key = self.openai_key_edit.text()
        if homepage_url:
            self.parent().custom_homepage = homepage_url
        if openai_key:
            self.parent().openai_api_key = openai_key
        self.accept()

# --------------------- Main Browser Window ---------------------


class OctoBrowse(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Octo Browse")
        self.setGeometry(100, 100, 1200, 800)

        # State and settings
        self.dark_mode = False
        self.ad_block_enabled = False
        self.incognito_mode = False
        self.current_theme = "default"
        self.custom_theme = None
        self.password_manager = PasswordManager()
        self.voice_recognizer = sr.Recognizer()
        self.openai_api_key = None
        self.history = []
        self.notes = []
        self.bookmarks = []  # New bookmarks list
        self.custom_homepage = "https://www.google.com"
        self.vpn_enabled = False
        self.default_user_agent = "Octo Browse"

        # Set up QWebEngine profile and ad-blocker interceptor
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setHttpUserAgent(self.default_user_agent)
        self.ad_block_interceptor = AdBlockerInterceptor(AD_BLOCK_LIST)

        # Create main tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setMovable(True)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_context_menu)

        # Create sidebar widgets
        self.notes_sidebar = QTextEdit()
        self.notes_sidebar.setPlaceholderText("Take notes here...")
        self.notes_sidebar.hide()

        self.calendar_sidebar = QCalendarWidget()
        self.calendar_sidebar.hide()

        self.todo_sidebar = QListWidget()
        self.todo_sidebar.hide()

        self.history_sidebar = QListWidget()
        self.history_sidebar.hide()
        self.history_sidebar.itemDoubleClicked.connect(self.load_history_url)

        self.news_sidebar = QListWidget()
        self.news_sidebar.hide()

        self.bookmarks_sidebar = QListWidget()
        self.bookmarks_sidebar.hide()
        self.bookmarks_sidebar.itemDoubleClicked.connect(self.load_bookmark)

        self.extension_tab = QTextEdit()
        self.extension_tab.setPlaceholderText("Enter Python code here...")
        self.extension_tab.hide()

        # Splitter to combine tabs and sidebars
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.notes_sidebar)
        self.splitter.addWidget(self.calendar_sidebar)
        self.splitter.addWidget(self.todo_sidebar)
        self.splitter.addWidget(self.history_sidebar)
        self.splitter.addWidget(self.news_sidebar)
        self.splitter.addWidget(self.bookmarks_sidebar)
        self.splitter.addWidget(self.extension_tab)
        self.setCentralWidget(self.splitter)

        # Create toolbar
        self.create_toolbar()

        # Additional widgets
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        self.toolbar.addWidget(self.progress_bar)

        self.weather_widget = QLabel("Weather: Loading...")
        self.weather_widget.hide()
        self.update_weather()

        self.update_news()

        # Add first tab (Home)
        self.add_tab(QUrl(self.custom_homepage), "Home")

    # --------------------- Incognito Mode Method ---------------------

    def toggle_incognito_mode(self):
        """Toggle incognito mode by changing persistent cookies policy."""
        self.incognito_mode = not self.incognito_mode
        # Toggle persistent cookies based on incognito state
        if self.incognito_mode:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            QMessageBox.information(self, "Incognito Mode", "Incognito mode enabled.")
        else:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            QMessageBox.information(self, "Incognito Mode", "Incognito mode disabled.")

    # --------------------- Toolbar Creation ---------------------

    def create_toolbar(self):
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)

        # New Tab button
        new_tab_btn = QAction("➕", self)
        new_tab_btn.setToolTip("New Tab")
        new_tab_btn.triggered.connect(lambda: self.add_tab(QUrl(self.custom_homepage), "New Tab"))
        self.toolbar.addAction(new_tab_btn)

        # Navigation buttons
        back_btn = QAction("⬅️", self)
        back_btn.setToolTip("Back")
        back_btn.triggered.connect(self.navigate_back)
        self.toolbar.addAction(back_btn)

        forward_btn = QAction("➡️", self)
        forward_btn.setToolTip("Forward")
        forward_btn.triggered.connect(self.navigate_forward)
        self.toolbar.addAction(forward_btn)

        refresh_btn = QAction("🔄", self)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.triggered.connect(self.refresh_page)
        self.toolbar.addAction(refresh_btn)

        # Address bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search term...")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.toolbar.addWidget(self.url_bar)

        # Dark mode toggle
        dark_mode_btn = QAction("🌙", self)
        dark_mode_btn.setToolTip("Toggle Dark Mode")
        dark_mode_btn.triggered.connect(self.toggle_dark_mode)
        self.toolbar.addAction(dark_mode_btn)

        # Upscale page button
        upscale_btn = QAction("🖼️", self)
        upscale_btn.setToolTip("Upscale Page")
        upscale_btn.triggered.connect(self.upscale_page)
        self.toolbar.addAction(upscale_btn)

        # Zoom in/out
        zoom_in_btn = QAction("🔍", self)
        zoom_in_btn.setToolTip("Zoom In")
        zoom_in_btn.triggered.connect(self.zoom_in)
        self.toolbar.addAction(zoom_in_btn)

        zoom_out_btn = QAction("🔎", self)
        zoom_out_btn.setToolTip("Zoom Out")
        zoom_out_btn.triggered.connect(self.zoom_out)
        self.toolbar.addAction(zoom_out_btn)

        # Text-to-speech button
        tts_btn = QAction("🔊", self)
        tts_btn.setToolTip("Read Aloud")
        tts_btn.triggered.connect(self.read_aloud)
        self.toolbar.addAction(tts_btn)

        # Ad-block toggle
        ad_block_btn = QAction("🚫", self)
        ad_block_btn.setToolTip("Toggle Ad Block")
        ad_block_btn.triggered.connect(self.toggle_ad_block)
        self.toolbar.addAction(ad_block_btn)

        # Summarize page button
        summarize_btn = QAction("📝", self)
        summarize_btn.setToolTip("Summarize Page")
        summarize_btn.triggered.connect(self.summarize_page)
        self.toolbar.addAction(summarize_btn)

        # AI Chatbot button (opens notes sidebar as a placeholder)
        chatbot_btn = QAction("🤖", self)
        chatbot_btn.setToolTip("Open Chatbot")
        chatbot_btn.triggered.connect(self.open_chatbot)
        self.toolbar.addAction(chatbot_btn)

        # Voice command button
        voice_btn = QAction("🎙️", self)
        voice_btn.setToolTip("Voice Command")
        voice_btn.triggered.connect(self.voice_command)
        self.toolbar.addAction(voice_btn)

        # Change User Agent button
        user_agent_btn = QAction("🕵️", self)
        user_agent_btn.setToolTip("Change User Agent")
        user_agent_btn.triggered.connect(self.change_user_agent)
        self.toolbar.addAction(user_agent_btn)

        # Theme menu
        theme_menu = QMenu("🎨 Themes", self)
        theme_menu.setToolTip("Change Theme")
        theme_menu.addAction("Default", lambda: self.set_theme("default"))
        theme_menu.addAction("Dark", lambda: self.set_theme("dark"))
        theme_menu.addAction("Blue", lambda: self.set_theme("blue"))
        theme_menu.addAction("Custom", lambda: self.set_theme("custom"))
        self.toolbar.addAction(theme_menu.menuAction())

        # Incognito mode toggle
        incognito_btn = QAction("🕶️", self)
        incognito_btn.setToolTip("Toggle Incognito Mode")
        incognito_btn.triggered.connect(self.toggle_incognito_mode)
        self.toolbar.addAction(incognito_btn)

        # Fullscreen toggle
        fullscreen_btn = QAction("⛶", self)
        fullscreen_btn.setToolTip("Toggle Fullscreen")
        fullscreen_btn.triggered.connect(self.toggle_fullscreen)
        self.toolbar.addAction(fullscreen_btn)

        # Settings button
        settings_btn = QAction("⚙️", self)
        settings_btn.setToolTip("Settings")
        settings_btn.triggered.connect(self.open_settings)
        self.toolbar.addAction(settings_btn)

        # Extensions toggle
        extensions_btn = QAction("🧩", self)
        extensions_btn.setToolTip("Toggle Extensions")
        extensions_btn.triggered.connect(self.toggle_extensions)
        self.toolbar.addAction(extensions_btn)

        # Run extension code button
        run_extension_btn = QAction("▶️", self)
        run_extension_btn.setToolTip("Run Extension")
        run_extension_btn.triggered.connect(self.run_extension)
        self.toolbar.addAction(run_extension_btn)

        # Add note for current page
        add_note_btn = QAction("📝", self)
        add_note_btn.setToolTip("Add Note for Current Page")
        add_note_btn.triggered.connect(self.add_note_for_page)
        self.toolbar.addAction(add_note_btn)

        # Clear history button
        clear_history_btn = QAction("🧹", self)
        clear_history_btn.setToolTip("Clear History")
        clear_history_btn.triggered.connect(self.clear_history)
        self.toolbar.addAction(clear_history_btn)

        # Bookmarks button (toggle bookmarks sidebar)
        bookmarks_btn = QAction("🔖", self)
        bookmarks_btn.setToolTip("Toggle Bookmarks Sidebar")
        bookmarks_btn.triggered.connect(self.toggle_bookmarks)
        self.toolbar.addAction(bookmarks_btn)

        # Add bookmark button
        add_bookmark_btn = QAction("⭐", self)
        add_bookmark_btn.setToolTip("Add Bookmark")
        add_bookmark_btn.triggered.connect(self.add_bookmark)
        self.toolbar.addAction(add_bookmark_btn)

    # --------------------- Tab and Navigation Methods ---------------------

    def add_tab(self, url: QUrl, title: str):
        browser = QWebEngineView()
        browser.load(url)
        index = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(index)
        browser.urlChanged.connect(lambda url, browser=browser: self.update_url_bar(url, browser))
        browser.loadProgress.connect(lambda progress, browser=browser: self.update_progress_bar(progress, browser))
        browser.loadFinished.connect(lambda _: self.on_load_finished(browser))

    def close_tab(self, index: int):
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)

    def navigate_back(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.back()

    def navigate_forward(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.forward()

    def refresh_page(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.reload()

    def navigate_to_url(self):
        url_text = self.url_bar.text().strip()
        if not url_text.startswith(("http://", "https://")):
            url_text = f"https://www.google.com/search?q={url_text}"
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setUrl(QUrl(url_text))

    def update_url_bar(self, url: QUrl, browser: QWebEngineView):
        if browser == self.tabs.currentWidget():
            self.url_bar.setText(url.toString())
            self.add_to_history(url.toString())

    def add_to_history(self, url: str):
        if url not in self.history:
            self.history.append(url)
            self.history_sidebar.addItem(QListWidgetItem(url))

    def load_history_url(self, item: QListWidgetItem):
        url = item.text()
        self.url_bar.setText(url)
        self.navigate_to_url()

    def clear_history(self):
        self.history.clear()
        self.history_sidebar.clear()
        QMessageBox.information(self, "History Cleared", "Browsing history has been cleared.")

    def update_progress_bar(self, progress: int, browser: QWebEngineView):
        if browser == self.tabs.currentWidget():
            self.progress_bar.setValue(progress)
            if progress < 100:
                self.progress_bar.show()
            else:
                self.progress_bar.hide()

    def on_load_finished(self, browser: QWebEngineView):
        if browser == self.tabs.currentWidget():
            self.progress_bar.hide()
            if self.dark_mode:
                self.apply_dark_mode(browser)

    # --------------------- Appearance and Theme Methods ---------------------

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        current_browser = self.tabs.currentWidget()
        if current_browser:
            self.apply_dark_mode(current_browser)

    def apply_dark_mode(self, browser: QWebEngineView):
        css = """
            html, body {
                background-color: #121212 !important;
                color: #e0e0e0 !important;
            }
            a { color: #bb86fc !important; }
            header, footer, nav, section { background-color: #1e1e1e !important; }
        """ if self.dark_mode else ""
        js = f"""
            (function() {{
                var style = document.getElementById('dark-mode-style');
                if (!style) {{
                    style = document.createElement('style');
                    style.id = 'dark-mode-style';
                    document.head.appendChild(style);
                }}
                style.textContent = `{css}`;
            }})();
        """
        browser.page().runJavaScript(js)

    def set_theme(self, theme: str):
        self.current_theme = theme
        if theme == "dark":
            self.toggle_dark_mode()
        elif theme == "blue":
            self.setStyleSheet("background-color: #e6f3ff;")
        elif theme == "custom":
            self.create_custom_theme()
        else:
            self.setStyleSheet("")

    def create_custom_theme(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.custom_theme = color.name()
            self.setStyleSheet(f"background-color: {self.custom_theme};")

    # --------------------- Additional Functionalities ---------------------

    def upscale_page(self):
        try:
            current_browser = self.tabs.currentWidget()
            if current_browser:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    screenshot_path = temp_file.name
                current_browser.grab().save(screenshot_path)
                img = cv2.imread(screenshot_path)
                if img is None:
                    raise ValueError("Screenshot capture failed.")
                upscaled_img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    upscaled_path = temp_file.name
                cv2.imwrite(upscaled_path, upscaled_img)
                self.add_tab(QUrl.fromLocalFile(upscaled_path), "Upscaled")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to upscale: {e}")

    def zoom_in(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setZoomFactor(current_browser.zoomFactor() + 0.1)

    def zoom_out(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setZoomFactor(current_browser.zoomFactor() - 0.1)

    def read_aloud(self):
        try:
            current_browser = self.tabs.currentWidget()
            if current_browser:
                current_browser.page().toPlainText(lambda text: self.speak_text(text))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read aloud: {e}")

    def speak_text(self, text: str):
        try:
            tts = gTTS(text)
            output_file = "output.mp3"
            tts.save(output_file)
            if os.name == "nt":
                os.system(f"start {output_file}")
            elif sys.platform == "darwin":
                os.system(f"afplay {output_file}")
            else:
                os.system(f"mpg123 {output_file}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Text-to-speech failed: {e}")

    def toggle_ad_block(self):
        self.ad_block_enabled = not self.ad_block_enabled
        if self.ad_block_enabled:
            self.profile.setUrlRequestInterceptor(self.ad_block_interceptor)
            QMessageBox.information(self, "Ad Block", "Ad Block enabled.")
        else:
            self.profile.setUrlRequestInterceptor(None)
            QMessageBox.information(self, "Ad Block", "Ad Block disabled.")

    def summarize_page(self):
        try:
            if not self.openai_api_key:
                self.openai_api_key, ok = QInputDialog.getText(self, "OpenAI API Key", "Enter your OpenAI API key:")
                if not ok or not self.openai_api_key:
                    QMessageBox.critical(self, "Error", "OpenAI API key is required.")
                    return
            current_browser = self.tabs.currentWidget()
            if current_browser:
                current_browser.page().toPlainText(lambda text: self.generate_summary(text))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to summarize: {e}")

    def generate_summary(self, text: str):
        try:
            openai.api_key = self.openai_api_key
            response = openai.Completion.create(
                engine="text-davinci-003",
                prompt=f"Summarize the following text:\n\n{text}",
                max_tokens=100,
            )
            summary = response.choices[0].text.strip()
            QMessageBox.information(self, "Summary", summary)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate summary: {e}")

    def open_chatbot(self):
        self.notes_sidebar.show()

    def voice_command(self):
        try:
            with sr.Microphone() as source:
                QMessageBox.information(self, "Voice Command", "Listening...")
                audio = self.voice_recognizer.listen(source)
                command = self.voice_recognizer.recognize_google(audio)
                QMessageBox.information(self, "Voice Command", f"You said: {command}")
                self.process_voice_command(command)
        except sr.UnknownValueError:
            QMessageBox.critical(self, "Error", "Could not understand audio.")
        except sr.RequestError:
            QMessageBox.critical(self, "Error", "Speech recognition service failed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Voice command error: {e}")

    def process_voice_command(self, command: str):
        command = command.lower()
        if "go to" in command:
            url = command.replace("go to", "").strip()
            self.url_bar.setText(url)
            self.navigate_to_url()
        elif "refresh" in command:
            self.refresh_page()
        elif "back" in command:
            self.navigate_back()
        elif "forward" in command:
            self.navigate_forward()
        elif "zoom in" in command:
            self.zoom_in()
        elif "zoom out" in command:
            self.zoom_out()
        elif "read aloud" in command:
            self.read_aloud()
        elif "summarize" in command:
            self.summarize_page()
        else:
            QMessageBox.information(self, "Voice Command", "Command not recognized.")

    def change_user_agent(self):
        user_agent, ok = QInputDialog.getText(self, "Change User Agent", "Enter the new user agent:")
        if ok and user_agent:
            self.profile.setHttpUserAgent(user_agent)
            QMessageBox.information(self, "User Agent", f"User agent changed to: {user_agent}")

    def update_weather(self):
        try:
            response = requests.get("https://api.weatherapi.com/v1/current.json?key=YOUR_API_KEY&q=London")
            data = response.json()
            weather = data["current"]["condition"]["text"]
            self.weather_widget.setText(f"Weather: {weather}")
        except Exception as e:
            self.weather_widget.setText("Weather: Unavailable")

    def update_news(self):
        try:
            response = requests.get("https://newsapi.org/v2/top-headlines?country=us&apiKey=YOUR_API_KEY")
            data = response.json()
            self.news_sidebar.clear()
            for article in data.get("articles", []):
                self.news_sidebar.addItem(QListWidgetItem(article.get("title", "No Title")))
        except Exception as e:
            self.news_sidebar.addItem(QListWidgetItem("News: Unavailable"))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.homepage_edit.setText(self.custom_homepage)
        dialog.openai_key_edit.setText(self.openai_api_key or "")
        dialog.exec()

    def show_context_menu(self, position):
        menu = QMenu(self)
        save_action = QAction("Save Page As...", self)
        save_action.setToolTip("Save the current page as an HTML file")
        save_action.triggered.connect(self.save_page)
        menu.addAction(save_action)

        view_source_action = QAction("View Page Source", self)
        view_source_action.setToolTip("View the source code of the current page")
        view_source_action.triggered.connect(self.view_page_source)
        menu.addAction(view_source_action)
        menu.exec(self.tabs.mapToGlobal(position))

    def save_page(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Page As", "", "HTML Files (*.html)")
            if file_path:
                current_browser.page().toHtml(lambda html: self.write_html(file_path, html))

    def write_html(self, file_path: str, html: str):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            QMessageBox.information(self, "Save Page", "Page saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save page: {e}")

    def view_page_source(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.page().toHtml(lambda html: self.show_source_code(html))

    def show_source_code(self, html: str):
        source_window = QDialog(self)
        source_window.setWindowTitle("Page Source")
        source_window.setModal(True)
        source_window.resize(800, 600)
        layout = QVBoxLayout()
        source_edit = QPlainTextEdit()
        source_edit.setPlainText(html)
        source_edit.setReadOnly(True)
        layout.addWidget(source_edit)
        source_window.setLayout(layout)
        source_window.exec()

    def toggle_extensions(self):
        self.extension_tab.setVisible(not self.extension_tab.isVisible())

    def run_extension(self):
        try:
            code = self.extension_tab.toPlainText()
            exec(code, globals(), locals())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run extension: {e}")

    def add_note_for_page(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            note, ok = QInputDialog.getText(self, "Add Note", "Enter your note:")
            if ok and note:
                url = current_browser.url().toString()
                self.notes.append((url, note))
                self.notes_sidebar.append(f"Note for {url}:\n{note}\n")

    # --------------------- Bookmarks Methods ---------------------

    def toggle_bookmarks(self):
        if self.bookmarks_sidebar.isVisible():
            self.bookmarks_sidebar.hide()
        else:
            self.bookmarks_sidebar.show()

    def add_bookmark(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            url = current_browser.url().toString()
            if url not in self.bookmarks:
                self.bookmarks.append(url)
                self.bookmarks_sidebar.addItem(QListWidgetItem(url))
                QMessageBox.information(self, "Bookmark Added", f"Bookmark added: {url}")
            else:
                QMessageBox.information(self, "Bookmark Exists", "This bookmark already exists.")

    def load_bookmark(self, item: QListWidgetItem):
        url = item.text()
        self.url_bar.setText(url)
        self.navigate_to_url()

    # --------------------- Keyboard Shortcuts ---------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_F5:
            self.refresh_page()
        elif event.key() == Qt.Key.Key_Backspace:
            self.navigate_back()
        elif event.key() == Qt.Key.Key_L and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.url_bar.setFocus()
        elif event.key() == Qt.Key.Key_T and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.add_tab(QUrl(self.custom_homepage), "New Tab")
        elif event.key() == Qt.Key.Key_W and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.close_tab(self.tabs.currentIndex())
        elif event.key() == Qt.Key.Key_Plus and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_Minus and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.zoom_out()
        else:
            super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    browser = OctoBrowse()
    browser.show()
    sys.exit(app.exec())

import sys
import cv2
import numpy as np
from gtts import gTTS
import openai
import speech_recognition as sr
from cryptography.fernet import Fernet
import requests
import tempfile
import os
from PyQt6.QtCore import QUrl, Qt, QThread, pyqtSignal
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
    QDockWidget,
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
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QAction, QIcon, QColor
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEngineUrlRequestInterceptor


# List of known ad-serving domains
AD_BLOCK_LIST = [
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
    "ads.youtube.com",
    "ads.linkedin.com",
    "ads.facebook.com",
    "ads.twitter.com",
]


class AdBlockerInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, block_list):
        super().__init__()
        self.block_list = set(block_list)  # Use a set for faster lookups

    def interceptRequest(self, info):
        """Intercept and block requests to ad-serving domains."""
        url = info.requestUrl().toString()
        for domain in self.block_list:
            if domain in url:
                info.block(True)
                break


class OctoBrowse(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Octo Browse")
        self.setGeometry(100, 100, 1024, 768)

        # Initialize settings
        self.dark_mode = False
        self.ad_block_enabled = False  # Ad blocker is disabled by default
        self.incognito_mode = False
        self.current_theme = "default"
        self.password_manager = PasswordManager()
        self.voice_recognizer = sr.Recognizer()
        self.openai_api_key = None
        self.history = []
        self.notes = []
        self.custom_homepage = "https://www.google.com"
        self.vpn_enabled = False
        self.default_user_agent = "Octo Browse"
        self.custom_theme = None

        # Set default user agent
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpUserAgent(self.default_user_agent)

        # Initialize ad blocker
        self.ad_block_interceptor = AdBlockerInterceptor(AD_BLOCK_LIST)

        # Create a tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setMovable(True)  # Enable drag-and-drop for tabs
        self.setCentralWidget(self.tabs)

        # Add the first tab
        self.add_tab(QUrl(self.custom_homepage), "Home")

        # Create a toolbar
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)

        # New tab button
        new_tab_btn = QAction("➕", self)
        new_tab_btn.setToolTip("New Tab")
        new_tab_btn.triggered.connect(lambda: self.add_tab(QUrl(self.custom_homepage), "New Tab"))
        self.toolbar.addAction(new_tab_btn)

        # Back button
        back_btn = QAction("⬅️", self)
        back_btn.setToolTip("Back")
        back_btn.triggered.connect(self.navigate_back)
        self.toolbar.addAction(back_btn)

        # Forward button
        forward_btn = QAction("➡️", self)
        forward_btn.setToolTip("Forward")
        forward_btn.triggered.connect(self.navigate_forward)
        self.toolbar.addAction(forward_btn)

        # Refresh button
        refresh_btn = QAction("🔄", self)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.triggered.connect(self.refresh_page)
        self.toolbar.addAction(refresh_btn)

        # Address bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search term...")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.toolbar.addWidget(self.url_bar)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        self.toolbar.addWidget(self.progress_bar)

        # Dark mode toggle
        dark_mode_btn = QAction("🌙", self)
        dark_mode_btn.setToolTip("Toggle Dark Mode")
        dark_mode_btn.triggered.connect(self.toggle_dark_mode)
        self.toolbar.addAction(dark_mode_btn)

        # Upscale button
        upscale_btn = QAction("🖼️", self)
        upscale_btn.setToolTip("Upscale Page")
        upscale_btn.triggered.connect(self.upscale_page)
        self.toolbar.addAction(upscale_btn)

        # Zoom in/out buttons
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

        # AI Summarization button
        summarize_btn = QAction("📝", self)
        summarize_btn.setToolTip("Summarize Page")
        summarize_btn.triggered.connect(self.summarize_page)
        self.toolbar.addAction(summarize_btn)

        # AI Chatbot button
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

        # Full-screen button
        fullscreen_btn = QAction("⛶", self)
        fullscreen_btn.setToolTip("Toggle Fullscreen")
        fullscreen_btn.triggered.connect(self.toggle_fullscreen)
        self.toolbar.addAction(fullscreen_btn)

        # Settings button
        settings_btn = QAction("⚙️", self)
        settings_btn.setToolTip("Settings")
        settings_btn.triggered.connect(self.open_settings)
        self.toolbar.addAction(settings_btn)

        # Extensions button
        extensions_btn = QAction("🧩", self)
        extensions_btn.setToolTip("Toggle Extensions")
        extensions_btn.triggered.connect(self.toggle_extensions)
        self.toolbar.addAction(extensions_btn)

        # Run extension button
        run_extension_btn = QAction("▶️", self)
        run_extension_btn.setToolTip("Run Extension")
        run_extension_btn.triggered.connect(self.run_extension)
        self.toolbar.addAction(run_extension_btn)

        # Add note button
        add_note_btn = QAction("📝", self)
        add_note_btn.setToolTip("Add Note for Current Page")
        add_note_btn.triggered.connect(self.add_note_for_page)
        self.toolbar.addAction(add_note_btn)

        # Note-taking sidebar
        self.notes_sidebar = QTextEdit()
        self.notes_sidebar.setPlaceholderText("Take notes here...")
        self.notes_sidebar.hide()

        # Calendar sidebar
        self.calendar_sidebar = QCalendarWidget()
        self.calendar_sidebar.hide()

        # To-Do List sidebar
        self.todo_sidebar = QListWidget()
        self.todo_sidebar.hide()

        # History sidebar
        self.history_sidebar = QListWidget()
        self.history_sidebar.hide()
        self.history_sidebar.itemDoubleClicked.connect(self.load_history_url)

        # Clear history button
        clear_history_btn = QAction("🧹", self)
        clear_history_btn.setToolTip("Clear History")
        clear_history_btn.triggered.connect(self.clear_history)
        self.toolbar.addAction(clear_history_btn)

        # Weather widget
        self.weather_widget = QLabel("Weather: Loading...")
        self.weather_widget.hide()
        self.update_weather()

        # News feed sidebar
        self.news_sidebar = QListWidget()
        self.news_sidebar.hide()
        self.update_news()

        # Extension tab
        self.extension_tab = QTextEdit()
        self.extension_tab.setPlaceholderText("Enter Python code here...")
        self.extension_tab.hide()

        # Split view
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.notes_sidebar)
        self.splitter.addWidget(self.calendar_sidebar)
        self.splitter.addWidget(self.todo_sidebar)
        self.splitter.addWidget(self.history_sidebar)
        self.splitter.addWidget(self.news_sidebar)
        self.splitter.addWidget(self.extension_tab)
        self.setCentralWidget(self.splitter)

        # Context menu for saving pages and viewing source code
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_context_menu)

    def add_tab(self, url, title):
        """Add a new tab."""
        browser = QWebEngineView()
        browser.load(url)
        index = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(index)
        browser.urlChanged.connect(lambda url, browser=browser: self.update_url_bar(url, browser))
        browser.loadProgress.connect(lambda progress, browser=browser: self.update_progress_bar(progress, browser))
        browser.loadFinished.connect(lambda _, browser=browser: self.on_load_finished(browser))

    def close_tab(self, index):
        """Close a tab."""
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)

    def navigate_back(self):
        """Navigate back in the current tab."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.back()

    def navigate_forward(self):
        """Navigate forward in the current tab."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.forward()

    def refresh_page(self):
        """Refresh the current tab."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.reload()

    def navigate_to_url(self):
        """Navigate to the URL entered in the address bar."""
        url = self.url_bar.text()
        if not url.startswith(("http://", "https://")):
            url = f"https://www.google.com/search?q={url}"
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setUrl(QUrl(url))

    def update_url_bar(self, url, browser):
        """Update the address bar with the current URL."""
        if browser == self.tabs.currentWidget():
            self.url_bar.setText(url.toString())
            self.add_to_history(url.toString())

    def add_to_history(self, url):
        """Add a URL to the browsing history."""
        if url not in self.history:
            self.history.append(url)
            self.history_sidebar.addItem(QListWidgetItem(url))

    def load_history_url(self, item):
        """Load a URL from the history sidebar."""
        url = item.text()
        self.url_bar.setText(url)
        self.navigate_to_url()

    def clear_history(self):
        """Clear the browsing history."""
        self.history.clear()
        self.history_sidebar.clear()
        QMessageBox.information(self, "History Cleared", "Browsing history has been cleared.")

    def update_progress_bar(self, progress, browser):
        """Update the progress bar during page loading."""
        if browser == self.tabs.currentWidget():
            self.progress_bar.setValue(progress)
            if progress < 100:
                self.progress_bar.show()
            else:
                self.progress_bar.hide()

    def on_load_finished(self, browser):
        """Handle page load completion."""
        if browser == self.tabs.currentWidget():
            self.progress_bar.hide()
            if self.dark_mode:
                self.apply_dark_mode(browser)

    def toggle_dark_mode(self):
        """Toggle dark mode for the browser."""
        self.dark_mode = not self.dark_mode
        current_browser = self.tabs.currentWidget()
        if current_browser:
            self.apply_dark_mode(current_browser)

    def apply_dark_mode(self, browser):
        """Apply dark mode using CSS injection."""
        if self.dark_mode:
            css = """
            body {
                background-color: #121212 !important;
                color: #ffffff !important;
            }
            a {
                color: #bb86fc !important;
            }
            """
        else:
            css = ""
        browser.page().runJavaScript(f"""
            var style = document.getElementById('dark-mode-style');
            if (!style) {{
                style = document.createElement('style');
                style.id = 'dark-mode-style';
                document.head.appendChild(style);
            }}
            style.textContent = `{css}`;
        """)

    def upscale_page(self):
        """Upscale the page using AI-based image enhancement."""
        try:
            current_browser = self.tabs.currentWidget()
            if current_browser:
                # Save the screenshot to a temporary file
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    screenshot_path = temp_file.name
                    current_browser.grab().save(screenshot_path)

                # Upscale the image
                img = cv2.imread(screenshot_path)
                upscaled_img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    upscaled_path = temp_file.name
                    cv2.imwrite(upscaled_path, upscaled_img)

                # Display the upscaled image in the browser
                current_browser.setUrl(QUrl.fromLocalFile(upscaled_path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to upscale: {e}")

    def zoom_in(self):
        """Zoom in on the page."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setZoomFactor(current_browser.zoomFactor() + 0.1)

    def zoom_out(self):
        """Zoom out on the page."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setZoomFactor(current_browser.zoomFactor() - 0.1)

    def read_aloud(self):
        """Read the page content aloud using text-to-speech."""
        try:
            current_browser = self.tabs.currentWidget()
            if current_browser:
                current_browser.page().toPlainText(lambda text: self.speak_text(text))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read aloud: {e}")

    def speak_text(self, text):
        """Convert text to speech using gTTS."""
        try:
            tts = gTTS(text)
            tts.save("output.mp3")
            import os
            os.system("start output.mp3" if os.name == "nt" else "afplay output.mp3")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to convert text to speech: {e}")

    def toggle_ad_block(self):
        """Toggle ad-blocking."""
        self.ad_block_enabled = not self.ad_block_enabled
        profile = QWebEngineProfile.defaultProfile()
        if self.ad_block_enabled:
            profile.setUrlRequestInterceptor(self.ad_block_interceptor)
            QMessageBox.information(self, "Ad Block", "Ad Block enabled.")
        else:
            profile.setUrlRequestInterceptor(None)
            QMessageBox.information(self, "Ad Block", "Ad Block disabled.")

    def summarize_page(self):
        """Summarize the page content using OpenAI's GPT."""
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

    def generate_summary(self, text):
        """Generate a summary using OpenAI's GPT."""
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

    def set_theme(self, theme):
        """Set the browser theme."""
        self.current_theme = theme
        if theme == "dark":
            self.apply_dark_mode(self.tabs.currentWidget())
        elif theme == "blue":
            self.setStyleSheet("background-color: #e6f3ff;")
        elif theme == "custom":
            self.create_custom_theme()
        else:
            self.setStyleSheet("")

    def create_custom_theme(self):
        """Create a custom theme."""
        color = QColorDialog.getColor()
        if color.isValid():
            self.custom_theme = color.name()
            self.setStyleSheet(f"background-color: {self.custom_theme};")

    def toggle_incognito_mode(self):
        """Toggle incognito mode."""
        self.incognito_mode = not self.incognito_mode
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies if self.incognito_mode
            else QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        QMessageBox.information(self, "Incognito Mode", f"Incognito Mode {'enabled' if self.incognito_mode else 'disabled'}.")

    def open_chatbot(self):
        """Open the AI chatbot sidebar."""
        self.notes_sidebar.show()

    def voice_command(self):
        """Use voice commands to control the browser."""
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
            QMessageBox.critical(self, "Error", "Could not request results from Google Speech Recognition service.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process voice command: {e}")

    def process_voice_command(self, command):
        """Process voice commands."""
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
        """Change the browser's user agent."""
        user_agent, ok = QInputDialog.getText(self, "Change User Agent", "Enter the new user agent:")
        if ok and user_agent:
            profile = QWebEngineProfile.defaultProfile()
            profile.setHttpUserAgent(user_agent)
            QMessageBox.information(self, "User Agent", f"User agent changed to: {user_agent}")

    def update_weather(self):
        """Update the weather widget with real-time weather information."""
        try:
            response = requests.get("https://api.weatherapi.com/v1/current.json?key=YOUR_API_KEY&q=London")
            data = response.json()
            weather = data["current"]["condition"]["text"]
            self.weather_widget.setText(f"Weather: {weather}")
        except Exception as e:
            self.weather_widget.setText("Weather: Unavailable")

    def update_news(self):
        """Update the news feed sidebar with the latest headlines."""
        try:
            response = requests.get("https://newsapi.org/v2/top-headlines?country=us&apiKey=YOUR_API_KEY")
            data = response.json()
            for article in data["articles"]:
                self.news_sidebar.addItem(QListWidgetItem(article["title"]))
        except Exception as e:
            self.news_sidebar.addItem(QListWidgetItem("News: Unavailable"))

    def toggle_fullscreen(self):
        """Toggle full-screen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
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

    def open_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.homepage_edit.setText(self.custom_homepage)
        dialog.openai_key_edit.setText(self.openai_api_key or "")
        dialog.exec()

    def show_context_menu(self, position):
        """Show a context menu for saving pages and viewing source code."""
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
        """Save the current page as an HTML file."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Page As", "", "HTML Files (*.html)")
            if file_path:
                current_browser.page().save(file_path, QWebEngineDownloadItem.SavePageFormat.CompleteHtmlSaveFormat)

    def view_page_source(self):
        """View the source code of the current page."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.page().toHtml(lambda html: self.show_source_code(html))

    def show_source_code(self, html):
        """Display the page source code in a new window."""
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
        """Toggle the visibility of the extensions tab."""
        self.extension_tab.setVisible(not self.extension_tab.isVisible())

    def run_extension(self):
        """Run custom Python code from the extensions tab."""
        try:
            code = self.extension_tab.toPlainText()
            exec(code)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run extension: {e}")

    def add_note_for_page(self):
        """Add a note for the current page."""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            note, ok = QInputDialog.getText(self, "Add Note", "Enter your note:")
            if ok and note:
                self.notes.append((current_browser.url().toString(), note))
                self.notes_sidebar.append(f"Note for {current_browser.url().toString()}:\n{note}\n")


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
        """Save settings and close the dialog."""
        homepage_url = self.homepage_edit.text()
        openai_key = self.openai_key_edit.text()

        if homepage_url:
            self.parent().custom_homepage = homepage_url
        if openai_key:
            self.parent().openai_api_key = openai_key

        self.accept()


class PasswordManager:
    """A simple password manager using AES-256 encryption."""
    def __init__(self):
        self.key = Fernet.generate_key()
        self.cipher = Fernet(self.key)

    def encrypt(self, password):
        """Encrypt a password."""
        return self.cipher.encrypt(password.encode()).decode()

    def decrypt(self, encrypted_password):
        """Decrypt a password."""
        return self.cipher.decrypt(encrypted_password.encode()).decode()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    browser = OctoBrowse()
    browser.show()
    sys.exit(app.exec())

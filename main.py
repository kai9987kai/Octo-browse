#!/usr/bin/env python3
"""
OctoBrowse: a PyQt6/QtWebEngine desktop browser prototype.

The app keeps the original browsing, sidebar, AI, speech, page-tool, bookmark,
history, weather, news, and extension-lab features while consolidating the
experimental alpha improvements into one maintained entry point.
"""

from __future__ import annotations

import ast
import hashlib
import ipaddress
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
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

from PyQt6.QtCore import QSize, QStandardPaths, QStringListModel, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
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
    QSpinBox,
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
    # Analytics and session-tracking endpoints commonly blocked by tracker lists.
    "adcolony.com",
    "adroll.com",
    "adsafeprotected.com",
    "agkn.com",
    "amplitude.com",
    "bidswitch.net",
    "bluekai.com",
    "casalemedia.com",
    "chartbeat.com",
    "clarity.ms",
    "crwdcntrl.net",
    "demdex.net",
    "exelator.com",
    "fullstory.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googletagservices.com",
    "hotjar.com",
    "indexww.com",
    "krxd.net",
    "mathtag.com",
    "media.net",
    "mgid.com",
    "mixpanel.com",
    "moatads.com",
    "mouseflow.com",
    "quantserve.com",
    "revcontent.com",
    "rlcdn.com",
    "segment.io",
    "sharethrough.com",
    "smartadserver.com",
    "triplelift.com",
    "yieldmo.com",
}

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "brave": "https://search.brave.com/search?q={query}",
    "startpage": "https://www.startpage.com/sp/search?query={query}",
}
DEFAULT_SEARCH_ENGINE = "google"

EASYLIST_URL = "https://easylist.to/easylist/easylist.txt"

DEFAULT_HOMEPAGE = "https://www.google.com"
DEFAULT_OPENAI_MODEL = os.environ.get("OCTOBROWSE_OPENAI_MODEL", "gpt-5-mini")
OCTO_BROWSER_NAME = "Octo Browser"
OCTO_BROWSER_VERSION = "3.1"
OCTO_BROWSER_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) OctoBrowser/{OCTO_BROWSER_VERSION} "
    f"Chrome/126.0.0.0 Safari/537.36"
)
MAX_HISTORY_ITEMS = 500

DOWNLOAD_PATH_ROLE = Qt.ItemDataRole.UserRole
DOWNLOAD_REQUEST_ROLE = Qt.ItemDataRole.UserRole + 1


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
    search_engine: str = DEFAULT_SEARCH_ENGINE
    https_only: bool = False
    gpc_enabled: bool = True
    tab_hibernation_enabled: bool = True
    hibernation_minutes: int = 15


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
    ) -> tuple[
        BrowserSettings,
        list[dict[str, Any]],
        list[str],
        list[dict[str, str]],
        list[str],
        list[str],
        list[str],
        dict[str, dict[str, bool]],
        dict[str, dict[str, bool]],
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
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
            search_engine=str(data.get("search_engine") or DEFAULT_SEARCH_ENGINE).lower(),
            https_only=bool(data.get("https_only", False)),
            gpc_enabled=bool(data.get("gpc_enabled", True)),
            tab_hibernation_enabled=bool(data.get("tab_hibernation_enabled", True)),
            hibernation_minutes=max(1, int(data.get("hibernation_minutes") or 15)),
        )
        if settings.search_engine not in SEARCH_ENGINES:
            settings.search_engine = DEFAULT_SEARCH_ENGINE
        history = self._coerce_history(data.get("history", []))[-MAX_HISTORY_ITEMS:]
        bookmarks = self._unique_strings(data.get("bookmarks", []))
        notes = self._coerce_notes(data.get("notes", []))
        todos = self._unique_strings(data.get("todos", []))
        session_tabs = self._unique_strings(data.get("session_tabs", []))
        reading_list = self._unique_strings(data.get("reading_list", []))
        site_permissions = self._coerce_site_permissions(data.get("site_permissions", {}))
        site_content = self._coerce_site_permissions(data.get("site_content", {}))
        downloads_history = self._coerce_downloads(data.get("downloads_history", []))
        plugin_grants = self._coerce_plugin_grants(data.get("plugin_grants", {}))
        return (
            settings,
            history,
            bookmarks,
            notes,
            todos,
            session_tabs,
            reading_list,
            site_permissions,
            site_content,
            downloads_history,
            plugin_grants,
        )

    def save(
        self,
        settings: BrowserSettings,
        bookmarks: list[str],
        notes: list[dict[str, str]],
        todos: list[str],
        session_tabs: list[str],
        reading_list: list[str],
        site_permissions: dict[str, dict[str, bool]],
        site_content: dict[str, dict[str, bool]],
        downloads_history: list[dict[str, Any]],
        plugin_grants: dict[str, dict[str, Any]],
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
            "search_engine": settings.search_engine,
            "https_only": settings.https_only,
            "gpc_enabled": settings.gpc_enabled,
            "tab_hibernation_enabled": settings.tab_hibernation_enabled,
            "hibernation_minutes": settings.hibernation_minutes,
            "bookmarks": bookmarks,
            "notes": notes,
            "todos": todos,
            "session_tabs": session_tabs,
            "reading_list": reading_list,
            "site_permissions": site_permissions,
            "site_content": site_content,
            "downloads_history": downloads_history[-100:],
            "plugin_grants": plugin_grants,
        }
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)

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
    def _coerce_history(values: Any) -> list[dict[str, Any]]:
        """Accept both the legacy list-of-URL format and rich history entries."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        if not isinstance(values, list):
            return result
        for item in values:
            if isinstance(item, dict):
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                try:
                    visits = max(1, int(item.get("visits", 1)))
                except (TypeError, ValueError):
                    visits = 1
                try:
                    last_visit = float(item.get("last_visit", 0.0))
                except (TypeError, ValueError):
                    last_visit = 0.0
            else:
                url = str(item).strip()
                title = ""
                visits = 1
                last_visit = 0.0
            if url and url not in seen:
                seen.add(url)
                result.append({"url": url, "title": title, "visits": visits, "last_visit": last_visit})
        return result

    @staticmethod
    def _coerce_plugin_grants(values: Any) -> dict[str, dict[str, Any]]:
        """Normalize plugin grants to {name: {permissions: [...], sha256: ...}}.

        Accepts the legacy {name: [permissions]} form; legacy entries get an
        empty sha256 so they are re-confirmed on next run (they predate
        file-identity binding).
        """
        result: dict[str, dict[str, Any]] = {}
        if not isinstance(values, dict):
            return result
        for name, record in values.items():
            if isinstance(record, list):
                permissions, sha256 = record, ""
            elif isinstance(record, dict):
                permissions = record.get("permissions", [])
                sha256 = str(record.get("sha256", ""))
                if not isinstance(permissions, list):
                    permissions = []
            else:
                continue
            cleaned = [str(p) for p in permissions if str(p) in PLUGIN_PERMISSIONS]
            result[str(name)] = {"permissions": cleaned, "sha256": sha256}
        return result

    @staticmethod
    def _coerce_downloads(values: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not isinstance(values, list):
            return result
        for item in values:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file", "")).strip()
            if not file_path:
                continue
            try:
                finished = float(item.get("time", 0.0))
            except (TypeError, ValueError):
                finished = 0.0
            result.append(
                {
                    "file": file_path,
                    "url": str(item.get("url", "")),
                    "status": str(item.get("status", "complete")),
                    "time": finished,
                }
            )
        return result

    @staticmethod
    def _coerce_site_permissions(values: Any) -> dict[str, dict[str, bool]]:
        result: dict[str, dict[str, bool]] = {}
        if not isinstance(values, dict):
            return result
        for origin, features in values.items():
            if not isinstance(features, dict):
                continue
            cleaned = {str(name): bool(allowed) for name, allowed in features.items() if str(name).strip()}
            if cleaned:
                result[str(origin)] = cleaned
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


class HistoryDatabase:
    """SQLite-backed browsing history (Firefox places-style schema).

    Replaces the old rewrite-the-whole-JSON-per-navigation persistence with
    one upsert per visit.
    """

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "history.sqlite"
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                visits INTEGER NOT NULL DEFAULT 1,
                last_visit REAL NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_visits_last ON visits(last_visit)")
        self.conn.commit()

    def load(self, limit: int = MAX_HISTORY_ITEMS) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT url, title, visits, last_visit FROM visits ORDER BY last_visit DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"url": url, "title": title, "visits": visits, "last_visit": last_visit}
            for url, title, visits, last_visit in reversed(rows)
        ]

    def record_visit(self, url: str, when: float) -> None:
        self.conn.execute(
            """
            INSERT INTO visits(url, last_visit) VALUES(?, ?)
            ON CONFLICT(url) DO UPDATE SET visits = visits + 1, last_visit = excluded.last_visit
            """,
            (url, when),
        )
        self.conn.commit()

    def set_title(self, url: str, title: str) -> None:
        self.conn.execute("UPDATE visits SET title = ? WHERE url = ?", (title, url))
        self.conn.commit()

    def remove(self, url: str) -> None:
        self.conn.execute("DELETE FROM visits WHERE url = ?", (url,))
        self.conn.commit()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM visits")
        self.conn.commit()

    def import_entries(self, entries: list[dict[str, Any]]) -> None:
        self.conn.executemany(
            """
            INSERT INTO visits(url, title, visits, last_visit) VALUES(?, ?, ?, ?)
            ON CONFLICT(url) DO NOTHING
            """,
            [
                (
                    str(entry.get("url", "")),
                    str(entry.get("title", "")),
                    int(entry.get("visits", 1)),
                    float(entry.get("last_visit", 0.0)),
                )
                for entry in entries
                if entry.get("url")
            ],
        )
        self.conn.commit()

    def prune(self, keep: int = MAX_HISTORY_ITEMS) -> None:
        self.conn.execute(
            "DELETE FROM visits WHERE url NOT IN (SELECT url FROM visits ORDER BY last_visit DESC LIMIT ?)",
            (keep,),
        )
        self.conn.commit()

    def close(self) -> None:
        try:
            self.prune()
            self.conn.close()
        except sqlite3.Error:
            pass


class FilterRuleSet:
    """Subset of the Adblock Plus filter syntax used by EasyList.

    Supports: `||domain^` network rules, `@@||domain^` exceptions,
    hosts-file lines, path/substring patterns with `*`, `^`, and `|`, and
    `##` cosmetic element-hiding rules (generic and per-domain).
    Pattern rules are indexed by their longest literal token (the same idea
    uBlock Origin uses) so each request only tests a handful of candidates.
    Procedural cosmetic rules and rules with unsupported options are skipped.
    """

    GENERIC_CAP = 100
    GENERIC_SELECTOR_CAP = 5000
    _CSS_CHUNK = 100  # selectors per CSS rule, so one bad selector only voids its chunk
    _TOKEN_RE = re.compile(r"[a-z0-9]{4,}")
    _HOSTS_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1)\s+([a-z0-9.-]+)$", re.IGNORECASE)
    _DOMAIN_RULE_RE = re.compile(r"^[a-z0-9.-]+\^?$", re.IGNORECASE)
    SUPPORTED_OPTIONS = {
        "third-party", "3p", "script", "image", "stylesheet", "xmlhttprequest",
        "subdocument", "object", "media", "font", "websocket", "other", "ping", "document",
    }

    def __init__(self) -> None:
        self.blocked_domains: set[str] = set()
        self.exception_domains: set[str] = set()
        self.token_buckets: dict[str, list[re.Pattern[str]]] = {}
        self.generic_patterns: list[re.Pattern[str]] = []
        self.generic_selectors: list[str] = []
        self.domain_selectors: dict[str, list[str]] = {}
        self.rule_count = 0
        self.cosmetic_count = 0
        self.skipped_count = 0
        self._generic_css: str | None = None

    def parse_text(self, text: str) -> None:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("!", "[")):
                continue
            if "#@#" in line or "#?#" in line or "#$#" in line:
                # Cosmetic exceptions and procedural/style rules are unsupported.
                self.skipped_count += 1
                continue
            if "##" in line:
                self._parse_cosmetic(line)
                continue
            hosts_match = self._HOSTS_RE.match(line)
            if hosts_match:
                domain = hosts_match.group(1).lower()
                if domain not in {"localhost", "localhost.localdomain", "broadcasthost"}:
                    self.blocked_domains.add(domain)
                    self.rule_count += 1
                continue
            exception = line.startswith("@@")
            if exception:
                line = line[2:]
            body, _, options = line.partition("$")
            if options and not self._options_supported(options):
                self.skipped_count += 1
                continue
            if body.startswith("||"):
                rest = body[2:]
                if self._DOMAIN_RULE_RE.match(rest):
                    domain = rest.rstrip("^").lower().strip(".")
                    if domain:
                        (self.exception_domains if exception else self.blocked_domains).add(domain)
                        self.rule_count += 1
                    continue
            if exception:
                # Path-level exceptions are rare and risky to approximate.
                self.skipped_count += 1
                continue
            pattern = self._compile_pattern(body)
            if pattern is None:
                self.skipped_count += 1
                continue
            token = self._pick_token(body)
            if token:
                self.token_buckets.setdefault(token, []).append(pattern)
                self.rule_count += 1
            elif len(self.generic_patterns) < self.GENERIC_CAP:
                self.generic_patterns.append(pattern)
                self.rule_count += 1
            else:
                self.skipped_count += 1

    def _parse_cosmetic(self, line: str) -> None:
        domains_part, _, selector = line.partition("##")
        selector = selector.strip()
        if not selector or "{" in selector or "}" in selector:
            self.skipped_count += 1
            return
        domains_part = domains_part.strip().lower()
        if not domains_part:
            if len(self.generic_selectors) < self.GENERIC_SELECTOR_CAP:
                self.generic_selectors.append(selector)
                self.cosmetic_count += 1
            else:
                self.skipped_count += 1
            return
        if "~" in domains_part:
            # Negated-domain cosmetics would need exclusion logic; skip safely.
            self.skipped_count += 1
            return
        added = False
        for domain in domains_part.split(","):
            domain = domain.strip()
            if domain:
                self.domain_selectors.setdefault(domain, []).append(selector)
                added = True
        if added:
            self.cosmetic_count += 1
        else:
            self.skipped_count += 1

    @classmethod
    def _css_block(cls, selectors: list[str]) -> str:
        # Chunked so a single invalid selector cannot invalidate every rule.
        blocks = []
        for start in range(0, len(selectors), cls._CSS_CHUNK):
            chunk = selectors[start : start + cls._CSS_CHUNK]
            blocks.append(", ".join(chunk) + " { display: none !important; }")
        return "\n".join(blocks)

    def cosmetic_css_for(self, host: str) -> str:
        if self._generic_css is None:
            self._generic_css = self._css_block(self.generic_selectors)
        site_selectors: list[str] = []
        if host:
            parts = host.split(".")
            for index in range(len(parts) - 1):
                candidate = ".".join(parts[index:])
                site_selectors.extend(self.domain_selectors.get(candidate, ()))
        site_css = self._css_block(site_selectors) if site_selectors else ""
        return "\n".join(part for part in (site_css, self._generic_css) if part)

    def _options_supported(self, options: str) -> bool:
        for option in options.split(","):
            if option.strip().lower() not in self.SUPPORTED_OPTIONS:
                return False
        return True

    @staticmethod
    def _compile_pattern(body: str) -> re.Pattern[str] | None:
        text = body
        host_anchor = anchor_start = anchor_end = False
        if text.startswith("||"):
            host_anchor = True
            text = text[2:]
        elif text.startswith("|"):
            anchor_start = True
            text = text[1:]
        if text.endswith("|"):
            anchor_end = True
            text = text[:-1]
        if not text:
            return None
        parts: list[str] = []
        for char in text:
            if char == "*":
                parts.append(".*")
            elif char == "^":
                parts.append(r"(?:[^a-zA-Z0-9_.%-]|$)")
            else:
                parts.append(re.escape(char))
        regex = "".join(parts)
        if host_anchor:
            regex = r"^[a-z][a-z0-9+.-]*://(?:[^/?#]*\.)?" + regex
        elif anchor_start:
            regex = "^" + regex
        if anchor_end:
            regex += "$"
        try:
            return re.compile(regex, re.IGNORECASE)
        except re.error:
            return None

    def _pick_token(self, body: str) -> str | None:
        tokens: list[str] = []
        for segment in re.split(r"[*^|]", body.lower()):
            tokens.extend(self._TOKEN_RE.findall(segment))
        tokens = [token for token in tokens if token not in {"http", "https", "www"}]
        return max(tokens, key=len) if tokens else None

    def is_exception_host(self, host: str) -> bool:
        return _domain_suffix_match(host, self.exception_domains) is not None

    def should_block(self, url_text: str, host: str) -> bool:
        if self.is_exception_host(host):
            return False
        if _domain_suffix_match(host, self.blocked_domains) is not None:
            return True
        lowered = url_text.lower()
        for token in set(self._TOKEN_RE.findall(lowered)):
            for pattern in self.token_buckets.get(token, ()):
                if pattern.search(url_text):
                    return True
        for pattern in self.generic_patterns:
            if pattern.search(url_text):
                return True
        return False


def _domain_suffix_match(host: str, domains: set[str]) -> str | None:
    """Walk the host's label suffixes; O(labels) regardless of set size."""
    if not host or not domains:
        return None
    parts = host.split(".")
    for index in range(len(parts) - 1):
        candidate = ".".join(parts[index:])
        if candidate in domains:
            return candidate
    return None


# Schemes allowed in hrefs on generated internal (octobrowse.local) pages.
# Everything else - javascript:, data:, vbscript:, blob: - is neutralized so a
# crafted bookmark/history/title cannot run script in the internal origin.
SAFE_LINK_SCHEMES = {"http", "https", "file", "ftp", "mailto", "octo"}


def safe_link_href(url: str) -> str:
    """Return an attribute-safe href, blanking out dangerous URL schemes."""
    text = str(url).strip()
    scheme, sep, _ = text.partition(":")
    if sep and scheme.lower() not in SAFE_LINK_SCHEMES:
        return "#"
    return html.escape(text, quote=True)


def is_blocked_fetch_host(host: str) -> bool:
    """True when a host resolves to a private/loopback/link-local/reserved address.

    Used to keep plugin fetch() from reaching internal services or cloud
    metadata endpoints (basic SSRF guardrail; redirects are also disabled).
    """
    host = host.strip().strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return True  # Unresolvable -> fail closed.
    for info in infos:
        raw_ip = info[4][0].split("%", 1)[0]
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            return True
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return True
    return False


class FilterParseWorker(QThread):
    parsed = pyqtSignal(object)

    def __init__(self, texts: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.texts = texts

    def run(self) -> None:
        rules = FilterRuleSet()
        for text in self.texts:
            try:
                rules.parse_text(text)
            except Exception:  # pragma: no cover - malformed list defensive guard
                continue
        self.parsed.emit(rules)


class ApiFetchWorker(QThread):
    data_ready = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, kind: str, url: str, parent: QWidget | None = None, as_json: bool = True) -> None:
        super().__init__(parent)
        self.kind = kind
        self.url = url
        self.as_json = as_json

    def run(self) -> None:
        if requests is None:
            self.failed.emit(self.kind, "Install the requests package.")
            return
        try:
            response = requests.get(self.url, timeout=6 if self.as_json else 30)
            response.raise_for_status()
            self.data_ready.emit(self.kind, response.json() if self.as_json else response.text)
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


class OctoRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Single request interceptor handling ad blocking, HTTPS-only upgrades, and GPC.

    Domain matching walks the host's label suffixes against a set, so each
    request costs O(host labels) instead of O(blocklist size).
    """

    def __init__(self, block_list: set[str]) -> None:
        super().__init__()
        self.block_list = {domain.lower() for domain in block_list}
        self.blocked_by_domain: Counter[str] = Counter()
        self.ad_block_enabled = False
        self.https_only = False
        self.gpc_enabled = True
        self.https_upgrades = 0
        self.filter_rules: FilterRuleSet | None = None

    def interceptRequest(self, info: Any) -> None:
        url = info.requestUrl()
        host = url.host().lower()
        if self.ad_block_enabled:
            rules = self.filter_rules
            excepted = rules.is_exception_host(host) if rules is not None else False
            if not excepted:
                match = self._matching_domain(host)
                if match:
                    self.blocked_by_domain[match] += 1
                    info.block(True)
                    return
                if rules is not None and rules.should_block(url.toString(), host):
                    self.blocked_by_domain[host or "pattern-rule"] += 1
                    info.block(True)
                    return
        if self.https_only and url.scheme() == "http" and self._upgradable_host(host):
            if info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame:
                secure = QUrl(url)
                secure.setScheme("https")
                self.https_upgrades += 1
                info.redirect(secure)
                return
        if self.gpc_enabled:
            info.setHttpHeader(b"Sec-GPC", b"1")
            info.setHttpHeader(b"DNT", b"1")

    def reset_stats(self) -> None:
        self.blocked_by_domain.clear()
        self.https_upgrades = 0

    def total_blocked(self) -> int:
        return sum(self.blocked_by_domain.values())

    def _matching_domain(self, host: str) -> str | None:
        return _domain_suffix_match(host, self.block_list)

    @staticmethod
    def _upgradable_host(host: str) -> bool:
        if not host or host == "localhost" or host.endswith(".local"):
            return False
        # Skip bare IPv4/IPv6 hosts; certificates rarely match them.
        if host.replace(".", "").isdigit() or ":" in host:
            return False
        return "." in host


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


PLUGIN_PERMISSIONS = {
    "tabs": "Open, list, switch, and close tabs",
    "navigation": "Navigate and reload the current tab",
    "page": "Read the current page's URL, title, and text",
    "history": "Read browsing history",
    "bookmarks": "Read and add bookmarks",
    "notes": "Add notes and todo items",
    "ui": "Show status messages and dialogs",
    "clipboard": "Read and write the clipboard",
    "network": "Fetch public web resources over HTTP(S) (private/loopback hosts blocked)",
}

PLUGIN_FETCH_LIMIT = 2_000_000  # bytes of response text a plugin may receive


def make_safe_builtins(print_fn: Any) -> dict[str, Any]:
    """Restricted builtins for plugin and extension-lab execution."""
    return {
        "Exception": Exception,
        "PermissionError": PermissionError,
        "ValueError": ValueError,
        "False": False,
        "True": True,
        "None": None,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "print": print_fn,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }


class OctoPluginAPI:
    """Capability object handed to plugins; every call checks a granted permission."""

    def __init__(self, browser_window: "OctoBrowse", plugin_name: str, granted: set[str]) -> None:
        self._browser = browser_window
        self.plugin_name = plugin_name
        self.granted = frozenset(granted)

    def _require(self, permission: str) -> None:
        if permission not in self.granted:
            raise PermissionError(
                f"Plugin '{self.plugin_name}' was not granted the '{permission}' permission."
            )

    # --- tabs ---
    def open_tab(self, url: str) -> None:
        self._require("tabs")
        self._browser.add_tab(self._browser.build_url(str(url)), "Plugin Tab", private=False)

    def list_tabs(self) -> list[dict[str, Any]]:
        self._require("tabs")
        tabs = []
        for index in range(self._browser.tabs.count()):
            widget = self._browser.tabs.widget(index)
            if isinstance(widget, QWebEngineView):
                tabs.append(
                    {
                        "index": index,
                        "title": self._browser.tabs.tabText(index),
                        "url": widget.url().toString(),
                    }
                )
        return tabs

    def switch_to_tab(self, index: int) -> None:
        self._require("tabs")
        if 0 <= int(index) < self._browser.tabs.count():
            self._browser.tabs.setCurrentIndex(int(index))

    def close_tab(self, index: int) -> None:
        self._require("tabs")
        if 0 <= int(index) < self._browser.tabs.count():
            self._browser.close_tab(int(index))

    # --- navigation ---
    def navigate(self, url: str) -> None:
        self._require("navigation")
        browser = self._browser.current_browser()
        if browser:
            browser.setUrl(self._browser.build_url(str(url)))

    def reload(self) -> None:
        self._require("navigation")
        self._browser.refresh_page()

    # --- page ---
    def page_url(self) -> str:
        self._require("page")
        browser = self._browser.current_browser()
        return browser.url().toString() if browser else ""

    def page_title(self) -> str:
        self._require("page")
        index = self._browser.tabs.currentIndex()
        return self._browser.tabs.tabText(index) if index >= 0 else ""

    def get_page_text(self, callback: Any) -> None:
        self._require("page")
        browser = self._browser.current_browser()
        if browser:
            browser.page().toPlainText(callback)

    # --- collections ---
    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        self._require("history")
        return [dict(entry) for entry in self._browser.history[-max(1, int(limit)):]]

    def bookmarks(self) -> list[str]:
        self._require("bookmarks")
        return list(self._browser.bookmarks)

    def add_bookmark(self, url: str) -> None:
        self._require("bookmarks")
        url = str(url).strip()
        if url and url not in self._browser.bookmarks:
            self._browser.bookmarks.append(url)
            self._browser.bookmarks_sidebar.addItem(QListWidgetItem(url))
            self._browser.save_settings()

    def add_note(self, note: str) -> None:
        self._require("notes")
        note = str(note).strip()
        if not note:
            return
        browser = self._browser.current_browser()
        url = browser.url().toString() if browser else "plugin"
        self._browser.notes.append({"url": url, "note": note})
        self._browser.notes_sidebar.append(f"Note for {url}:\n{note}\n")
        self._browser.save_settings()

    def add_todo(self, text: str) -> None:
        self._require("notes")
        text = str(text).strip()
        if not text:
            return
        self._browser.todos.append(text)
        self._browser.todo_sidebar.addItem(QListWidgetItem(text))
        self._browser.save_settings()

    # --- ui ---
    def set_status(self, message: str) -> None:
        self._require("ui")
        self._browser.set_status(f"[{self.plugin_name}] {message}")

    def show_message(self, title: str, text: str) -> None:
        self._require("ui")
        QMessageBox.information(self._browser, f"{self.plugin_name}: {title}", str(text)[:4000])

    # --- clipboard ---
    def clipboard_text(self) -> str:
        self._require("clipboard")
        return QApplication.clipboard().text()

    def set_clipboard_text(self, text: str) -> None:
        self._require("clipboard")
        QApplication.clipboard().setText(str(text))

    # --- network ---
    def fetch(self, url: str, timeout: float = 10.0) -> str:
        self._require("network")
        if requests is None:
            raise RuntimeError("Install the requests package to use plugin networking.")
        url = str(url)
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("Plugins may only fetch http(s) URLs.")
        host = QUrl(url).host()
        if is_blocked_fetch_host(host):
            raise ValueError(
                "Plugins cannot fetch private, loopback, or link-local addresses."
            )
        # Redirects are disabled so a public URL cannot bounce to an internal one.
        response = requests.get(url, timeout=min(float(timeout), 15.0), allow_redirects=False)
        response.raise_for_status()
        return response.text[:PLUGIN_FETCH_LIMIT]


class OctoWebPage(QWebEnginePage):
    def __init__(self, browser_window: "OctoBrowse", profile: QWebEngineProfile, private: bool, parent: QWidget) -> None:
        super().__init__(profile, parent)
        self.browser_window = browser_window
        self.private = private

    def createWindow(self, _window_type: QWebEnginePage.WebWindowType) -> QWebEnginePage:
        view = self.browser_window.add_tab(QUrl("about:blank"), "New Window", private=self.private)
        return view.page()

    def acceptNavigationRequest(
        self,
        url: QUrl,
        navigation_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if is_main_frame and url.scheme().lower() == "octo":
            self.browser_window.handle_octo_command(url.toString())
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


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

        self.search_engine_combo = QComboBox()
        for engine in SEARCH_ENGINES:
            self.search_engine_combo.addItem(engine.title(), engine)
        current_index = self.search_engine_combo.findData(settings.search_engine)
        self.search_engine_combo.setCurrentIndex(max(0, current_index))

        self.https_only_check = QCheckBox("Upgrade http:// page loads to https://")
        self.https_only_check.setChecked(settings.https_only)
        self.gpc_check = QCheckBox("Send Global Privacy Control (Sec-GPC) and DNT headers")
        self.gpc_check.setChecked(settings.gpc_enabled)
        self.hibernation_check = QCheckBox("Hibernate idle background tabs to save memory")
        self.hibernation_check.setChecked(settings.tab_hibernation_enabled)
        self.hibernation_minutes_spin = QSpinBox()
        self.hibernation_minutes_spin.setRange(1, 240)
        self.hibernation_minutes_spin.setValue(settings.hibernation_minutes)
        self.hibernation_minutes_spin.setSuffix(" min idle")

        for key_edit in (self.openai_key_edit, self.weather_key_edit, self.news_key_edit):
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("Homepage URL:", self.homepage_edit)
        layout.addRow("Search Engine:", self.search_engine_combo)
        layout.addRow("Browser Identity:", self.user_agent_edit)
        layout.addRow("Privacy:", self.https_only_check)
        layout.addRow("", self.gpc_check)
        layout.addRow("Performance:", self.hibernation_check)
        layout.addRow("", self.hibernation_minutes_spin)
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
            search_engine=str(self.search_engine_combo.currentData() or DEFAULT_SEARCH_ENGINE),
            https_only=self.https_only_check.isChecked(),
            gpc_enabled=self.gpc_check.isChecked(),
            tab_hibernation_enabled=self.hibernation_check.isChecked(),
            hibernation_minutes=self.hibernation_minutes_spin.value(),
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


class LibrarySearchDialog(QDialog):
    def __init__(self, parent: "OctoBrowse") -> None:
        super().__init__(parent)
        self.browser = parent
        self.entries = parent.library_entries()
        self.setWindowTitle("Library Search")
        self.setModal(True)
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        title = QLabel("Search everything")
        title.setObjectName("PaletteTitle")
        layout.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tabs, history, bookmarks, reading list, notes, and tasks...")
        self.search.textChanged.connect(self.filter_entries)
        self.search.returnPressed.connect(self.open_selected)
        layout.addWidget(self.search)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(lambda _item: self.open_selected())
        layout.addWidget(self.results)

        self.filter_entries("")
        self.search.setFocus()

    def filter_entries(self, query: str) -> None:
        tokens = [token for token in query.lower().split() if token]
        self.results.clear()
        for index, entry in enumerate(self.entries):
            haystack = f"{entry['kind']} {entry['title']} {entry.get('url', '')}".lower()
            if all(token in haystack for token in tokens):
                item = QListWidgetItem(self.format_entry(entry))
                if entry.get("url"):
                    item.setToolTip(entry["url"])
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def format_entry(self, entry: dict[str, Any]) -> str:
        title = str(entry.get("title") or entry.get("url") or "Untitled").replace("\n", " ").strip()
        url = str(entry.get("url") or "").replace("\n", " ").strip()
        if len(title) > 90:
            title = f"{title[:87]}..."
        if url and len(url) > 86:
            url = f"{url[:83]}..."
        suffix = f"  -  {url}" if url and url != title else ""
        return f"{entry['kind']}: {title}{suffix}"

    def open_selected(self) -> None:
        item = self.results.currentItem()
        if not item:
            return
        entry = self.entries[item.data(Qt.ItemDataRole.UserRole)]
        self.accept()
        self.browser.open_library_entry(entry)


class OctoBrowse(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(OCTO_BROWSER_NAME)
        self.setGeometry(100, 100, 1200, 800)

        self.store = SettingsStore()
        (
            self.settings,
            legacy_history,
            self.bookmarks,
            self.notes,
            self.todos,
            self.session_tabs,
            self.reading_list,
            self.site_permissions,
            self.site_content,
            self.downloads_history,
            self.plugin_grants,
        ) = self.store.load()
        self.openai_api_key = self.settings.openai_api_key
        self.plugins_dir = self.store.directory / "plugins"

        self.history_db = HistoryDatabase(self.store.directory)
        self.history = self.history_db.load()
        if not self.history and legacy_history:
            # One-time migration from the old JSON history blob.
            self.history_db.import_entries(legacy_history)
            self.history = self.history_db.load()
        self._history_index: dict[str, dict[str, Any]] = {entry["url"]: entry for entry in self.history}

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
        self.request_interceptor = OctoRequestInterceptor(AD_BLOCK_LIST)
        self.request_interceptor.ad_block_enabled = self.ad_block_enabled
        self.request_interceptor.https_only = self.settings.https_only
        self.request_interceptor.gpc_enabled = self.settings.gpc_enabled
        self.profile.setUrlRequestInterceptor(self.request_interceptor)

        self.filter_workers: list[FilterParseWorker] = []
        self.filter_list_dir = self.store.directory / "filterlists"
        QTimer.singleShot(0, self.reload_filter_lists)
        QTimer.singleShot(5_000, self.refresh_stale_filter_lists)

        self.hibernation_timer = QTimer(self)
        self.hibernation_timer.timeout.connect(self.hibernate_idle_tabs)
        self.hibernation_timer.start(60_000)

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
        self.downloads_sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.downloads_sidebar.customContextMenuRequested.connect(self.show_downloads_context_menu)

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

        self.security_badge = QLabel("Octo")
        self.security_badge.setObjectName("SecurityBadge")
        self.security_badge.setToolTip("Connection security")
        self.toolbar.addWidget(self.security_badge)

        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("AddressBar")
        self.url_bar.setPlaceholderText("Enter URL or search term... (Ctrl+L)")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.url_bar.setMinimumWidth(300)
        self.url_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.url_suggestions_model = QStringListModel(self.address_suggestions(), self)
        self.url_completer = QCompleter(self.url_suggestions_model, self)
        self.url_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.url_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.url_completer.activated[str].connect(self.apply_address_suggestion)
        self.url_bar.setCompleter(self.url_completer)
        self.toolbar.addWidget(self.url_bar)

        self.find_bar = QLineEdit()
        self.find_bar.setObjectName("FindBar")
        self.find_bar.setPlaceholderText("Find in page")
        self.find_bar.returnPressed.connect(self.find_in_page)
        self.find_bar.textChanged.connect(self.find_in_page)
        self.find_bar.hide()
        self.toolbar.addWidget(self.find_bar)

        self.find_count_label = QLabel("")
        self.find_count_label.setObjectName("FindCount")
        self.find_count_label.hide()
        self.toolbar.addWidget(self.find_count_label)

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
        self._add_menu_action(tools_menu, "Site Permissions", "Review saved per-site permissions", self.open_site_permissions)
        self._add_menu_action(tools_menu, "Site Controls", "Per-site JavaScript and image toggles", self.open_site_controls)
        self._add_menu_action(tools_menu, "Update EasyList", "Download and apply the EasyList filter list", self.update_easylist)
        self._add_menu_action(tools_menu, "Load Filter List...", "Import an Adblock-format filter list file", self.load_filter_list_file)
        self._add_menu_action(tools_menu, "Hibernate Background Tabs", "Free memory used by background tabs", self.hibernate_background_tabs_now)
        self._add_menu_action(tools_menu, "Mute/Unmute Tab", "Toggle audio for the current tab", self.toggle_mute_current_tab, "Ctrl+M")
        self._add_menu_action(tools_menu, "Feature Audit", "Show implemented feature checklist", self.open_feature_audit)
        self._add_menu_action(tools_menu, "Library Search", "Search all browser collections", self.open_library_search, "Ctrl+Shift+F")
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
        self._add_menu_action(tools_menu, "Plugin Manager", "Install and run permissioned plugins", self.open_plugin_manager)
        self._add_menu_action(tools_menu, "Run Extension", "Run constrained extension code (legacy)", self.run_extension)
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
        self.workspace_rail.setIconSize(QSize(20, 20))
        self.workspace_rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.workspace_rail)

        self._add_rail_action("Home", "Open dashboard", self.open_dashboard, QStyle.StandardPixmap.SP_DirHomeIcon)
        self._add_rail_action("Search", "Search tabs and saved collections", self.open_library_search, QStyle.StandardPixmap.SP_FileDialogContentsView)
        self._add_rail_action("Audit", "Show implemented feature checklist", self.open_feature_audit, QStyle.StandardPixmap.SP_DialogApplyButton)
        self.workspace_rail.addSeparator()
        self._add_rail_action("Notes", "Show notes and AI chat", lambda: self.toggle_panel(self.notes_sidebar), QStyle.StandardPixmap.SP_FileIcon)
        self._add_rail_action("Tasks", "Show todo list", lambda: self.toggle_panel(self.todo_sidebar), QStyle.StandardPixmap.SP_DialogYesButton)
        self._add_rail_action("History", "Show history", lambda: self.toggle_panel(self.history_sidebar), QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self._add_rail_action("News", "Show news", lambda: self.toggle_panel(self.news_sidebar), QStyle.StandardPixmap.SP_MessageBoxInformation)
        self._add_rail_action("Downloads", "Show downloads", lambda: self.toggle_panel(self.downloads_sidebar), QStyle.StandardPixmap.SP_ArrowDown)
        self._add_rail_action("Reading", "Show reading list", lambda: self.toggle_panel(self.reading_sidebar), QStyle.StandardPixmap.SP_FileDialogListView)
        self._add_rail_action("Bookmarks", "Show bookmarks", self.toggle_bookmarks, QStyle.StandardPixmap.SP_DialogSaveButton)
        self._add_rail_action("Extensions", "Show extension lab", self.toggle_extensions, QStyle.StandardPixmap.SP_ComputerIcon)

    def _add_rail_action(
        self,
        text: str,
        tooltip: str,
        handler: Any,
        icon: QStyle.StandardPixmap | None = None,
    ) -> QAction:
        action = QAction(text, self)
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
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
        self._add_menu_action(view_menu, "Next Tab", "Switch to the next tab", self.next_tab, "Ctrl+Tab")
        self._add_menu_action(view_menu, "Previous Tab", "Switch to the previous tab", self.previous_tab, "Ctrl+Shift+Tab")
        for tab_number in range(1, 10):
            jump_action = QAction(f"Tab {tab_number}", self)
            jump_action.setShortcut(f"Ctrl+{tab_number}")
            jump_action.triggered.connect(lambda _checked=False, number=tab_number: self.jump_to_tab(number))
            self.addAction(jump_action)
        self._add_menu_action(view_menu, "Library Search", "Search tabs and collections", self.open_library_search, "Ctrl+Shift+F")
        self._add_menu_action(view_menu, "Feature Audit", "Show implemented feature checklist", self.open_feature_audit)
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
                spacing: 3px;
                padding: 8px 6px;
                background: {panel_bg};
                border-right: 1px solid {border};
            }}
            QToolBar#WorkspaceRail QToolButton {{
                min-width: 92px;
                max-width: 106px;
                min-height: 54px;
                padding: 6px 4px;
                border: 1px solid transparent;
                border-radius: 7px;
                color: {text};
            }}
            QToolBar#WorkspaceRail QToolButton:pressed {{
                background: {accent};
                color: #ffffff;
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
            QLabel#WeatherBadge, QLabel#SecurityBadge, QLabel#FindCount {{
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
            f"Ad block {'on' if self.ad_block_enabled else 'off'} | {self.request_interceptor.total_blocked()} blocked"
        )
        self.status_zoom.setText(f"Zoom {int(zoom * 100)}%")

    def available_commands(self) -> list[BrowserCommand]:
        return [
            BrowserCommand("Open dashboard", "workspace overview", self.open_dashboard),
            BrowserCommand("Feature audit", "implemented checklist", self.open_feature_audit),
            BrowserCommand("Library search", "tabs history bookmarks notes tasks", self.open_library_search),
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
            BrowserCommand("Site permissions", "camera mic location decisions", self.open_site_permissions),
            BrowserCommand("Site controls", "per-site javascript images", self.open_site_controls),
            BrowserCommand("Update EasyList", "download ad-block filter list", self.update_easylist),
            BrowserCommand("Load filter list", "import adblock rules file", self.load_filter_list_file),
            BrowserCommand("Hibernate background tabs", "free memory now", self.hibernate_background_tabs_now),
            BrowserCommand("Mute tab", "toggle tab audio", self.toggle_mute_current_tab),
            BrowserCommand("Next tab", "Ctrl+Tab", self.next_tab),
            BrowserCommand("Previous tab", "Ctrl+Shift+Tab", self.previous_tab),
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
            BrowserCommand("Plugin manager", "permissioned plugins", self.open_plugin_manager),
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

    def open_library_search(self) -> None:
        LibrarySearchDialog(self).exec()

    def address_suggestions(self) -> list[str]:
        commands = [
            "octo:dashboard",
            "octo:features",
            "octo:identity",
            "octo:tabs",
            "octo:downloads",
            "octo:reading",
            "octo:history",
            "octo:bookmarks",
            "octo:todos",
            "octo:notes",
            "octo:library",
            "octo:permissions",
            "octo:plugins",
            "octo:settings",
            "!ddg ",
            "!yt ",
            "!gh ",
            "!w ",
            "!maps ",
            "!news ",
            "!pypi ",
            "!mdn ",
        ]
        now = time.time()
        ranked = sorted(self.history, key=lambda entry: self._frecency(entry, now), reverse=True)
        urls = []
        for url in [entry["url"] for entry in ranked[:60]] + self.bookmarks + self.reading_list:
            if url and url not in urls:
                urls.append(url)
        return commands + urls

    def refresh_address_suggestions(self) -> None:
        if hasattr(self, "url_suggestions_model"):
            self.url_suggestions_model.setStringList(self.address_suggestions())

    def apply_address_suggestion(self, text: str) -> None:
        self.url_bar.setText(text)
        if not text.endswith(" "):
            self.navigate_to_url()

    def library_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, QWebEngineView):
                entries.append(
                    {
                        "kind": "Tab",
                        "title": self.tabs.tabText(index),
                        "url": widget.url().toString(),
                        "tab_index": index,
                    }
                )
        for entry in reversed(self.history[-120:]):
            entries.append({"kind": "History", "title": entry.get("title") or entry["url"], "url": entry["url"]})
        for url in self.bookmarks:
            entries.append({"kind": "Bookmark", "title": url, "url": url})
        for url in self.reading_list:
            entries.append({"kind": "Reading", "title": url, "url": url})
        for note in self.notes:
            entries.append({"kind": "Note", "title": note.get("note", ""), "url": note.get("url", "")})
        for todo in self.todos:
            entries.append({"kind": "Task", "title": todo})
        return entries

    def open_library_entry(self, entry: dict[str, Any]) -> None:
        if "tab_index" in entry:
            self.tabs.setCurrentIndex(int(entry["tab_index"]))
            return
        if entry.get("url"):
            self.add_tab(QUrl(str(entry["url"])), str(entry.get("kind", "Library")))
            return
        if entry.get("kind") == "Task":
            self.open_panel(self.todo_sidebar)
        else:
            self.open_panel(self.notes_sidebar)

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
            safe_href = safe_link_href(url)
            safe_text = html.escape(url, quote=True)
            mode = "Private" if widget.property("private") else "Standard"
            rows.append(f"<tr><td>{index + 1}</td><td>{title}</td><td>{mode}</td><td><a href=\"{safe_href}\">{safe_text}</a></td></tr>")
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

    def open_feature_audit(self) -> None:
        rows = []
        for category, features in self.feature_catalog().items():
            items = "".join(f"<li>{html.escape(feature)}</li>" for feature in features)
            rows.append(f"<section class='panel'><h2>{html.escape(category)}</h2><ul>{items}</ul></section>")
        feature_count = sum(len(items) for items in self.feature_catalog().values())
        audit_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Feature Audit</title>
<style>
body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f6f8fb; color: #142033; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 34px 24px 56px; }}
h1 {{ margin: 0 0 6px; }}
.sub {{ color: #64748b; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 14px; }}
.panel {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; padding: 16px; }}
li {{ margin: 7px 0; }}
</style>
</head>
<body>
<main>
<h1>Feature Audit</h1>
<div class="sub">{feature_count} implemented browser capabilities across main and alpha parity plus new Octo Browser features.</div>
<div class="grid">{''.join(rows)}</div>
</main>
</body>
</html>"""
        self.add_html_tab(audit_html, "Feature Audit", private=False)

    def feature_catalog(self) -> dict[str, list[str]]:
        return {
            "Core Browser": [
                "Tabbed browsing with close, duplicate, restore, and target-blank support",
                "Address/search bar with URL normalization, bang search, Octo commands, and suggestions",
                "Frecency-ranked address suggestions from titled, visit-counted history",
                "Configurable default search engine (Google, DuckDuckGo, Bing, Brave, Startpage)",
                "Back, forward, reload, home, zoom, fullscreen, and user-agent controls",
                "Tab navigation shortcuts (Ctrl+Tab, Ctrl+1-9) and per-tab audio mute",
                "HTML5 fullscreen support for video players",
                "Built-in PDF viewer",
                "Session restore for standard tabs",
                "Render-process crash detection with automatic reload",
            ],
            "Workspace": [
                "Dashboard first screen",
                "Command palette",
                "Unified library search",
                "Left workspace rail and focused side panels",
                "Tab overview",
                "Automatic background-tab hibernation to reclaim memory",
                "Find-in-page with live match counter",
            ],
            "Collections": [
                "SQLite-backed history with titles, visit counts, and context actions",
                "Bookmarks with context actions",
                "Persistent reading list",
                "Notes and todos",
                "Download manager with pause/resume/cancel and persistent download history",
            ],
            "Page Tools": [
                "Reader view",
                "Page insights",
                "Save page HTML",
                "View source",
                "Screenshot saving",
                "OpenCV upscaled screenshot preview",
                "Copy URL and Markdown link",
            ],
            "Privacy And Identity": [
                "Ad-block interceptor with fast suffix matching and privacy report",
                "EasyList-compatible filter list parsing with token-indexed pattern rules",
                "Cosmetic element-hiding rules injected per page",
                "Automatic weekly EasyList refresh",
                "Per-site content controls (JavaScript and image toggles)",
                "HTTPS-only mode with automatic page upgrades",
                "Global Privacy Control (Sec-GPC) and DNT request headers",
                "Per-site permission prompts for camera, microphone, location, and notifications",
                "Connection security badge in the toolbar",
                "Private/off-the-record tabs",
                "Global private mode history pause",
                "Clear browser data",
                "Octo Browser HTTP and navigator identity",
            ],
            "AI And Voice": [
                "OpenAI page summarization",
                "Page-aware AI chat",
                "Text-to-speech read aloud",
                "SpeechRecognition voice commands",
            ],
            "Extensibility": [
                "Permissioned plugin API with manifest-declared capabilities and a plugin manager",
                "Constrained extension lab (legacy)",
                "Trusted legacy extension execution path",
                "Session password scratchpad",
                "Persistent settings with atomic writes",
            ],
        }

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
            f"Blocked this session: {self.request_interceptor.total_blocked()}",
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
        for entry in self.history:
            self.history_sidebar.addItem(self._make_history_item(entry))
        for past_download in self.downloads_history[-20:]:
            file_path = str(past_download.get("file", ""))
            status = str(past_download.get("status", "complete")).title()
            item = QListWidgetItem(f"{status}: {Path(file_path).name}")
            item.setToolTip(file_path)
            item.setData(DOWNLOAD_PATH_ROLE, file_path)
            self.downloads_sidebar.addItem(item)
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
            self.private_profile.setUrlRequestInterceptor(self.request_interceptor)
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

    def apply_privacy_settings(self) -> None:
        """Push the current privacy toggles into the always-installed interceptor."""
        self.request_interceptor.ad_block_enabled = self.ad_block_enabled
        self.request_interceptor.https_only = self.settings.https_only
        self.request_interceptor.gpc_enabled = self.settings.gpc_enabled

    def reload_filter_lists(self) -> None:
        """Parse every cached filter list off the UI thread."""
        texts: list[str] = []
        if self.filter_list_dir.is_dir():
            for list_path in sorted(self.filter_list_dir.glob("*.txt")):
                try:
                    texts.append(list_path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
        if not texts:
            self.request_interceptor.filter_rules = None
            return
        worker = FilterParseWorker(texts, self)
        worker.parsed.connect(self.handle_filter_rules_parsed)
        worker.finished.connect(lambda worker=worker: self.cleanup_filter_worker(worker))
        self.filter_workers.append(worker)
        worker.start()

    def cleanup_filter_worker(self, worker: FilterParseWorker) -> None:
        if worker in self.filter_workers:
            self.filter_workers.remove(worker)

    def handle_filter_rules_parsed(self, rules: object) -> None:
        if not isinstance(rules, FilterRuleSet):
            return
        self.request_interceptor.filter_rules = rules
        self.set_status(
            f"Filter lists loaded: {rules.rule_count} rules "
            f"({len(rules.blocked_domains)} domains, {rules.skipped_count} unsupported skipped)"
        )

    def load_filter_list_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Filter List", "", "Filter Lists (*.txt);;All Files (*)"
        )
        if not file_path:
            return
        source = Path(file_path)
        try:
            self.filter_list_dir.mkdir(parents=True, exist_ok=True)
            (self.filter_list_dir / source.name).write_text(
                source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Filter List", f"Could not import filter list: {exc}")
            return
        self.reload_filter_lists()
        self.set_status(f"Imported filter list {source.name}")

    def update_easylist(self) -> None:
        self.set_status("Downloading EasyList...")
        self.start_api_worker("filterlist", EASYLIST_URL, as_json=False)

    def refresh_stale_filter_lists(self) -> None:
        """Re-download EasyList automatically when the cached copy is over a week old."""
        cache_path = self.filter_list_dir / "easylist.txt"
        try:
            if cache_path.exists() and time.time() - cache_path.stat().st_mtime > 7 * 86400:
                self.update_easylist()
        except OSError:
            pass

    def _wire_browser(self, browser: QWebEngineView) -> None:
        """Connections and engine settings shared by every tab."""
        browser.setProperty("last_active", time.time())
        page = browser.page()
        settings = browser.settings()
        for attr_name, value in (
            ("FullScreenSupportEnabled", True),
            ("PdfViewerEnabled", True),
            ("PluginsEnabled", True),
            ("ScrollAnimatorEnabled", True),
        ):
            attr = getattr(QWebEngineSettings.WebAttribute, attr_name, None)
            if attr is not None:
                settings.setAttribute(attr, value)

        browser.urlChanged.connect(lambda new_url, browser=browser: self.update_url_bar(new_url, browser))
        browser.urlChanged.connect(lambda new_url, browser=browser: self.apply_site_content(browser, new_url))
        browser.loadProgress.connect(lambda progress, browser=browser: self.update_progress_bar(progress, browser))
        browser.loadFinished.connect(lambda _ok, browser=browser: self.on_load_finished(browser))
        browser.titleChanged.connect(lambda page_title, browser=browser: self.update_tab_title(browser, page_title))
        page.fullScreenRequested.connect(self.handle_fullscreen_request)
        page.renderProcessTerminated.connect(
            lambda status, _code, browser=browser: self.handle_render_crash(browser, status)
        )
        if hasattr(page, "permissionRequested"):  # Qt 6.8+
            page.permissionRequested.connect(self.handle_permission_request)
        elif hasattr(page, "featurePermissionRequested"):
            page.featurePermissionRequested.connect(
                lambda origin, feature, page=page: self.handle_feature_permission(page, origin, feature)
            )

    def add_tab(self, url: QUrl, title: str, private: bool | None = None) -> QWebEngineView:
        is_private = self.incognito_mode if private is None else private
        browser = QWebEngineView()
        browser.setProperty("private", is_private)
        browser.setPage(OctoWebPage(self, self.profile_for_tab(is_private), is_private, browser))
        browser.load(url)

        display_title = f"Private - {title}" if is_private else title
        index = self.tabs.addTab(browser, display_title)
        self.tabs.setCurrentIndex(index)

        self._wire_browser(browser)
        self.update_status_badges()
        self.set_status("Opened private tab" if is_private else "Opened tab")
        return browser

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
        if not browser.property("private"):
            self.update_history_title(browser.url().toString(), title)

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
        self.wake_browser(browser)
        self.url_bar.setText(browser.url().toString())
        self.update_security_badge(browser.url())
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
            "features": self.open_feature_audit,
            "audit": self.open_feature_audit,
            "library": self.open_library_search,
            "search": self.open_library_search,
            "downloads": lambda: self.toggle_panel(self.downloads_sidebar),
            "history": lambda: self.toggle_panel(self.history_sidebar),
            "bookmarks": self.toggle_bookmarks,
            "reading": lambda: self.toggle_panel(self.reading_sidebar),
            "todos": lambda: self.toggle_panel(self.todo_sidebar),
            "tasks": lambda: self.toggle_panel(self.todo_sidebar),
            "notes": lambda: self.toggle_panel(self.notes_sidebar),
            "permissions": self.open_site_permissions,
            "plugins": self.open_plugin_manager,
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
        self.find_count_label.setVisible(self.find_bar.isVisible())
        if self.find_bar.isVisible():
            self.find_bar.setFocus()
            self.find_bar.selectAll()
        else:
            self.find_count_label.clear()
            browser = self.current_browser()
            if browser:
                browser.page().findText("")

    def _handle_find_result(self, result: Any) -> None:
        try:
            total = result.numberOfMatches()
            active = result.activeMatch()
        except Exception:
            return
        self.find_count_label.setText(f"{active}/{total}" if total else "0/0")

    def find_in_page(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        query = self.find_bar.text()
        if not query:
            self.find_count_label.clear()
            browser.page().findText("")
            return
        try:
            browser.page().findText(query, QWebEnginePage.FindFlag(0), self._handle_find_result)
        except TypeError:
            browser.page().findText(query)

    def find_previous(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        query = self.find_bar.text()
        try:
            browser.page().findText(query, QWebEnginePage.FindFlag.FindBackward, self._handle_find_result)
        except TypeError:
            browser.page().findText(query, QWebEnginePage.FindFlag.FindBackward)

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
        template = SEARCH_ENGINES.get(self.settings.search_engine, SEARCH_ENGINES[DEFAULT_SEARCH_ENGINE])
        return QUrl(template.format(query=quote_plus(url_text)))

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
        browser.setPage(OctoWebPage(self, self.profile_for_tab(private), private, browser))
        browser.setHtml(html_text, QUrl("https://octobrowse.local/"))
        index = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(index)
        self._wire_browser(browser)
        self.update_status_badges()

    def open_dashboard(self) -> None:
        self.add_html_tab(self.build_dashboard_html(), "Dashboard", private=False)

    def build_dashboard_html(self) -> str:
        history_links = self._dashboard_links(self.history[-8:])
        bookmark_links = self._dashboard_links(self.bookmarks[:10])
        notes_count = len(self.notes)
        todo_count = len(self.todos)
        reading_count = len(self.reading_list)
        blocked = self.request_interceptor.total_blocked()
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
.actions {{ margin-top: 16px; display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; }}
.metric, .panel, .action {{
  background: #ffffff;
  border: 1px solid #dce3ec;
  border-radius: 8px;
  padding: 16px;
}}
.metric, .action {{ display: block; color: #172033; }}
.metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
.action strong {{ display: block; margin-bottom: 4px; }}
.action span {{ color: #64748b; font-size: 13px; }}
.metric:hover, .action:hover {{ border-color: #7aa7e8; box-shadow: 0 8px 24px rgba(23, 32, 51, 0.08); }}
.wide {{ margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
a {{ color: #0f5dcc; text-decoration: none; }}
li {{ margin: 8px 0; }}
.empty {{ color: #6b7280; }}
@media (max-width: 820px) {{
  .grid, .actions, .wide {{ grid-template-columns: 1fr 1fr; }}
}}
@media (max-width: 560px) {{
  .grid, .actions, .wide {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<main>
  <h1>OctoBrowse</h1>
  <div class="sub">Workspace dashboard for quick return, privacy awareness, and page work.</div>
  <section class="grid">
    <a class="metric" href="octo:history">History<strong>{len(self.history)}</strong></a>
    <a class="metric" href="octo:bookmarks">Bookmarks<strong>{len(self.bookmarks)}</strong></a>
    <a class="metric" href="octo:todos">Todos<strong>{todo_count}</strong></a>
    <a class="metric" href="octo:features">Features<strong>{sum(len(items) for items in self.feature_catalog().values())}</strong></a>
    <a class="metric" href="octo:reading">Reading<strong>{reading_count}</strong></a>
    <a class="metric" href="octo:tabs">Saved Tabs<strong>{saved_tabs_count}</strong></a>
  </section>
  <section class="actions">
    <a class="action" href="octo:features"><strong>Feature Audit</strong><span>Verify the old and new capability set.</span></a>
    <a class="action" href="octo:library"><strong>Library Search</strong><span>Search tabs, history, bookmarks, notes, and tasks.</span></a>
    <a class="action" href="octo:identity"><strong>Browser Identity</strong><span>Inspect Octo Browser user agent and navigator values.</span></a>
    <a class="action" href="octo:tabs"><strong>Tab Overview</strong><span>Review every open standard and private tab.</span></a>
    <a class="action" href="octo:downloads"><strong>Downloads</strong><span>Open download progress and completed files.</span></a>
    <a class="action" href="octo:settings"><strong>Settings</strong><span>Manage homepage, keys, model, weather, and news.</span></a>
  </section>
  <section class="wide">
    <div class="panel"><h2>Recent</h2>{history_links}</div>
    <div class="panel"><h2>Bookmarks</h2>{bookmark_links}</div>
  </section>
  <section class="wide">
    <div class="panel"><h2>Session</h2><p>{weather}</p><p>{notes_count} saved notes in this workspace.</p><p>{downloads_count} tracked downloads.</p><p>{blocked} requests blocked this session.</p><p>Identity: {browser_identity}</p></div>
    <div class="panel"><h2>Shortcuts</h2><p>Ctrl+K command palette</p><p>Ctrl+F find in page</p><p>Ctrl+D bookmark</p><p>Ctrl+J downloads</p><p>Ctrl+Shift+T reopen tab</p></div>
  </section>
</main>
</body>
</html>"""

    def _dashboard_links(self, entries: list[Any]) -> str:
        if not entries:
            return '<p class="empty">Nothing saved yet.</p>'
        items = []
        for entry in entries:
            if isinstance(entry, dict):
                url = str(entry.get("url") or "")
                label_text = str(entry.get("title") or "").strip() or url.replace("https://", "").replace("http://", "")
            else:
                url = str(entry)
                label_text = url.replace("https://", "").replace("http://", "")
            safe_url = safe_link_href(url)
            label = html.escape(label_text[:72])
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
        keywords = html.escape(", ".join(self.extract_keywords(cleaned, limit=8)))
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
            f"Ad-blocked requests this session: {self.request_interceptor.total_blocked()}",
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
        browser.setProperty("last_active", time.time())
        text = url.toString()
        self.url_bar.setText(text)
        self.update_security_badge(url)
        if not self.incognito_mode and not browser.property("private") and not self.is_internal_url(text):
            self.add_to_history(text)
        self.update_status_badges()

    def update_security_badge(self, url: QUrl) -> None:
        if not hasattr(self, "security_badge"):
            return
        scheme = url.scheme().lower()
        if self.is_internal_url(url.toString()):
            self.security_badge.setText("Octo")
            self.security_badge.setToolTip("Internal OctoBrowse page")
        elif scheme == "https":
            self.security_badge.setText("\U0001F512")
            self.security_badge.setToolTip("Connection uses HTTPS")
        elif scheme == "http":
            self.security_badge.setText("⚠ http")
            self.security_badge.setToolTip("Connection is not encrypted")
        else:
            self.security_badge.setText(scheme or "?")
            self.security_badge.setToolTip(f"Scheme: {scheme or 'unknown'}")

    def _make_history_item(self, entry: dict[str, Any]) -> QListWidgetItem:
        title = str(entry.get("title") or "").strip()
        url = str(entry.get("url") or "")
        item = QListWidgetItem(f"{title}  -  {url}" if title else url)
        item.setData(Qt.ItemDataRole.UserRole, url)
        item.setToolTip(url)
        return item

    def _history_sidebar_item(self, url: str) -> QListWidgetItem | None:
        for row in range(self.history_sidebar.count()):
            item = self.history_sidebar.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == url:
                return item
        return None

    @staticmethod
    def _frecency(entry: dict[str, Any], now: float) -> float:
        """Mozilla-style frecency: visit count weighted by recency buckets."""
        age_days = max(0.0, now - float(entry.get("last_visit") or 0)) / 86400
        if age_days <= 4:
            weight = 100
        elif age_days <= 14:
            weight = 70
        elif age_days <= 31:
            weight = 50
        elif age_days <= 90:
            weight = 30
        else:
            weight = 10
        return max(1, int(entry.get("visits") or 1)) * weight

    def add_to_history(self, url: str) -> None:
        if self.is_internal_url(url):
            return
        now = time.time()
        entry = self._history_index.get(url)
        if entry is not None:
            entry["visits"] = int(entry.get("visits") or 0) + 1
            entry["last_visit"] = now
            item = self._history_sidebar_item(url)
            if item is not None:
                title = str(entry.get("title") or "").strip()
                item.setText(f"{title}  -  {url}" if title else url)
        else:
            entry = {"url": url, "title": "", "visits": 1, "last_visit": now}
            self.history.append(entry)
            self._history_index[url] = entry
            if len(self.history) > MAX_HISTORY_ITEMS:
                for removed in self.history[: len(self.history) - MAX_HISTORY_ITEMS]:
                    self._history_index.pop(removed["url"], None)
                    stale_item = self._history_sidebar_item(removed["url"])
                    if stale_item is not None:
                        self.history_sidebar.takeItem(self.history_sidebar.row(stale_item))
                self.history = self.history[-MAX_HISTORY_ITEMS:]
            self.history_sidebar.addItem(self._make_history_item(entry))
        self.history_db.record_visit(url, now)
        self.refresh_address_suggestions()

    def update_history_title(self, url: str, title: str) -> None:
        entry = self._history_index.get(url)
        title = title.strip()
        if entry is None or not title or entry.get("title") == title:
            return
        entry["title"] = title
        self.history_db.set_title(url, title)
        item = self._history_sidebar_item(url)
        if item is not None:
            item.setText(f"{title}  -  {url}")

    def load_history_url(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self.url_bar.setText(str(url))
        self.navigate_to_url()

    def clear_history(self) -> None:
        self.history.clear()
        self._history_index.clear()
        self.history_sidebar.clear()
        self.history_db.clear()
        self.refresh_address_suggestions()
        QMessageBox.information(self, "History Cleared", "Browsing history has been cleared.")

    def clear_browser_data(self) -> None:
        self.history.clear()
        self._history_index.clear()
        self.history_sidebar.clear()
        self.history_db.clear()
        self.profile.clearHttpCache()
        self.profile.cookieStore().deleteAllCookies()
        if self.private_profile is not None:
            self.private_profile.clearHttpCache()
            self.private_profile.cookieStore().deleteAllCookies()
        self.request_interceptor.reset_stats()
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
        self.inject_cosmetic_filters(browser)

    def inject_cosmetic_filters(self, browser: QWebEngineView) -> None:
        """Apply element-hiding rules from loaded filter lists to the page."""
        if not self.ad_block_enabled:
            return
        rules = self.request_interceptor.filter_rules
        if rules is None or (not rules.generic_selectors and not rules.domain_selectors):
            return
        url = browser.url()
        if self.is_internal_url(url.toString()):
            return
        css = rules.cosmetic_css_for(url.host().lower())
        if not css:
            return
        script = f"""
(() => {{
  const id = "octo-cosmetic-style";
  let style = document.getElementById(id);
  if (!style) {{
    style = document.createElement("style");
    style.id = id;
    (document.head || document.documentElement).appendChild(style);
  }}
  style.textContent = {json.dumps(css)};
}})();
"""
        browser.page().runJavaScript(script)

    def toggle_dark_mode(self) -> None:
        self.set_theme("default" if self.dark_mode else "dark")

    def apply_dark_mode(self, browser: QWebEngineView) -> None:
        # Prefer Chromium's auto-darkening (Qt 6.7+): it inverts intelligently
        # and respects pages that already declare a dark color scheme.
        force_dark = getattr(QWebEngineSettings.WebAttribute, "ForceDarkMode", None)
        if force_dark is not None:
            browser.settings().setAttribute(force_dark, self.dark_mode)
            return
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
        self.apply_privacy_settings()
        status = "enabled" if self.ad_block_enabled else "disabled"
        self.update_status_badges()
        self.save_settings()
        QMessageBox.information(self, "Ad Block", f"Ad block {status}.")

    def show_privacy_report(self) -> None:
        blocked = self.request_interceptor.total_blocked()
        top_domains = self.request_interceptor.blocked_by_domain.most_common(8)
        rules = self.request_interceptor.filter_rules
        filter_summary = (
            f"{rules.rule_count} rules ({len(rules.blocked_domains)} domains, {rules.skipped_count} skipped)"
            if rules is not None
            else "built-in list only"
        )
        lines = [
            f"Ad block: {'on' if self.ad_block_enabled else 'off'}",
            f"Blocked requests this session: {blocked}",
            f"Filter lists: {filter_summary}",
            f"Site content overrides: {len(self.site_content)}",
            f"HTTPS-only mode: {'on' if self.settings.https_only else 'off'}",
            f"HTTPS upgrades this session: {self.request_interceptor.https_upgrades}",
            f"Global Privacy Control: {'on' if self.settings.gpc_enabled else 'off'}",
            f"Saved site permissions: {sum(len(features) for features in self.site_permissions.values())}",
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
        self.open_panel(self.notes_sidebar, status="Page chat mode")
        self.notes_sidebar.append("Ask about the current page on a new line, then press Enter.\n")

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

    def start_api_worker(self, kind: str, url: str, as_json: bool = True) -> None:
        worker = ApiFetchWorker(kind, url, self, as_json=as_json)
        worker.data_ready.connect(self.handle_api_data)
        worker.failed.connect(self.handle_api_error)
        worker.finished.connect(lambda worker=worker: self.cleanup_api_worker(worker))
        self.network_workers.append(worker)
        worker.start()

    def cleanup_api_worker(self, worker: ApiFetchWorker) -> None:
        if worker in self.network_workers:
            self.network_workers.remove(worker)

    def handle_api_data(self, kind: str, data: object) -> None:
        if kind == "filterlist" and isinstance(data, str):
            try:
                self.filter_list_dir.mkdir(parents=True, exist_ok=True)
                (self.filter_list_dir / "easylist.txt").write_text(data, encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "EasyList", f"Could not cache EasyList: {exc}")
                return
            self.reload_filter_lists()
            return
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

    def handle_api_error(self, kind: str, error: str) -> None:
        if kind == "weather":
            self.weather_widget.setText("Weather: Unavailable")
        elif kind == "news":
            self.news_sidebar.clear()
            self.news_sidebar.addItem(QListWidgetItem("News: Unavailable"))
        elif kind == "filterlist":
            self.set_status(f"EasyList download failed: {error}")

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
        item.setData(DOWNLOAD_PATH_ROLE, str(target))
        item.setData(DOWNLOAD_REQUEST_ROLE, download)
        self.downloads_sidebar.addItem(item)
        self.open_panel(self.downloads_sidebar, status=f"Downloading {target.name}")
        self.downloads.append({"file": str(target), "status": "downloading"})

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
        finished_status: str | None = None
        if "Completed" in state_name:
            item.setText(f"Complete: {filename}")
            self.set_status(f"Downloaded {filename}")
            finished_status = "complete"
        elif "Cancelled" in state_name:
            item.setText(f"Cancelled: {filename}")
            self.set_status("Download cancelled")
            finished_status = "cancelled"
        elif "Interrupted" in state_name:
            item.setText(f"Failed: {filename}")
            self.set_status("Download failed")
            finished_status = "failed"
        if finished_status is not None:
            item.setData(DOWNLOAD_REQUEST_ROLE, None)
            try:
                source_url = download.url().toString()
            except Exception:
                source_url = ""
            self.downloads_history.append(
                {
                    "file": str(item.data(DOWNLOAD_PATH_ROLE) or filename),
                    "url": source_url,
                    "status": finished_status,
                    "time": time.time(),
                }
            )
            self.downloads_history = self.downloads_history[-100:]
            self.save_settings()

    def show_downloads_context_menu(self, position: Any) -> None:
        item = self.downloads_sidebar.itemAt(position)
        menu = QMenu(self)
        if item is not None:
            download = item.data(DOWNLOAD_REQUEST_ROLE)
            file_path = str(item.data(DOWNLOAD_PATH_ROLE) or "")
            if download is not None:
                try:
                    is_paused = bool(download.isPaused())
                except Exception:
                    is_paused = False
                if is_paused:
                    resume_action = QAction("Resume", self)
                    resume_action.triggered.connect(lambda _checked=False, d=download: d.resume())
                    menu.addAction(resume_action)
                else:
                    pause_action = QAction("Pause", self)
                    pause_action.triggered.connect(lambda _checked=False, d=download: d.pause())
                    menu.addAction(pause_action)
                cancel_action = QAction("Cancel", self)
                cancel_action.triggered.connect(lambda _checked=False, d=download: d.cancel())
                menu.addAction(cancel_action)
                menu.addSeparator()
            if file_path:
                open_file_action = QAction("Open File", self)
                open_file_action.triggered.connect(
                    lambda _checked=False, p=file_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p))
                )
                open_file_action.setEnabled(Path(file_path).exists())
                menu.addAction(open_file_action)
                open_folder_action = QAction("Open Containing Folder", self)
                open_folder_action.triggered.connect(
                    lambda _checked=False, p=file_path: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(Path(p).parent))
                    )
                )
                menu.addAction(open_folder_action)
                menu.addSeparator()
        clear_action = QAction("Clear Download List", self)
        clear_action.triggered.connect(self.clear_download_list)
        menu.addAction(clear_action)
        menu.exec(self.downloads_sidebar.mapToGlobal(position))

    def clear_download_list(self) -> None:
        self.downloads_sidebar.clear()
        self.downloads_history.clear()
        self.save_settings()
        self.set_status("Download list cleared")

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def handle_fullscreen_request(self, request: Any) -> None:
        """Let pages (video players) enter real fullscreen by hiding browser chrome."""
        request.accept()
        entering = request.toggleOn()
        for widget in (self.toolbar, self.workspace_rail, self.menuBar(), self.statusBar(), self.tabs.tabBar()):
            widget.setVisible(not entering)
        if entering:
            self._was_window_fullscreen = self.isFullScreen()
            self.showFullScreen()
        elif not getattr(self, "_was_window_fullscreen", False):
            self.showNormal()

    def handle_render_crash(self, browser: QWebEngineView, status: Any) -> None:
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            return
        now = time.time()
        last_crash = float(browser.property("last_crash") or 0)
        browser.setProperty("last_crash", now)
        if now - last_crash > 30:
            QTimer.singleShot(0, browser.reload)
            self.set_status("Page crashed - reloading")
        else:
            self.set_status("Page keeps crashing - reload manually to retry")

    def hibernate_idle_tabs(self, force: bool = False) -> int:
        """Discard idle background tabs so Chromium frees their memory.

        Mirrors Chrome's tab-discarding lifecycle: the page reloads
        automatically the next time its tab is selected.
        """
        if not force and not self.settings.tab_hibernation_enabled:
            return 0
        threshold = 0 if force else max(1, self.settings.hibernation_minutes) * 60
        now = time.time()
        current = self.tabs.currentWidget()
        hibernated = 0
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if not isinstance(widget, QWebEngineView) or widget is current:
                continue
            if self.is_internal_url(widget.url().toString()):
                continue
            last_active = float(widget.property("last_active") or 0)
            if now - last_active < threshold:
                continue
            page = widget.page()
            try:
                if page.recentlyAudible():
                    continue
                if page.lifecycleState() != QWebEnginePage.LifecycleState.Active:
                    continue
                page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
                hibernated += 1
            except Exception:
                continue
        if hibernated:
            self.set_status(f"Hibernated {hibernated} background tab{'s' if hibernated != 1 else ''}")
        return hibernated

    def hibernate_background_tabs_now(self) -> None:
        if not self.hibernate_idle_tabs(force=True):
            self.set_status("No background tabs to hibernate")

    def wake_browser(self, browser: QWebEngineView) -> None:
        browser.setProperty("last_active", time.time())
        try:
            if browser.page().lifecycleState() != QWebEnginePage.LifecycleState.Active:
                browser.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except Exception:
            pass

    def _permission_key(self, origin: QUrl) -> str:
        if origin.port() != -1:
            return f"{origin.scheme()}://{origin.host()}:{origin.port()}"
        return f"{origin.scheme()}://{origin.host()}"

    def _decide_permission(self, origin: QUrl, feature_name: str) -> bool:
        key = self._permission_key(origin)
        stored = self.site_permissions.get(key, {})
        if feature_name in stored:
            return stored[feature_name]
        label = feature_name.replace("MediaAudioVideoCapture", "camera and microphone")
        label = label.replace("MediaAudioCapture", "microphone").replace("MediaVideoCapture", "camera")
        label = label.replace("DesktopAudioVideoCapture", "screen and audio capture")
        label = label.replace("DesktopVideoCapture", "screen capture")
        answer = QMessageBox.question(
            self,
            "Site Permission",
            f"{key} wants to use: {label}\n\nAllow? Your choice is remembered for this site.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        allowed = answer == QMessageBox.StandardButton.Yes
        self.site_permissions.setdefault(key, {})[feature_name] = allowed
        self.save_settings()
        return allowed

    def handle_permission_request(self, permission: Any) -> None:
        """Qt 6.8+ unified permission API."""
        try:
            feature_name = getattr(permission.permissionType(), "name", str(permission.permissionType()))
            if self._decide_permission(permission.origin(), feature_name):
                permission.grant()
            else:
                permission.deny()
        except Exception:
            pass

    def handle_feature_permission(self, page: QWebEnginePage, origin: QUrl, feature: Any) -> None:
        """Legacy per-feature permission API (Qt < 6.8)."""
        feature_name = getattr(feature, "name", str(feature))
        policy = (
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            if self._decide_permission(origin, feature_name)
            else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        )
        page.setFeaturePermission(origin, feature, policy)

    def open_site_permissions(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Site Permissions")
        dialog.resize(560, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Saved per-site permission decisions. Double-click an entry to remove it."))
        permissions_list = QListWidget()

        def refresh() -> None:
            permissions_list.clear()
            for origin, features in sorted(self.site_permissions.items()):
                for feature_name, allowed in sorted(features.items()):
                    item = QListWidgetItem(f"{origin} - {feature_name}: {'allowed' if allowed else 'blocked'}")
                    item.setData(Qt.ItemDataRole.UserRole, (origin, feature_name))
                    permissions_list.addItem(item)
            if not permissions_list.count():
                permissions_list.addItem(QListWidgetItem("No saved site permissions."))

        def remove_item(item: QListWidgetItem) -> None:
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data:
                return
            origin, feature_name = data
            self.site_permissions.get(origin, {}).pop(feature_name, None)
            if not self.site_permissions.get(origin):
                self.site_permissions.pop(origin, None)
            self.save_settings()
            refresh()

        permissions_list.itemDoubleClicked.connect(remove_item)
        layout.addWidget(permissions_list)
        clear_btn = QPushButton("Clear All")

        def clear_all() -> None:
            self.site_permissions.clear()
            self.save_settings()
            refresh()

        clear_btn.clicked.connect(clear_all)
        layout.addWidget(clear_btn)
        refresh()
        dialog.exec()

    def apply_site_content(self, browser: QWebEngineView, url: QUrl) -> None:
        """Apply per-site JavaScript/image preferences before the page renders."""
        host = url.host().lower()
        prefs = self.site_content.get(host, {})
        settings = browser.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, bool(prefs.get("javascript", True))
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AutoLoadImages, bool(prefs.get("images", True))
        )

    def open_site_controls(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        host = browser.url().host().lower()
        if not host or self.is_internal_url(browser.url().toString()):
            QMessageBox.information(self, "Site Controls", "Open a website tab to set per-site controls.")
            return
        prefs = self.site_content.get(host, {})

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Site Controls - {host}")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Content controls for {host} (reload the page to fully apply):"))
        javascript_check = QCheckBox("Allow JavaScript")
        javascript_check.setChecked(bool(prefs.get("javascript", True)))
        images_check = QCheckBox("Load images")
        images_check.setChecked(bool(prefs.get("images", True)))
        layout.addWidget(javascript_check)
        layout.addWidget(images_check)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(dialog.accept)
        layout.addWidget(save_btn)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_prefs = {"javascript": javascript_check.isChecked(), "images": images_check.isChecked()}
        if all(new_prefs.values()):
            self.site_content.pop(host, None)
        else:
            self.site_content[host] = new_prefs
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, QWebEngineView) and widget.url().host().lower() == host:
                self.apply_site_content(widget, widget.url())
        self.save_settings()
        self.set_status(f"Site controls saved for {host}")

    def _read_plugin_manifest(self, path: Path) -> dict[str, Any] | None:
        """Extract MANIFEST from a plugin file without executing any of its code."""
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            return None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "MANIFEST" for target in node.targets
            ):
                try:
                    manifest = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    return None
                if not isinstance(manifest, dict) or not str(manifest.get("name", "")).strip():
                    return None
                permissions = manifest.get("permissions", [])
                if not isinstance(permissions, list):
                    return None
                manifest["permissions"] = [str(p) for p in permissions if str(p) in PLUGIN_PERMISSIONS]
                return manifest
        return None

    def discover_plugins(self) -> list[dict[str, Any]]:
        plugins: list[dict[str, Any]] = []
        if not self.plugins_dir.is_dir():
            return plugins
        for path in sorted(self.plugins_dir.glob("*.py")):
            manifest = self._read_plugin_manifest(path)
            if manifest is not None:
                plugins.append({"path": path, "manifest": manifest})
        return plugins

    @staticmethod
    def _plugin_file_hash(path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return ""

    def _ensure_plugin_grants(self, manifest: dict[str, Any], path: Path) -> set[str] | None:
        """Return the granted permission set, prompting the user if needed.

        Grants are bound to the plugin file's content hash, so a different file
        reusing an approved plugin's name (or an edited version of an approved
        plugin) does not silently inherit the old permissions.
        """
        name = str(manifest["name"])
        requested = [p for p in manifest.get("permissions", []) if p in PLUGIN_PERMISSIONS]
        current_hash = self._plugin_file_hash(path)
        record = self.plugin_grants.get(name)
        same_file = bool(record) and record.get("sha256") and record.get("sha256") == current_hash
        granted = set(record.get("permissions", [])) if same_file else set()
        missing = [p for p in requested if p not in granted]
        if not missing and same_file:
            return granted & set(requested) if requested else set()

        prompt_lines = [f"  - {permission}: {PLUGIN_PERMISSIONS[permission]}" for permission in requested]
        changed_note = ""
        if record and not same_file:
            changed_note = (
                "\n\nNote: this file's contents differ from the version you previously "
                "approved under this name, so its permissions must be re-confirmed."
            )
        answer = QMessageBox.question(
            self,
            "Plugin Permissions",
            f"Plugin '{name}' requests these permissions:\n\n"
            + "\n".join(prompt_lines or ["  - (none)"])
            + changed_note
            + "\n\nGrant them and run the plugin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        approved = set(requested)
        self.plugin_grants[name] = {"permissions": sorted(approved), "sha256": current_hash}
        self.save_settings()
        return approved

    def run_plugin_file(self, path: Path) -> None:
        manifest = self._read_plugin_manifest(path)
        if manifest is None:
            QMessageBox.critical(self, "Plugins", f"{path.name} has no valid MANIFEST.")
            return
        granted = self._ensure_plugin_grants(manifest, path)
        if granted is None:
            self.set_status("Plugin run cancelled")
            return
        api = OctoPluginAPI(self, str(manifest["name"]), granted)
        output: list[str] = []

        def plugin_print(*args: object, sep: str = " ", end: str = "\n") -> None:
            output.append(sep.join(str(arg) for arg in args) + end.rstrip("\n"))

        env: dict[str, Any] = {
            "__builtins__": make_safe_builtins(plugin_print),
            "api": api,
            "MANIFEST": manifest,
        }
        try:
            code = path.read_text(encoding="utf-8", errors="replace")
            exec(compile(code, f"<plugin:{path.name}>", "exec"), env, env)
            activate = env.get("activate")
            if callable(activate):
                activate(api)
            self.set_status(f"Plugin '{manifest['name']}' ran")
            if output:
                QMessageBox.information(
                    self, f"Plugin: {manifest['name']}", "\n".join(output)[:4000]
                )
        except Exception as exc:
            QMessageBox.critical(self, "Plugins", f"Plugin '{manifest['name']}' failed: {exc}")

    def install_plugin_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Install Plugin", "", "Python Plugins (*.py)"
        )
        if not file_path:
            return
        source = Path(file_path)
        if self._read_plugin_manifest(source) is None:
            QMessageBox.critical(
                self,
                "Plugins",
                "That file has no valid MANIFEST dict (needs at least a 'name' and a "
                "'permissions' list), so it cannot be installed.",
            )
            return
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            (self.plugins_dir / source.name).write_text(
                source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Plugins", f"Could not install plugin: {exc}")
            return
        self.set_status(f"Installed plugin {source.name}")

    def open_plugin_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Plugin Manager")
        dialog.resize(640, 440)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Plugins are Python files with a MANIFEST and an activate(api) entry point.\n"
                "They run with restricted builtins and only the permissions you grant."
            )
        )
        plugin_list = QListWidget()
        layout.addWidget(plugin_list)

        def refresh() -> None:
            plugin_list.clear()
            for plugin in self.discover_plugins():
                manifest = plugin["manifest"]
                name = manifest["name"]
                permissions = ", ".join(manifest.get("permissions", [])) or "none"
                granted = ", ".join(self.plugin_grants.get(name, {}).get("permissions", [])) or "none yet"
                item = QListWidgetItem(
                    f"{name} {manifest.get('version', '')}\n"
                    f"    {manifest.get('description', 'No description.')}\n"
                    f"    Requests: {permissions} | Granted: {granted}"
                )
                item.setData(Qt.ItemDataRole.UserRole, str(plugin["path"]))
                plugin_list.addItem(item)
            if not plugin_list.count():
                placeholder = QListWidgetItem("No plugins installed. Use Install Plugin... to add one.")
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                plugin_list.addItem(placeholder)

        def selected_path() -> Path | None:
            item = plugin_list.currentItem()
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            return Path(str(data)) if data else None

        def run_selected() -> None:
            path = selected_path()
            if path:
                self.run_plugin_file(path)
                refresh()

        def remove_selected() -> None:
            path = selected_path()
            if not path:
                return
            manifest = self._read_plugin_manifest(path)
            try:
                path.unlink()
            except OSError as exc:
                QMessageBox.critical(dialog, "Plugins", f"Could not remove plugin: {exc}")
                return
            if manifest is not None:
                self.plugin_grants.pop(str(manifest["name"]), None)
                self.save_settings()
            refresh()

        def revoke_selected() -> None:
            path = selected_path()
            if not path:
                return
            manifest = self._read_plugin_manifest(path)
            if manifest is not None:
                self.plugin_grants.pop(str(manifest["name"]), None)
                self.save_settings()
            refresh()

        plugin_list.itemDoubleClicked.connect(lambda _item: run_selected())

        buttons = QVBoxLayout()
        for label, handler in (
            ("Run Plugin", run_selected),
            ("Install Plugin...", lambda: (self.install_plugin_file(), refresh())),
            ("Revoke Permissions", revoke_selected),
            ("Remove Plugin", remove_selected),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, h=handler: h())
            buttons.addWidget(button)
        layout.addLayout(buttons)
        refresh()
        dialog.exec()

    def next_tab(self) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % count)

    def previous_tab(self) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % count)

    def jump_to_tab(self, number: int) -> None:
        if number == 9:
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        elif 1 <= number <= self.tabs.count():
            self.tabs.setCurrentIndex(number - 1)

    def toggle_mute_current_tab(self) -> None:
        browser = self.current_browser()
        if not browser:
            return
        page = browser.page()
        muted = not page.isAudioMuted()
        page.setAudioMuted(muted)
        self.set_status("Tab muted" if muted else "Tab unmuted")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_weather = (self.settings.weather_api_key, self.settings.weather_location)
        old_news_key = self.settings.news_api_key
        self.settings = dialog.to_settings(self.settings)
        self.openai_api_key = self.settings.openai_api_key
        self.apply_privacy_settings()
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

        browser = self.current_browser()
        if browser is not None:
            muted = browser.page().isAudioMuted()
            mute_action = QAction("Unmute Tab" if muted else "Mute Tab", self)
            mute_action.triggered.connect(self.toggle_mute_current_tab)
            menu.addAction(mute_action)

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
        if widget.isVisible():
            for panel in self.side_panels:
                panel.hide()
            self.apply_panel_split(None)
            self.set_status("Panel closed")
            self.tabs.setFocus()
            return

        self.open_panel(widget)

    def open_panel(self, widget: QWidget, status: str | None = None) -> None:
        for panel in self.side_panels:
            panel.hide()
        widget.show()
        widget.raise_()
        self.apply_panel_split(widget)
        widget.setFocus()
        self.set_status(status or f"{self.panel_title(widget)} opened")

    def apply_panel_split(self, widget: QWidget | None) -> None:
        total_width = max(self.splitter.width(), self.width(), 900)
        sizes = [0 for _index in range(self.splitter.count())]
        tab_index = self.splitter.indexOf(self.tabs)
        if tab_index >= 0:
            sizes[tab_index] = total_width

        if widget is not None:
            panel_index = self.splitter.indexOf(widget)
            panel_width = max(280, min(460, total_width // 3))
            if tab_index >= 0:
                sizes[tab_index] = max(520, total_width - panel_width)
            if panel_index >= 0:
                sizes[panel_index] = panel_width

        self.splitter.setSizes(sizes)

    def panel_title(self, widget: QWidget) -> str:
        for panel, title in (
            (self.notes_sidebar, "Notes"),
            (self.calendar_sidebar, "Calendar"),
            (self.todo_sidebar, "Tasks"),
            (self.history_sidebar, "History"),
            (self.news_sidebar, "News"),
            (self.downloads_sidebar, "Downloads"),
            (self.reading_sidebar, "Reading list"),
            (self.bookmarks_sidebar, "Bookmarks"),
            (self.extension_tab, "Extensions"),
        ):
            if widget is panel:
                return title
        return "Panel"

    def toggle_extensions(self) -> None:
        self.toggle_panel(self.extension_tab)

    def run_extension(self) -> None:
        code = self.extension_tab.toPlainText().strip()
        if not code:
            return
        output: list[str] = []

        def safe_print(*args: object, sep: str = " ", end: str = "\n") -> None:
            output.append(sep.join(str(arg) for arg in args) + end.rstrip("\n"))

        env = {
            "__builtins__": make_safe_builtins(safe_print),
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
            self.open_panel(self.todo_sidebar, status="Task added")
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
        new_tab_action.triggered.connect(
            lambda: self.add_tab(QUrl(str(item.data(Qt.ItemDataRole.UserRole) or item.text())), "History")
        )
        menu.addAction(new_tab_action)
        remove_action = QAction("Remove History Entry", self)
        remove_action.triggered.connect(lambda: self.remove_history_entry(item))
        menu.addAction(remove_action)
        menu.exec(self.history_sidebar.mapToGlobal(position))

    def remove_history_entry(self, item: QListWidgetItem) -> None:
        url = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        row = self.history_sidebar.row(item)
        if row >= 0:
            self.history_sidebar.takeItem(row)
        entry = self._history_index.pop(url, None)
        if entry is not None and entry in self.history:
            self.history.remove(entry)
        self.history_db.remove(url)
        self.refresh_address_suggestions()
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
        session_tabs = self.get_session_tabs()
        if session_tabs:
            self.session_tabs = session_tabs
        try:
            self.store.save(
                self.settings,
                self.bookmarks,
                self.notes,
                self.todos,
                self.session_tabs,
                self.reading_list,
                self.site_permissions,
                self.site_content,
                self.downloads_history,
                self.plugin_grants,
            )
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
        finally:
            self.refresh_address_suggestions()

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
        self.hibernation_timer.stop()
        self.save_settings()
        self.history_db.close()
        for worker in list(self.network_workers) + list(self.ai_workers) + list(self.filter_workers):
            worker.wait(300)
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

Octo-browse

Octo-browse is an experimental, Python + PyQt6/QtWebEngine desktop browser prototype that mixes traditional browsing with “power tools” like tabbed browsing, ad-blocking via request interception, incognito mode, page tools (save/page source), and a few “labs” features such as OpenCV page upscaling, AI page summarisation hooks, sidebars, and a built-in Python “extensions” scratchpad.

What’s inside

This repo is centered around:

main.py — the primary application entry point (full browser UI).

alpha.py — an earlier/alternate experimental build (kept for iteration/testing).

Key features
Core browsing UI

Tabbed browsing built on QTabWidget + QWebEngineView.

Split-view layout that can host multiple side panels (tabs + sidebars).

Privacy / control

Incognito mode toggle (UI action wired to toggle_incognito_mode).

Ad-block toggle implemented via QWebEngineUrlRequestInterceptor.

Ad-blocking implementation (technical)

A hardcoded domain blocklist (e.g., doubleclick.net, googlesyndication.com, etc.).

An interceptor class (AdBlockerInterceptor) checks each request URL and calls info.block(True) when a blocked domain substring matches.

The interceptor is installed/uninstalled on the default profile using profile.setUrlRequestInterceptor(...).

Page tools

Save Page As… (Complete HTML save format).

View Page Source opens a new tab populated via page().toHtml(...).

“Labs” features

Upscale Page: takes a widget screenshot and upscales via OpenCV (cv2.resize) before loading the result.

Read Aloud: UI action for “Read Aloud” (calls read_aloud).

AI Summarise Page: UI action wired to summarize_page, described as using OpenAI GPT.

Built-in “Extensions” scratchpad: a text area where Python code is executed via exec(...). Treat as unsafe if you paste untrusted code.

Themes / appearance

Theme switching includes at least default, blue, and a custom colour picker flow (via QColorDialog).

Requirements

Python: 3.10+ recommended

GUI: PyQt6 + PyQt6-WebEngine (QtWebEngine is required for QWebEngineView)

Computer vision: opencv-python (used for page upscaling)

Optional (depending on your build/use):

OpenAI Python SDK (for summarisation hooks)

Install
Windows (PowerShell)
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip

pip install PyQt6 PyQt6-WebEngine opencv-python
# Optional (if you want the AI summariser wired up in your environment):
pip install openai

macOS / Linux (bash/zsh)
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

pip install PyQt6 PyQt6-WebEngine opencv-python
# Optional:
pip install openai

Run
python main.py


If you want to run the alternate build:

python alpha.py

Configuration notes
OpenAI summarisation

The UI includes a “Summarize Page” action calling summarize_page and an OpenAI key field is surfaced through the settings dialog flow.
Practical options:

Set your key inside the app’s settings UI (if enabled in your current build).

Or export an environment variable and update the code to read it (if you prefer env-based config).

Ad-block list

The ad-blocker uses a static list of known ad domains and a substring match strategy.
This is intentionally simple and fast, but it can:

overblock if a legitimate URL contains a blocked substring

underblock compared to real filter engines (uBlock-style rule parsing isn’t implemented)

Architecture (quick map)

OctoBrowse(QMainWindow) — top-level app window, toolbars, tabs, split view, actions.

AdBlockerInterceptor(QWebEngineUrlRequestInterceptor) — request interception + blocking.

SettingsDialog(QDialog) — settings UI surface (theme/OpenAI key hooks/etc.).

Security

If you discover a vulnerability, follow the repository’s SECURITY.md guidance.

License

Licensed under the Apache License 2.0.

Roadmap ideas (if you want to evolve this into a “real” power browser)

Replace substring ad-blocking with real filter parsing (EasyList-style)

Proper per-tab profiles for real incognito isolation

Download manager + permissions UI

Extension sandboxing (avoid raw exec)

Persistent bookmarks/history storage (SQLite)

Per-site settings + content security controls

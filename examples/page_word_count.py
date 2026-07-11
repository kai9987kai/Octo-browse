"""Example OctoBrowse plugin: shows a word count for the current page.

Install it via Tools > Plugin Manager > Install Plugin..., then run it.
Python plugins are trusted local automation and require Developer Mode.
Manifest permissions document intended use of the `api` object; they are not a
security sandbox. See PLUGIN_PERMISSIONS in main.py for the full list.
"""

MANIFEST = {
    "name": "Page Word Count",
    "version": "1.0",
    "description": "Counts the words on the current page and shows a summary.",
    "permissions": ["page", "ui"],
}


def activate(api):
    def report(text):
        words = len(text.split())
        api.show_message("Word Count", f"{api.page_title()}\n{words} words on this page.")

    api.get_page_text(report)

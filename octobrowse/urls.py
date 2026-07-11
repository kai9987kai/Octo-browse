"""URL classification helpers shared by browser state and tests."""

from __future__ import annotations

from urllib.parse import urlsplit


INTERNAL_HTTPS_HOST = "octobrowse.local"


def is_internal_url(url: str) -> bool:
    """Return whether *url* is an OctoBrowse-owned or ephemeral browser URL.

    Host comparisons are exact.  A hostile page containing ``octobrowse.local``
    in its path, query, or a longer hostname is still an ordinary web page.
    """
    text = str(url or "").strip()
    if not text:
        return True
    try:
        parsed = urlsplit(text)
    except ValueError:
        return False
    scheme = parsed.scheme.lower()
    if scheme in {"about", "data", "octo"}:
        return True
    return scheme == "https" and (parsed.hostname or "").lower() == INTERNAL_HTTPS_HOST


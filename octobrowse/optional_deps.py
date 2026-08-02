"""Deferred loading for OctoBrowse's optional runtime dependencies.

Importing ``openai``, ``gtts``, ``speech_recognition``, ``requests`` and
``cryptography`` at module scope costs well over a second of cold start for
features most launches never touch — ``openai`` alone is more than half of
``import main``, and it is referenced only inside a background QThread.

This module defers that cost to first use.  ``available()`` answers "could this
be loaded?" without importing anything, so UI guards stay cheap; ``load()``
performs and caches the real import, returning ``None`` when the dependency is
absent so callers keep the same optional-feature behaviour they had when these
were guarded ``try: import`` blocks.

Frozen builds need care in both directions.  PyInstaller cannot see an import
that only happens at runtime, so every name here must also appear as a
``--hidden-import`` in ``packaging/build_common.ps1``.  And ``find_spec`` is
unreliable under PyInstaller's importer, so ``available()`` falls back to an
actual load attempt when running frozen.
"""

from __future__ import annotations

import functools
import importlib
import importlib.util
import sys
from types import ModuleType


__all__ = ["available", "load", "reset_cache"]


#: Dependencies deferred by this module, mapped to the pip distribution that
#: provides them, so error messages can tell the user what to install.
OPTIONAL_DISTRIBUTIONS = {
    "cryptography.fernet": "cryptography",
    "gtts": "gTTS",
    "openai": "openai",
    "requests": "requests",
    "speech_recognition": "SpeechRecognition",
}


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


@functools.cache
def load(name: str) -> ModuleType | None:
    """Import ``name`` once and cache it; return ``None`` if unavailable.

    Any import-time failure is treated as "feature not installed", matching the
    ``except ImportError`` blocks this replaced.  A dependency whose own import
    raises something other than ``ImportError`` would otherwise take down an
    unrelated part of the browser.
    """

    try:
        return importlib.import_module(name)
    except Exception:
        return None


def available(name: str) -> bool:
    """Whether ``name`` can be imported, without importing it when avoidable.

    Under a frozen build ``find_spec`` cannot be trusted, so this falls back to
    a real (cached) load there.
    """

    if name in sys.modules:
        return True
    if _frozen():
        return load(name) is not None
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def reset_cache() -> None:
    """Clear the memoized loads. Intended for tests."""

    load.cache_clear()

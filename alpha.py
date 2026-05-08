#!/usr/bin/env python3
"""
Compatibility launcher for the former alpha build.

The alpha-only features have been merged into main.py so both entry points now
start the same maintained OctoBrowse application.
"""

from main import main


if __name__ == "__main__":
    raise SystemExit(main())

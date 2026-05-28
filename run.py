"""PyInstaller entry-point shim.

When PyInstaller treats ``src/screen_recorder/__main__.py`` as the top-level
script directly, its relative imports (``from .assets import …``) fail because
there is no parent package in scope. We use this tiny launcher instead so the
``screen_recorder`` package is imported normally and relative imports work.
"""

from __future__ import annotations

from screen_recorder.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())

"""Console-script entry point for the Tkinter frontend."""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    try:
        if __package__:
            from .app import run_app
        else:  # PyInstaller executes the entry script as __main__.
            from photo_date_restore.gui.app import run_app
    except ImportError as exc:
        print(f"error: GUI requires tkinter: {exc}", file=sys.stderr)
        return 3
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())

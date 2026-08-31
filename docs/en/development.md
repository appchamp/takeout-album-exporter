# GUI Development Guide

Japanese: [../ja/development.md](../ja/development.md)

This document is for developers who build `Photo Date Restore.app` from source. Python, Tk, and PyInstaller are not needed to use the distributed `.app`; see [usage.md](usage.md) for the end-user workflow.

## Requirements

- Python 3.14 with Tk
- PyInstaller
- ExifTool (an external runtime dependency)

On macOS, installing `python-tk@3.14` through Homebrew also installs `python@3.14` and `tcl-tk` as dependencies.

```bash
brew install python-tk@3.14
brew install exiftool
```

## GUI environment and build

At the repository root, prepare the external GUI environment at `$HOME/.venvs/takeout-album-exporter/gui`, refresh the installed package metadata, then build.

```bash
"$HOME/.venvs/takeout-album-exporter/gui/bin/pip" install -e . --no-deps
"$HOME/.venvs/takeout-album-exporter/gui/bin/pyinstaller" --noconfirm packaging/photo-date-restore-gui.spec
```

The result is `dist/Photo Date Restore.app`. The build uses `packaging/photo-date-restore-gui.spec`.

The app's About information and bundle version (`CFBundleShortVersionString` / `CFBundleVersion`) come from installed package metadata. After changing the version, always repeat the editable install above before building.

The launched `.app` does not bundle ExifTool; it searches `PATH`, `/opt/homebrew/bin`, then `/usr/local/bin`.

For distribution ZIP creation, verification, and manual GUI testing, see [release.md](release.md).

# Photo Date & Metadata Restorer for Google Photos with Google Takeout

Japanese: [README-ja.md](README-ja.md)

Version 1.1.0 / MIT License / <https://github.com/kimipooh/takeout-album-exporter>

This safety-oriented Python CLI restores and adjusts missing capture timestamps and filesystem `mtime` for photos and videos exported from Google Photos Takeout. It uses Google JSON metadata alongside existing EXIF/XMP metadata. An Apple Silicon build of `Photo Date Restore.app` provides the same workflow through a macOS GUI.

[Use the macOS GUI](#gui-version-macos) | [Use the CLI](#quick-start)

- Detailed guide: [docs/en/usage.md](docs/en/usage.md) (translated from the canonical Japanese [docs/ja/usage.md](docs/ja/usage.md))
- Build the GUI from source: [docs/en/development.md](docs/en/development.md)
- Maintainer release procedure: [docs/en/release.md](docs/en/release.md)
- Design and safety specification: [docs/en/design.md](docs/en/design.md)

## How to use the app version (macOS Apple Silicon)

1. Download the Apple Silicon ZIP from [GitHub Releases](https://github.com/kimipooh/takeout-album-exporter/releases).
2. Extract the ZIP.
3. Install ExifTool: `brew install exiftool`
4. Open `Photo Date Restore.app` and begin with a dry run.

The distributed `.app` includes the Python/Tk runtime, so end users do not need to install Python, Tk, or PyInstaller. See the [GUI section](#gui-version-macos) and [usage guide](docs/en/usage.md) for details.

## Overview

Google Takeout can separate a photo from its capture time:

```text
photo.jpg
photo.jpg.supplemental-metadata.json
```

The tool uniquely matches JSON in the same directory and does not overwrite a trustworthy existing capture time. When a JSON `photoTakenTime` is uniquely matched and timezone evidence is sufficient, it restores the capture time and writes `DateTimeOriginal` / `CreateDate` for JPEG/TIFF. If a JPEG/TIFF originally has no EXIF, ExifTool may create a new EXIF metadata block. When timezone cannot be determined, it does not guess or write capture metadata and repairs only `mtime`. It never uses JSON `creationTime` as capture time.

## Features

- Restores capture datetime and filesystem `mtime` for Google Photos images and videos by matching sidecar JSON against existing EXIF/XMP; with sufficient evidence, JPEG/TIFF can gain missing EXIF capture timestamps, and a new EXIF metadata block may be created when none existed
- Dry run by default; writes only when `--apply` is given explicitly
- Copy mode first, leaving the original data untouched (the GUI is copy mode only)
- Verbose output with a user-facing explanation for each processed file
- Audit report (CSV / JSONL) recording the internal statuses
- Safety-first timezone handling that uses only evidence-backed timezones
- ExifTool-based metadata read/write with read-back verification
- macOS GUI (distributed as a `.app`), Cancel during a run, and an About dialog

## Required and recommended software by workflow

### Using the macOS GUI

- **Required:** ExifTool only
- **Not required:** Python, Tk, or PyInstaller; the distributed `.app` includes the Python/Tk runtime
- **Recommended:** Download the Apple Silicon ZIP from GitHub Releases and install ExifTool through Homebrew

### Using the CLI

- **Required:** Python 3.9 or later and ExifTool
- **Recommended:** a Python virtual environment and a package manager such as Homebrew
- See the [usage guide](docs/en/usage.md) for options, the safe workflow, and troubleshooting.

### Building the GUI from source

This is a developer workflow and needs Python 3.14 with Tk, PyInstaller, and a GUI virtual environment. See the [development guide](docs/en/development.md), rather than treating those as requirements for the distributed app.

## Homebrew and ExifTool

ExifTool is an external dependency for both the GUI and CLI and is not bundled in the `.app`. Homebrew is not required, but is a recommended package manager for macOS. If it is not installed, see the [official Homebrew site](https://brew.sh/).

```bash
brew install exiftool
exiftool -ver
```

The GUI looks briefly for ExifTool on `PATH`, `/opt/homebrew/bin`, and `/usr/local/bin`. It still opens when ExifTool is absent, then gives installation guidance when you press `Start`.

## Quick Start

This is the shortest CLI path. Run these commands **at the repository root**.

```bash
cd /path/to/takeout-photo-date-restorer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Test run (dry-run)

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv"
```

No photos are copied and no EXIF or `mtime` changes are made. Review the report.

### Actual run

After reviewing the dry-run report, add `--apply`.

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv" \
  --apply
```

`--output DIR` leaves the input unchanged and creates repaired copies in another directory when used with `--apply`. See the [usage guide](docs/en/usage.md) for the complete workflow.

### Verbose output and audit reports

Add `-v` / `--verbose` to print a user-facing explanation for each processed file, including during a dry run. `--report` saves a CSV / JSONL audit report containing the unchanged internal statuses.

## GUI version (macOS)

To use the distributed `Photo Date Restore.app`, install only ExifTool. Download the ZIP from [GitHub Releases](https://github.com/kimipooh/takeout-album-exporter/releases), extract it, and open `Photo Date Restore.app`; Python/Tk is not needed.

The `.app` is unsigned and not notarized. If macOS warns on first launch, allow it in System Settings > Privacy & Security.

The GUI is copy mode only. Select Input and Output folders, keep the default-on dry run and Verbose output for the first pass, configure timezone, overwrite, and an audit report, then press `Start`. `Cancel` takes effect at the next metadata-read batch boundary or after the file currently being written, preserving partial results and the audit report. See [the GUI chapter of the usage guide](docs/en/usage.md#4-gui-version-macos) for details.

For launching or building the GUI from source, see the [development guide](docs/en/development.md).

## Safety notes

- Always proceed as **dry run → review report → apply → verify output**.
- Do not begin by running `--in-place --apply` against the original Google Takeout. `--in-place` is for a backed-up working copy.
- Use `--timezone Asia/Tokyo` only for an album known to have been captured in Japan. Do not apply it without evidence to a whole Takeout that might include overseas photos.
- `--move-json` is for advanced use. It archives successful sidecars; it does not delete JSON.

## Author

Kimiya Kitani

## Project

<https://github.com/kimipooh/takeout-album-exporter>

## License

MIT License. Copyright (c) 2026 Kimiya Kitani. See [LICENSE](LICENSE).

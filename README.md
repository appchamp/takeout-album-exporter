# Photo Date & Metadata Restorer for Google Photos with Google Takeout

Japanese: [README-ja.md](README-ja.md)

Version 1.1.0 / MIT License / <https://github.com/kimipooh/takeout-album-exporter>

`photo-date-restore` tool is a safety-oriented Python CLI for matching media from a Google Photos Takeout export with sidecar JSON, then restoring missing capture timestamps and filesystem `mtime`. It prioritizes trustworthy existing EXIF/XMP capture metadata and uses JSON `photoTakenTime` only when needed.

- Detailed guide: [docs/en/usage.md](docs/en/usage.md) (translated from the canonical Japanese [docs/ja/usage.md](docs/ja/usage.md))
- Design and safety specification: [docs/en/design.md](docs/en/design.md)

## Overview

Google Takeout can separate a photo from its capture time:

```text
photo.jpg
photo.jpg.supplemental-metadata.json
```

The tool uniquely matches JSON in the same directory. It does not overwrite a trustworthy existing capture time, does not guess `DateTimeOriginal` when evidence is insufficient, and never uses JSON `creationTime` as capture time.

## Features

- Restores capture datetime and filesystem `mtime` for Google Photos images and videos by matching sidecar JSON against existing EXIF/XMP
- Dry run by default; writes only when `--apply` is given explicitly
- Copy mode first, leaving the original data untouched (the GUI is copy mode only)
- Verbose output with a user-facing explanation for each processed file
- Audit report (CSV / JSONL) recording the internal statuses
- Safety-first timezone handling that uses only evidence-backed timezones
- ExifTool-based metadata read/write with read-back verification
- macOS GUI (distributed as a `.app`), Cancel during a run, and an About dialog

## Installation (macOS example)

Run the following **at the repository root**. Replace `/path/to/takeout-photo-date-restorer` with the location of this repository.

```bash
cd /path/to/takeout-photo-date-restorer

python3 --version
python3 -m venv .venv
source .venv/bin/activate

python --version
which python

brew install exiftool
exiftool -ver

python -m pip install -e .
python -m photo_date_restore --help
```

`pyproject.toml` requires Python **3.9 or later**. Without activating the virtual environment, you can still run `.venv/bin/python -m photo_date_restore` from the repository root.

`photo-date-restore` is a shorthand available only when the installed console script is reachable from the current `PATH`. This guide uses `python -m photo_date_restore` as the primary, environment-independent form.

Without ExifTool, the CLI stops before processing. On macOS, install it with `brew install exiftool` as shown above.

## Quick Start

Copy this and replace only the paths.

```bash
cd /path/to/takeout-photo-date-restorer

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -e .
```

### Test run (dry-run)

First, review what would happen without changing any files.

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv"
```

At this stage, no photos are copied, and no EXIF or `mtime` changes are made. Review the report.

### Actual run

Review the dry-run report, and if it looks correct, add `--apply`.

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv" \
  --apply
```

`--output DIR` leaves the input unchanged and creates repaired copies in another directory when `--apply` is used. It is the recommended mode for protecting an original Takeout. See the [usage guide](docs/en/usage.md) for the full procedure, timezone, reports, in-place mode, JSON archiving, and troubleshooting.

### Verbose output

Add `-v` / `--verbose` to print a user-facing explanation for each processed file, including during a dry run. Without it, the output remains the final summary only.

### Audit report

Use `--report` to save a CSV / JSONL audit report. The report records the internal statuses (`EXIF_JSON_MATCH_TZ_GPS`, `JSON_TIME_MTIME_ONLY`, and so on) exactly as produced. The verbose display is a user-facing rewording and is a separate thing from the report's internal statuses. Use the report when you need to verify results afterwards.

## GUI version (macOS)

The GUI requires Python with Tk and ExifTool. On macOS with Homebrew, install them as follows. ExifTool is required and is not bundled with the application.

```bash
brew install python-tk@3.14
brew install exiftool
```

After installing the package, launch it with either command:

```bash
photo-date-restore-gui
python -m photo_date_restore.gui
```

The window offers the following controls:

- `Input folder` / `Output folder`
- `Dry run (analyze only, write nothing)` — **on by default**
- `Verbose output (show each processed file)` — **on by default**
- `Overwrite existing files in output folder`
- Save an audit report (CSV / JSONL)
- `Start` / `Cancel`
- `Open Output Folder`

Select the Input and Output folders, then set the default-on Verbose output and dry run, timezone, output overwrite, and an audit report (CSV / JSONL), and press `Start`. ExifTool metadata is read in batches of up to 100 files per directory, so the log shows reading progress (`[100/1896] Reading metadata...`) before switching to `Analyzing:` and the user-facing per-file results, even in dry-run mode. `Cancel` reacts at the next batch boundary — typically within one batch of metadata reads, or after the current file being written — preserving completed partial results and their audit report. After completion, the log shows the summary directly in the main window (no separate popup); `Open Output Folder` opens the destination in Finder.

The About item in the application menu or Help menu shows the Version, author, MIT License, and Project URL.

The GUI is copy mode only. `--in-place` and `--move-json` remain CLI-only. The CLI arguments and behavior are unchanged and remain fully supported.

### ExifTool (external dependency)

ExifTool is an external dependency and is not bundled in the `.app`. Install it separately, for example with Homebrew:

```bash
brew install exiftool
```

At startup the application detects ExifTool in this order:

1. `exiftool` on `PATH`
2. `/opt/homebrew/bin/exiftool` (Apple Silicon Homebrew)
3. `/usr/local/bin/exiftool` (Intel Homebrew)

If none is found the GUI still launches and stops at `Start` with installation guidance.

### Download the macOS app (.app)

A prebuilt ZIP for Apple Silicon is attached to the GitHub Release:

`Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip`

This `.app` is unsigned and not notarized. macOS may show a security warning the first time you open it; if so, allow it from System Settings > Privacy & Security. ExifTool must be installed separately.

### Build the `.app`

From the repository root, use the GUI development `.venv-gui`:

```bash
./.venv-gui/bin/pip install -e . --no-deps
./.venv-gui/bin/pyinstaller --noconfirm packaging/photo-date-restore-gui.spec
```

The result is `dist/Photo Date Restore.app`. `dist/` is generated output and is not tracked by Git.

For how to build the release ZIP and compute its checksums, see "4.4 Building and verifying the release ZIP" in [docs/en/usage.md](docs/en/usage.md).

## Safety notes

- Always proceed as **dry run → review report → apply → verify output**.
- Do not begin by running `--in-place --apply` against the original Google Takeout. `--in-place` is for a backed-up working copy.
- Use `--timezone Asia/Tokyo` only for an album known to have been captured in Japan. Do not apply it without evidence to a whole Takeout that might include overseas photos.
- `--move-json` is for advanced use. It archives successful sidecars; it does not delete JSON.

## Representative examples

The development samples are read-only. Never run `--in-place --apply` against `sources/Takeout`.

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/Album A" \
  --output "./test-output/group-photo" \
  --report "./reports/group-photo.csv"
```

When the timezone cannot be determined, `JSON_TIME_MTIME_ONLY` restores only `mtime` and does not write capture-time metadata. Use the detailed guide's `--timezone Asia/Tokyo --apply` example only when capture in Japan is confirmed.

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/Album B" \
  --output "./test-output/library-fair" \
  --report "./reports/library-fair.csv"
```

`EXIF_JSON_MATCH_TZ_GPS` means existing metadata and JSON agree with GPS-based timezone evidence; `EXIF_JSON_MATCH_TZ_INFERRED` means they agree using same-directory evidence. Existing EXIF/XMP is not overwritten.

For details, see [docs/en/usage.md](docs/en/usage.md).

## Author

Kimiya Kitani

## Project

<https://github.com/kimipooh/takeout-album-exporter>

## License

MIT License. Copyright (c) 2026 Kimiya Kitani. See [LICENSE](LICENSE).

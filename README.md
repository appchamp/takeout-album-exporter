# Photo Date & Metadata Restorer for Google Photos with Google Takeout

Japanese: [README-ja.md](README-ja.md)

`photo-date-restore` tool is a safety-oriented Python CLI for matching media from a Google Photos Takeout export with sidecar JSON, then restoring missing capture timestamps and filesystem `mtime`. It prioritizes trustworthy existing EXIF/XMP capture metadata and uses JSON `photoTakenTime` only when needed.

- Detailed guide (canonical Japanese source): [docs/en/usage.md](docs/en/usage.md)
- Design and safety specification: [docs/ja/design.md](docs/ja/design.md)

## Overview

Google Takeout can separate a photo from its capture time:

```text
photo.jpg
photo.jpg.supplemental-metadata.json
```

The tool uniquely matches JSON in the same directory. It does not overwrite a trustworthy existing capture time, does not guess `DateTimeOriginal` when evidence is insufficient, and never uses JSON `creationTime` as capture time.

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

Add `-v` / `--verbose` to print a user-facing explanation for each processed file, including during a dry run. Without it, the output remains the final summary only. Detailed internal statuses remain unchanged in the audit report.

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

Select the Input and Output folders, then set the default-on Verbose output and dry run, timezone, output overwrite, and an audit report (CSV / JSONL), and press `Start`. ExifTool metadata is read in batches of up to 100 files per directory, so the log shows reading progress (`[100/1896] Reading metadata...`) before switching to `Analyzing:` and the user-facing per-file results, even in dry-run mode. `Cancel` reacts at the next batch boundary — typically within one batch of metadata reads, or after the current file being written — preserving completed partial results and their audit report. After completion, the log shows the summary directly in the main window (no separate popup); `Open Output Folder` opens the destination in Finder.

The About item in the application menu or Help menu shows the Version, author, MIT License, and Project URL.

The GUI is copy mode only. `--in-place` and `--move-json` remain CLI-only. The CLI arguments and behavior are unchanged and remain fully supported.

### Build the `.app`

From the repository root, use the GUI development `.venv-gui`:

```bash
./.venv-gui/bin/pyinstaller --noconfirm packaging/photo-date-restore-gui.spec
```

The result is `dist/Photo Date Restore.app`. The `.app` does not include ExifTool; at startup it searches `PATH`, `/opt/homebrew/bin`, and `/usr/local/bin` for it.

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

## License

MIT License. See [LICENSE](LICENSE).

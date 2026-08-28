# photo-date-restore Usage Guide

日本語: [../ja/usage.md](../ja/usage.md)

This guide translates the canonical Japanese document. For a short introduction see [README.md](../../README.md); for design and safety decisions see [the Japanese design specification](../ja/design.md).

## 1. Rules to follow first

Keep a separate copy of the original Google Takeout. Do not start by running `--in-place --apply` on the original. Normally, use `--output DIR`, which leaves the input unchanged. Always proceed in this order:

1. dry run
2. review the report
3. apply
4. verify the output

Any command without `--apply` is a dry run. It changes no media, EXIF/XMP, `mtime`, JSON, or output directory. A dry run with `--report` creates only the report file.

The tool does not use JSON `creationTime` or filenames as capture times, and it does not guess a timezone without evidence. When timezone is unknown, it may still repair only `mtime` from the UTC instant in JSON `photoTakenTime`.

## 2. Installation (from the beginning, macOS primary example)

Run every command below **at the repository root**. First move there.

```bash
cd /path/to/takeout-photo-date-restorer
```

### 2.1 Check Python

```bash
python3 --version
```

`pyproject.toml` declares `requires-python = ">=3.9"`. Python 3.9 or later is required. On macOS, use `python3` before the virtual environment is created.

### 2.2 Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate

python --version
which python
```

After activation, `which python` normally points to `.venv/bin/python`. Use `python` in that activated environment.

In Windows PowerShell, at the same repository root, use:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2.3 Install ExifTool

On macOS, this is the Homebrew example:

```bash
brew install exiftool
exiftool -ver
```

Without ExifTool, the CLI stops before processing with `ExifTool executable not found`. It is required to safely read and write photo metadata. You can also select another executable with `--exiftool PATH`.

### 2.4 Install the package and verify it

```bash
python -m pip install -e .
python -m photo_date_restore --help
```

`python -m photo_date_restore` is the primary launch method in this guide. If you did not activate the virtual environment, start it reliably from the repository root as follows:

```bash
.venv/bin/python -m photo_date_restore --help
```

Installation also creates the `photo-date-restore` console script. It is a **shorthand only when installed and available through the current `PATH`**. You can check it:

```bash
photo-date-restore --help
```

Because some environments report `photo-date-restore: command not found`, all remaining examples use `python -m photo_date_restore`.

## 3. Quick Start: only these steps first

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

No photos are copied, no EXIF/XMP is changed, and no `mtime` is changed. It only shows what would be done. Review the report.

### Actual run

If it is safe, add `--apply` with the same conditions.

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv" \
  --apply
```

## 4. GUI version (macOS)

The GUI is a screen for the existing CLI copy mode. CLI arguments and behavior are unchanged and remain fully supported. The GUI does not expose `--in-place` or `--move-json`; those remain CLI-only.

### 4.1 Requirements and launch

Python 3.14 with Tk and ExifTool are required. ExifTool is not bundled in the `.app`.

```bash
brew install python-tk@3.14
brew install exiftool

photo-date-restore-gui
# or
python -m photo_date_restore.gui
```

### 4.2 Use

1. Select the Input and Output folders.
2. Start with the default `Dry run (analyze only, write nothing)` and default-on `Verbose output (show each processed file)`, then set timezone, output overwrite, and a CSV / JSONL audit report.
3. Press `Start` and review user-facing per-file results, including in dry-run mode, and the directory being read in the log. Detailed internal statuses remain unchanged in the audit report. To stop, press `Cancel`: it safely waits for the current file to finish and preserves completed partial results and their audit report. Use the application menu or Help menu About item to confirm the Version, author, MIT License, and Project URL.
4. After the completion display, use `Open Output Folder` to open the destination in Finder.

### 4.3 Build the `.app`

At the repository root, use the GUI development environment:

```bash
./.venv-gui/bin/pip install -e . --no-deps
./.venv-gui/bin/pyinstaller --noconfirm packaging/photo-date-restore-gui.spec
```

The `.app` reads its Version and Project URL from the installed package metadata. If you skip the reinstall after changing the version, About shows stale values, so always reinstall before building.

The result is `dist/Photo Date Restore.app`. The launched `.app` does not bundle ExifTool and searches `PATH`, `/opt/homebrew/bin`, then `/usr/local/bin`.

### 4.4 Manual GUI test checklist

- The GUI launches.
- Input and Output folders can be selected.
- Dry run, default-on Verbose output, timezone, output overwrite, and audit-report toggles work.
- Verbose output shows one user-facing line for each processed file, including during dry-run; internal statuses remain in the report.
- Cancel waits safely for the current file, then preserves partial results and the report.
- The application menu or Help menu About item shows the Version, author, MIT License, and Project URL.
- With ExifTool present, its path appears in the log.
- With ExifTool absent, startup continues and Start gives a clear failure.
- Start in dry-run and confirm that no output is created.
- Start with apply and confirm copy-mode output.
- After invalid input, recover from the error and start again.
- After success, `Open Output Folder` is enabled and opens Finder.

## 5. `--output` and dry run / apply

Besides `INPUT`, exactly one of `--output DIR` or `--in-place` is required.

```text
python -m photo_date_restore INPUT (--output DIR | --in-place) [OPTIONS]
```

`--output DIR` is the recommended mode.

- It does not change the original input data.
- With `--apply`, it creates repaired media copies in another directory, preserving input-relative paths.
- In a dry run, specifying output does not create the output directory or media.
- Copy mode does not copy sidecar JSON to output.

Choose this mode to protect the original Takeout. With apply, media that cannot be repaired because of a conflict and similar conditions may still be copied unchanged. Different existing output produces `OUTPUT_EXISTS` by default and is not overwritten.

| Option | Role |
| --- | --- |
| `--output DIR` | Write to another directory; mutually exclusive with and preferred over `--in-place` |
| `--in-place` | Process the input in place; use only on a working copy |
| `--apply` | Actually copy, write, and move; without it the run is dry |
| `-v`, `--verbose` | Show one progress line for each processed file |
| `--timezone NAME` | IANA timezone name, for example `Asia/Tokyo` |
| `--report PATH` | CSV or JSONL audit report |
| `--move-json DIR` | Archive successful sidecars; in-place only |
| `--exiftool PATH` | Select the ExifTool executable |

To show file-by-file progress during a dry run, add `-v` or `--verbose`:

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  -v
```

## 6. Handle timezone safely

JSON `photoTakenTime.timestamp` is an absolute UTC instant. `DateTimeOriginal`, on the other hand, is usually a local wall-clock value without a timezone. Writing UTC digits directly can shift the capture time by hours.

### When no timezone option is needed

No option is needed when the tool can safely determine timezone from an existing EXIF offset, GPS UTC time, or sufficient same-directory evidence. Trustworthy existing capture metadata is not overwritten with JSON.

### When a timezone option is needed

Use it when there is no EXIF capture time, only JSON `photoTakenTime`, and the capture location is known — for example, an album known to have been shot in Japan.

#### Test run (dry-run)

```bash
python -m photo_date_restore \
  "/path/to/Album" \
  --output "./output" \
  --timezone Asia/Tokyo
```

#### Actual run

Review the report, then apply under the same conditions if it looks correct.

```bash
python -m photo_date_restore \
  "/path/to/Album" \
  --output "./output" \
  --timezone Asia/Tokyo \
  --apply
```

### When not to specify it

Do not add this without evidence to a complete Google Photos tree that may contain overseas photos:

```text
--timezone Asia/Tokyo
```

When timezone is unknown, omit it and examine `JSON_TIME_MTIME_ONLY` in the report. Apply can safely repair only `mtime`; it does not write local capture metadata.

## 7. `--in-place` (advanced)

**Do not run in-place against the original Google Takeout from the start.** First make a backup or use a working copy made with copy mode.

### Test run (dry-run)

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place
```

### Actual run

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place \
  --apply
```

An interactive terminal asks for confirmation. Add `--yes` only for deliberate automation. After an ExifTool write, `<file>_original` remains until read-back verification succeeds; on failure the tool restores it and reports `VERIFY_FAILED`.

## 8. How to read the report

Look at **`status` first**. Then inspect the evidence, planned action, and timestamps.

| Column | Why inspect it first |
| --- | --- |
| `file` | Target file |
| `status` | Final decision and the next action to take |
| `existing_datetime` | Existing capture time |
| `existing_datetime_source` | Tag/evidence for the existing time |
| `json_photo_taken_time` | UTC absolute instant from JSON |
| `selected_datetime` | Chosen capture time; may be blank when timezone is unknown |
| `selected_datetime_source` | Source, existing tag or `PHOTO_TAKEN_TIME` |
| `timezone_source` | `EXPLICIT`, `GPS`, `INFERRED`, `CLI`, or `NONE` |
| `difference_seconds` | EXIF/JSON difference; `32400` is nine hours |
| `planned_metadata_action` | For example `WRITE`, `SKIP_TIMEZONE_REQUIRED`, or `NONE` |
| `planned_mtime_action` | `SET` means apply will set `mtime` |
| `new_mtime` | UTC absolute instant that apply would set |

In a dry run, focus on `planned_*` and `new_mtime`. A `.csv` report defaults to UTF-8 with BOM; a `.jsonl` report is JSONL.

### Statuses and what to do

| Status | Meaning | What you should do |
| --- | --- | --- |
| `NO_CHANGE` | No repair needed or already correct | Leave it alone |
| `OK_EXIF` | Trustworthy existing time; JSON time is unavailable | Keep existing value |
| `EXIF_JSON_MATCH` | EXIF and JSON agree within tolerance | Normally leave it alone |
| `EXIF_JSON_MATCH_TZ_EXPLICIT` | Explicit offset or CLI timezone explains the difference | Normally leave it alone |
| `EXIF_JSON_MATCH_TZ_GPS` | GPS explains the timezone difference | Normally leave it alone |
| `EXIF_JSON_MATCH_TZ_INFERRED` | Same-directory evidence explains the timezone difference | Normally leave it alone |
| `EXIF_JSON_POSSIBLE_TZ` | Looks like a timezone difference but evidence is weak | Keep existing value; inspect if needed |
| `EXIF_JSON_CONFLICT` | Difference cannot be explained safely | Inspect before apply; no automatic repair |
| `JSON_TIME_USED` | JSON can safely restore the time | Candidate for apply |
| `JSON_TIME_MTIME_ONLY` | Timezone is missing, so metadata cannot be written | Add timezone only if location is known; otherwise apply only mtime if desired |
| `NO_JSON` | No matching sidecar | Check layout or whether it was archived |
| `NO_DATE` | No trustworthy existing time or `photoTakenTime` | Inspect manually; never use `creationTime` |
| `AMBIGUOUS_JSON` | JSON mapping is not unique | Do not repair automatically |
| `OUTPUT_EXISTS` | A different output file exists | Compare it; do not casually overwrite |
| `VERIFY_FAILED` | Read-back verification failed | Check `error`; in-place is restored |
| `ERROR` | Malformed JSON, I/O, or another processing error | Check `error` and `message`, then correct the cause |

`UNSUPPORTED` and `SKIPPED` are enum values but are not normally emitted by the current standard path. Unsupported HEIC/video metadata writes normally appear as `UNSUPPORTED_FORMAT_FOR_METADATA(...)` in `message`.

## 9. Real-data examples (read-only)

The following `sources/Takeout/...` paths are development samples. Substitute your paths as a normal user. Never use `--in-place --apply` on these samples.

### Album A

#### Test run (dry-run)

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/Album A" \
  --output "./test-output/group-photo" \
  --report "./reports/group-photo.csv"
```

When the timezone cannot be determined, `JSON_TIME_MTIME_ONLY` restores only `mtime` and does not change capture-time metadata.

#### Actual run (only when capture in Japan is known)

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/Album A" \
  --output "./test-output/group-photo" \
  --timezone Asia/Tokyo \
  --report "./reports/group-photo-apply.csv" \
  --apply
```

### Album B

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/Album B" \
  --output "./test-output/library-fair" \
  --report "./reports/library-fair.csv"
```

`EXIF_JSON_MATCH_TZ_GPS` means existing metadata and JSON agree with GPS-based timezone evidence; `EXIF_JSON_MATCH_TZ_INFERRED` means they agree using same-directory evidence.

Existing EXIF/XMP capture time is not overwritten here.

### Complete Google Photos tree

First dry run:

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト" \
  --output "./test-output/google-photos" \
  --report "./reports/google-photos.csv"
```

Normally do not specify timezone here. Read the report, then decide by album only where capture location is certain.

## 10. `--move-json` (advanced)

`--move-json` is in-place only. It archives JSON rather than deleting it. Its destination must be outside INPUT and outside the repository's `sources/` tree.

### Test run (dry-run)

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place \
  --move-json "/path/to/json-backup"
```

### Actual run

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place \
  --move-json "/path/to/json-backup" \
  --apply
```

- Only the uniquely matched sidecar of a fully successful media result is archived.
- Conflict, `ERROR`, `AMBIGUOUS_JSON`, `JSON_TIME_MTIME_ONLY`, and similar results do not move JSON.
- The archive preserves INPUT-relative paths and creates `_sidecar_index.csv`.
- JSON is not deleted. Rescanning INPUT after archiving returns `NO_JSON` because the sidecar is no longer there.
- A collision is not overwritten and is recorded as `planned_json_action=SKIP_DESTINATION_EXISTS`.

## 11. Common errors

### `photo-date-restore: command not found`

The console script is not on PATH. Run:

```bash
source .venv/bin/activate
python -m photo_date_restore --help
```

### `No module named photo_date_restore`

Confirm that you are at the repository root, then install the package:

```bash
python -m pip install -e .
```

### ExifTool not found

On macOS, install and check it:

```bash
brew install exiftool
exiftool -ver
```

### `invalid IANA timezone`

`Asia/Tokoyo` is incorrect. Use:

```text
Asia/Tokyo
```

### No output directory is created

This is normal in a dry run. After reviewing the report, add `--apply` to the same command to create output.

## 12. Safest recommended workflow

1. Preserve the original Google Takeout separately.
2. Move to the repository.
3. Create and activate `.venv`.
4. Check ExifTool.
5. Run `python -m pip install -e .`.
6. Dry run one album.
7. Review the report.
8. If needed, specify timezone only for an album with a known capture location.
9. Create repaired copies with `--output --apply`.
10. Check output media, report, and `mtime`.
11. Expand the scope only after that succeeds.

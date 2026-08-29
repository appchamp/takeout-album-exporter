# Release Procedure

Japanese: [../ja/release.md](../ja/release.md)

This document is for maintainers. End users should use [usage.md](usage.md).

## Create and verify the distribution ZIP

`dist/` is PyInstaller output and `release/` holds distribution ZIPs; neither is tracked by Git. Build the ZIP from `dist/Photo Date Restore.app` with macOS `ditto`. Do not use `zip`, which can drop extended attributes.

```bash
ditto -c -k --sequesterRsrc --keepParent \
  "dist/Photo Date Restore.app" \
  "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
```

Extract it and confirm that the `.app` launches.

```bash
mkdir -p /tmp/photo-date-restore-test
ditto -x -k \
  "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip" \
  /tmp/photo-date-restore-test
```

Calculate SHA-256 as the primary integrity value and MD5 as a supplementary check, then record them in the GitHub Release notes.

```bash
shasum -a 256 "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
md5 "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
```

Hashes change with each build, so do not embed them in the README or usage guide. The Apple Silicon (arm64) distribution is unsigned and not notarized; attach it to the GitHub Release manually.

## Manual GUI checks before release

- The GUI launches and Input / Output folders can be selected.
- Dry run, default-on Verbose output, timezone, output overwrite, and audit report toggles work.
- Verbose output shows each processed file during dry run while internal statuses remain in the report.
- A large directory shows progress from `Reading metadata:` to `Analyzing:`.
- Cancel stops safely at the next batch boundary or after the current file, retaining partial results and the report.
- No popup appears after normal completion or cancellation.
- About shows the Version, author, MIT License, and Project URL.
- With and without ExifTool, verify either its path or clear installation guidance.
- Dry run creates no output; apply creates copy-mode output.
- The app recovers from invalid input, and `Open Output Folder` opens Finder after success.

# Repository Instructions for Implementation Agents

## Project purpose

This repository provides `photo-date-restore`, a safety-first Python CLI for Google Takeout / Google Photos exports. It parses Google Photos sidecar JSON, matches each sidecar to exactly one media file, preserves trustworthy existing EXIF/XMP metadata, restores missing capture time from JSON `photoTakenTime`, repairs filesystem `mtime`, and keeps the original Takeout data safe and auditable.

The tool is not a general photo organizer. Do not add album reorganization, duplicate removal, media deletion, filename-based date guessing, HEIC/video writes, `creationTime` fallback, resume, or parallel processing unless the user explicitly scopes that work.

## Source of truth

Use the following precedence when requirements differ:

1. The user's latest explicit instructions
2. This `AGENTS.md`
3. `docs/design.md`, which is the canonical design specification
4. `README.md` and `CHANGELOG.md`
5. The current implementation and tests

Read `docs/design.md`, the user-facing documentation, the relevant implementation, and the tests before modifying behavior. `CLAUDE.md`, when present, is also required context for maintaining this file. If documentation and working code have a minor structural difference but the code already satisfies the behavioral and safety requirements, do not redesign the code merely to mirror the document's proposed module layout.

## Protected data

Everything under `sources/`, especially `sources/Takeout/`, is original source data and must be treated as read-only.

- Do not edit, rename, move, delete, chmod, or change metadata or `mtime` under `sources/`.
- Do not create temporary files or directories under `sources/`.
- Do not move JSON sidecars or run `--in-place --apply` against `sources/Takeout`.
- Tests requiring writes must use `tmp_path`, another temporary directory, or a copied fixture outside `sources/`.
- Before and after acceptance work, compare the source tree's relative paths, file count, size, `mtime_ns`, and SHA-256 values.

The repository must ignore `sources/`; never add source photos or JSON to Git.

## Datetime safety

Datetime selection is whitelist-based. Preserve the ordering and exclusions documented in `docs/design.md`.

- Existing trustworthy capture metadata such as `EXIF:DateTimeOriginal`, `EXIF:CreateDate`, and approved capture-date XMP tags takes precedence over JSON.
- JSON `photoTakenTime.timestamp` is the v1.0 sidecar source for a missing capture datetime. It is an absolute UTC instant.
- Do not use JSON `creationTime` as capture time in v1.0.
- Do not use `XMP:MetadataDate`, filesystem `mtime`, file access/change time, ICC profile dates, or album metadata dates as capture time.
- Never write a UTC `photoTakenTime` directly into a local-wall-clock `DateTimeOriginal` field when timezone evidence is unavailable.
- Resolve timezone only from supported evidence: explicit metadata offset, GPS datetime, corroborated same-directory siblings, or an explicit `--timezone` value.
- If evidence is ambiguous, conflicting, invalid, or insufficient, do not guess and do not write local capture metadata. Preserve the existing conflict and mtime-only behavior.
- Never overwrite a trustworthy existing capture datetime with JSON by default.

## Sidecar matching safety

Keep matching directory-local, evidence-based, and one-to-one.

- Build matches by indexing from JSON sidecars rather than assigning the first filename-derived guess.
- Treat JSON `title` as important evidence and keep NFC normalization, supplemental-metadata suffix handling, truncation handling, duplicate suffix handling, and case-sensitive-first comparison.
- One JSON may match at most one media file and one media file may receive at most one JSON.
- If the best candidate is not unique or the 1:1 constraint fails, report `AMBIGUOUS_JSON` and perform no write or JSON move.
- Do not classify album metadata as a media sidecar. A media sidecar requires a non-empty `title` and a usable `photoTakenTime` or `creationTime`; capture-time selection still uses `photoTakenTime` only.
- Never assign a weak or guessed JSON merely to increase the match rate.

## Modification policy

- Preserve the existing module structure and public CLI behavior.
- Make only the smallest changes necessary for the explicit request.
- Do not perform broad refactors, redesign the applier architecture, remove existing features, or add adjacent features without authorization.
- Do not delete, replace, weaken, or skip existing tests to make a change pass. Add focused regression tests for new behavior.
- Keep dry-run as the default. Without `--apply`, no media, metadata, `mtime`, JSON, output directory, or other filesystem state may be changed.
- Keep copy mode non-destructive to its input. In-place behavior always requires explicit `--in-place`; real mutation additionally requires `--apply`.

## ExifTool safety

- Use ExifTool for supported metadata writes and avoid media re-encoding.
- Do not destroy unrelated metadata or MakerNotes.
- Keep ExifTool's `<file>_original` backup until read-back verification succeeds.
- Verify written datetime values, relevant offsets, file type, dimensions where applicable, and nonzero size.
- On verification failure, restore the original in in-place mode and do not report the item as successful.
- Remove `_original` only after successful verification. A completed run must not leave unintended `_original` files.

## JSON move safety

`--move-json` is an in-place-only archival operation, never deletion. Dry-run may preview it, but an actual move requires both `--in-place` and `--apply`.

- Move only the uniquely matched sidecar of a fully successful media result, and only after media metadata/mtime work and verification have completed.
- Do not move sidecars for conflict, ambiguity, error, unsupported, missing-JSON, or partial mtime-only outcomes. Never move album metadata implicitly.
- Preserve the sidecar's path relative to INPUT beneath the requested destination.
- Never overwrite or rename around a destination collision. Leave both files untouched and record the skip/error in the audit row.
- Verify a copied sidecar before removing its source during a cross-filesystem-safe move. Never provide a JSON deletion mode.

## Testing policy

Run the project's current verification commands after changes, including at minimum:

```text
pytest
py_compile
pyflakes
```

Use the repository's active Python environment and preserve existing test coverage. Exercise both dry-run and apply behavior, collision/failure paths, path preservation, idempotency, and media/source immobility for filesystem features. Acceptance tests against `sources/Takeout` must be read-only; any in-place apply test must target a temporary copy.

For every new or modified Markdown file, inspect the leading bytes before completion. Machine-consumed files such as `AGENTS.md` must be UTF-8 without BOM. Preserve the existing encoding of human-facing Markdown unless a specific requirement says otherwise. Non-Markdown files must not gain a BOM unless explicitly required.

## Git policy

- Work on the requested feature branch and inspect `git status` before and after changes.
- Preserve all user-owned uncommitted changes. Do not stash, restore, overwrite, stage, commit, or push unless explicitly instructed.
- Never force-push or use destructive reset/checkout operations.
- Keep `sources/` ignored and verify that code, tests, docs, README, and this file remain eligible for tracking.

## Definition of done

Before reporting completion, provide evidence for:

- the files and behavior changed
- full test totals and results
- compile and lint results
- requested acceptance-test counts and statuses
- idempotency and absence of unnecessary repeated ExifTool writes
- `sources/Takeout` invariance by file count, size, `mtime_ns`, and SHA-256
- Markdown BOM checks appropriate to each changed file
- `git diff --stat` (noting that it omits untracked files) and `git status --short`
- unresolved items, deviations, and remaining risks

Do not commit or push as part of completion unless the user separately authorizes those operations.

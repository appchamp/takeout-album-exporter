# Design Specification for Restoring Google Takeout Photo and Video Capture Times

日本語（正本）: [../ja/design.md](../ja/design.md)

- Document type: design and maintenance specification; English translation
- Repository: `takeout-album-exporter`
- State: v1.0 implemented
- Encoding: UTF-8 without a BOM
- Real-data investigation: 2026-08-27
- Investigation environment: macOS (Darwin 25.6.0, APFS), ExifTool 13.55, Python 3.9.6, ffmpeg available

The Japanese document is canonical. This translation preserves its design decisions, real-data evidence, safety requirements, historical proposals, acceptance expectations, and future-work boundaries. When a historical proposal differs from the completed implementation, the current-implementation notes below and the [usage guide](usage.md) take precedence.

## Revision history

| Date | Change |
| --- | --- |
| 2026-08-27 | Initial design, including real-data investigation |
| 2026-08-27 addendum | Removed system-local timezone as a default; excluded `creationTime` fallback from v1.0; introduced format-independent `write_media_datetime()`; split timezone-match status by evidence |
| 2026-08-27 documentation reorganization | Checked against v1.0 implementation, CLI, and 81 tests; established Japanese canonical documentation and separated usage from design |

## Current implementation correspondence

The original design record is intentionally retained in the Japanese canonical document. The completed implementation has a smaller CLI and a less fragmented module layout than some original proposals. Current commands are defined by `photo-date-restore --help` and [usage.md](usage.md).

- Exactly one mode is required: `--output DIR` or `--in-place`.
- Dry-run is the default; filesystem changes require `--apply`.
- JPEG, TIFF, and PNG metadata writes are implemented. HEIC and video metadata writes are not.
- `creationTime` is read for audit purposes but never selected as capture time.
- `--resume`, `--jobs`, `--json-fallback creation-time`, `--enable-heic`, `--enable-video`, `--add-offset`, `--edited-policy`, `--filename-date`, `albums.csv`, and explicit birth-time control are proposals, not current features.
- Exact report columns are defined by `REPORT_COLUMNS` in `photo_date_restore/report.py`; exact status names are defined by `Status` in `photo_date_restore/models.py`.
- `TIMEZONE_REQUIRED_FOR_METADATA` is a `message` reason code, not a status. `SKIP_DESTINATION_EXISTS` is a `planned_json_action` value.
- The implementation centers orchestration in `pipeline.py` instead of reproducing the proposed applier hierarchy. It already satisfies the behavioral and safety requirements, so no structural redesign is warranted.
- Multiple Takeout albums were examined. Source-invariance checks use a pre-work snapshot of paths, file count, total bytes, `mtime_ns`, and SHA-256.

The limited pre-v1.0 safety fixes resolved these implementation differences:

- `--timezone` is validated with `zoneinfo.ZoneInfo` before processing; an invalid IANA name is a CLI error.
- A corresponding sidecar with invalid syntax, unreadable content, or invalid required values is `ERROR`, not `NO_JSON`; its cause is reported and media, `mtime`, and JSON remain unchanged.
- In a dry run, `planned_mtime_action=SET` places the UTC absolute instant that apply would set in `new_mtime`, without changing the real file.

The following difference remains outside this limited fix:

- `UNSUPPORTED` and `SKIPPED` exist in the enum but are not normally emitted; unsupported metadata formats are reported through `UNSUPPORTED_FORMAT_FOR_METADATA(...)` in `message`.

## 1. Purpose

Provide a safety-first Python CLI that restores lost capture timestamps for photos and videos exported by Google Takeout. It recursively:

1. discovers media;
2. matches each media file with a Google Takeout sidecar using evidence;
3. reads existing EXIF, XMP, and QuickTime metadata;
4. compares existing metadata with JSON;
5. selects a trustworthy capture timestamp and records its source;
6. writes capture metadata only when necessary;
7. repairs filesystem `mtime` and, where the platform naturally does so, creation time;
8. records every decision and change in an audit report.

### 1.1 Highest-priority principles

```text
1. Do not damage the original.
2. Do not write a guessed datetime.
3. Respect existing EXIF.
4. Use JSON to verify it.
5. Restore from JSON only when EXIF is missing.
6. Leave unresolved cases as conflicts.
7. Never discard the JSON original.
8. Support dry-run.
9. Make every change auditable.
10. Be idempotent.
```

A value that merely looks like a date is not sufficient. Capture time, Google Photos registration time, media-edit time, and Takeout extraction time are distinct. The real data demonstrates misleading values in `XMP:MetadataDate`, `creationTime`, and `FileModifyDate`.

## 2. Non-goals

The tool does not move, delete, or rename original media; reorganize by date; deduplicate; rebuild albums or create symlinks; write GPS/descriptions/people; guess from filenames by default; extract Takeout ZIPs; or upload to Google Photos. Live Photo pairing, general album export, and metadata beyond capture time remain separate future work.

## 3. Real-data investigation

### 3.1 Method and source protection

The investigation read `sources/Takeout/` with ExifTool and filesystem inspection only. Write experiments used scratch copies. A prior tool created empty `.claude/.cc-writes/` directories under the source tree; this historical observation is retained in the canonical document because even empty directories violate the no-write principle. They are not media and hidden-directory traversal excludes them.

### 3.2 Dataset

```text
sources/Takeout/Google フォト/
├── Album A/
│   ├── IMG_0001.jpg, IMG_0002.jpg, IMG_0003.jpg, IMG_0004.jpg
│   ├── one supplemental-metadata JSON per media
│   └── メタデータ.json
└── Album B/
    ├── 17 JPEGs and IMG_0102.PNG
    ├── one supplemental-metadata JSON per media
    └── メタデータ.json
```

The generalized sample contains media sidecars and album metadata. The per-path before/after invariant remains authoritative.

Media sidecars use `<full-media-name>.supplemental-metadata.json`. Their `title` exactly matches the media basename. This sample has no filename truncation, duplicate suffix, or normalization-stressing name, so those cases require synthetic tests.

### 3.3 Album metadata

Japanese Takeout uses `メタデータ.json`. Album metadata may have `title` and `date` but lacks both `photoTakenTime` and `creationTime`. A media sidecar therefore requires a nonempty `title` and at least a usable `photoTakenTime` or `creationTime`. Capture-time selection still permits only `photoTakenTime` in v1.0.

### 3.4 `Album A`: capture EXIF missing

| File | Trustworthy capture metadata | JSON `photoTakenTime` UTC | JSON `creationTime` UTC |
| --- | --- | --- | --- |
| `IMG_0001.jpg` | none; misleading `MetadataDate` exists | 2024-01-01 00:00:00 | 2024-01-02 00:00:00 |
| `IMG_0002.jpg` | none; misleading `MetadataDate` exists | 2024-01-01 00:01:00 | 2024-01-02 00:00:00 |
| `IMG_0003.jpg` | none | 2024-01-01 02:00:00 | 2024-01-02 00:00:00 |
| `IMG_0004.jpg` | none | 2024-01-01 02:01:00 | 2024-01-02 00:00:00 |

`XMP-xmp:MetadataDate` is an Adobe metadata-edit timestamp and differs from `photoTakenTime` by exactly 16 hours. The identical `creationTime` values match the album date and describe upload/registration, not capture. `FileModifyDate` reflects Takeout download/extraction. Consequently `photoTakenTime` is the only usable capture source for these four files.

### 3.5 `Album B`: existing capture metadata

For a generalized JPEG sample, local `DateTimeOriginal` and JSON UTC differ by a +09:00 timezone offset. Each JPEG also has `GPSDateTime`, from which a +09:00 offset is independently derived after quarter-hour rounding. The difference is a representation of one instant, not a conflict.

`IMG_0102.PNG` has no EXIF but has `XMP-photoshop:DateCreated`, which exactly equals JSON converted to JST. This tag is trustworthy; `XMP-xmp:MetadataDate` is not. Tag-level whitelisting is mandatory.

### 3.6 Write experiments

- Adding JPEG `DateTimeOriginal`, `CreateDate`, and offset tags with ExifTool preserved XMP, ICC, Adobe APP14, and image data.
- PNG XMP/creation-time writes succeeded. PNG eXIf is readable by fewer viewers and is not the selected default.
- A synthetic MP4 write with `-api QuickTimeUTC=1` stored UTC correctly; omitting that API causes a typical nine-hour error.
- On APFS, moving `mtime` backward also lowers birth time; moving it forward does not raise birth time.
- HEIC writing was not tested because no real sample was available.

## 4. Google Takeout structure

Directory names are locale-dependent and cannot be assumed. Any selected root is scanned recursively, and matching remains within one directory.

A media sidecar commonly contains `title`, `photoTakenTime`, `creationTime`, optional geo fields, people, and origin data. Unix `timestamp`, not localized `formatted`, is parsed. Zero coordinates mean no location. Broken or unusual JSON must be validated. Album metadata naturally fails the media-sidecar condition.

## 5. Media-to-sidecar matching

### 5.1 Principle

Never assign the first filename-derived guess. Build a reverse index from JSON, score evidence, enforce one JSON per media and one media per JSON, and return `AMBIGUOUS_JSON` without repair if the best result is not unique.

### 5.2 Classification and normalization

Within each directory:

1. decode and parse JSON;
2. require a JSON object, nonempty `title`, and usable `photoTakenTime` or `creationTime`;
3. exclude album metadata;
4. normalize names and titles to Unicode NFC;
5. decompose supplemental-metadata suffixes, truncation, and duplicate markers;
6. compare case-sensitively first and use case-insensitive evidence only at a lower tier.

### 5.3 Evidence tiers

The implemented tiers are:

| Tier | Evidence |
| --- | --- |
| `T1_EXACT_TITLE` | normalized JSON `title` equals media basename, with safe duplicate tolerance |
| `T2_EXACT_NAME` | decomposed JSON name equals media basename case-sensitively |
| `T3_DERIVED_VERIFIED` | an edited/extension/duplicate transform matches and `title` corroborates it |
| `T4_TRUNCATED_PREFIX` | a sufficiently long truncated prefix matches and exact `title` verifies it |

`title` is important because it is content evidence rather than merely a possibly truncated sidecar filename. Weak assignment is never used merely to increase match rate.

## 6. Datetime selection

### 6.1 Whitelist

Trustworthy existing capture candidates are selected by tag priority: EXIF `DateTimeOriginal`, EXIF `CreateDate`, approved XMP capture tags such as Photoshop `DateCreated`, and supported QuickTime creation tags. Existing EXIF `ModifyDate` is only a lower-priority candidate where the design explicitly permits it.

If no trusted existing candidate exists, JSON `photoTakenTime.timestamp` is the v1.0 source. The following are excluded: `creationTime`, `XMP:MetadataDate`, `XMP:ModifyDate`, ICC profile dates, filesystem timestamps, album dates, and standalone QuickTime media-modify time.

### 6.2 Decision cases

- Existing capture time plus JSON: compare them. Keep existing metadata on a match; write nothing on conflict.
- Existing capture time without usable JSON: trust existing metadata (`OK_EXIF`).
- No existing capture time plus `photoTakenTime`: always use its UTC instant for `mtime`; write local metadata only if timezone evidence exists.
- Only `creationTime`: `NO_DATE` in v1.0.
- No candidate: `NO_DATE`.

### 6.3 EXIF/JSON comparison

Let `delta` be the existing local-wall-clock digits treated provisionally as UTC minus JSON `photoTakenTime` UTC.

- Absolute delta within the configured `conflict-seconds` (default 60): `EXIF_JSON_MATCH`.
- Otherwise, round to the nearest 900 seconds if within `tz-tolerance` (default 90) and within ±14 hours.
- Confirm that offset, in order, with an explicit media offset, GPS, at least three consistent same-directory siblings, or CLI timezone.
- Map evidence to `EXIF_JSON_MATCH_TZ_EXPLICIT`, `_GPS`, `_INFERRED`, or `EXIF_JSON_POSSIBLE_TZ`.
- A non-timezone-shaped or over-14-hour delta is `EXIF_JSON_CONFLICT`.

Existing capture metadata is never overwritten in case A. `POSSIBLE_TZ` keeps the existing value with low confidence but lacks sufficient evidence for adding an offset.

### 6.4 Why existing EXIF wins

`DateTimeOriginal` is primary data written at capture. Google JSON may be derived from that data. JSON may be better only after a user manually corrected Google Photos, so any future prefer-JSON behavior must be explicit and is not part of current v1.0.

## 7. Priority summary and `creationTime`

For missing metadata with `photoTakenTime`, timezone evidence yields `JSON_TIME_USED` and writes local time plus offset; absent evidence yields `JSON_TIME_MTIME_ONLY`, `planned_metadata_action=SKIP_TIMEZONE_REQUIRED`, and `message=TIMEZONE_REQUIRED_FOR_METADATA`.

`creationTime` was identical across each album and aligned with upload/album time. Using it would collapse many photos onto one misleading timestamp. It remains report-only. The historical `--json-fallback creation-time` proposal is retained only as future design and is not a current option.

## 8. Timezone processing

The system-local timezone is deliberately not a candidate. The capture location may differ from the machine running the tool.

| Priority | Evidence | `timezone_source` |
| --- | --- | --- |
| 1 | Media `OffsetTimeOriginal` or equivalent explicit offset | `EXPLICIT` |
| 2 | Offset derived from local capture time versus `GPSDateTime` | `GPS` |
| 3 | At least three consistent explicit/GPS observations in the same directory | `INFERRED` |
| 4 | User-supplied IANA `--timezone` | `CLI` |
| 5 | No supported evidence | `NONE` |

When restoring from JSON, a supported metadata writer records local time and an offset together. This preserves the absolute instant. Historical `--utc`, geo inference, disable-sibling, and no-offset alternatives are not implemented.

## 9. ExifTool writes

ExifTool is selected because it supports non-reencoding writes, preserves MakerNotes better than EXIF-block reconstruction, handles JPEG/TIFF/PNG and potentially QuickTime, and supports read-back verification.

Current write dispatch is format-independent:

| Format | Current tags |
| --- | --- |
| JPEG/TIFF | `EXIF:DateTimeOriginal`, `EXIF:CreateDate`, `EXIF:OffsetTimeOriginal`, `EXIF:OffsetTimeDigitized` |
| PNG | `XMP-photoshop:DateCreated`, `XMP-xmp:CreateDate`, `PNG:CreationTime` |
| HEIC/video | no metadata write in v1.0 |

Do not write IFD0 `ModifyDate` as capture time. Case B adds missing tags; case A does not write existing capture metadata.

### 9.1 Verification and rollback

After a write, read the target back and verify expected datetime, relevant offset, file type, dimensions where applicable, and nonzero size. ExifTool's `<file>_original` remains until verification succeeds. On in-place failure, restore it and report `VERIFY_FAILED`; on success, remove the backup. No completed run should leave an unintended `_original`.

Historical proposals for QuickTime write tags, `--preserve-xattr`, PNG eXIf, and opt-in HEIC/video are retained in the Japanese record but are not available in v1.0.

## 10. Filesystem dates

`mtime` is set with `os.utime()` to the selected absolute instant. `ctime` is kernel-managed and never set. Python has no portable direct birth-time setter. APFS commonly lowers birth time when `mtime` is moved into the past; this observed side effect is not a portable guarantee. Explicit birth-time control remains out of scope.

## 11. Copy mode

Copy mode preserves the complete path relative to INPUT and writes media beneath OUTPUT. It does not copy sidecars or album metadata. `.DS_Store` and AppleDouble files are ignored.

Unresolved media can be copied unchanged, but receives no timestamp repair. Existing correct output becomes `NO_CHANGE`; different existing output becomes `OUTPUT_EXISTS` unless `--overwrite-output` is explicit. INPUT remains read-only.

The original design discussed optional copying of JSON, album metadata, capacity checks, and separate appliers. Those options are not implemented.

## 12. In-place mode

In-place requires explicit `--in-place`; mutation additionally requires `--apply`. Interactive runs ask for confirmation unless `--yes` is present. Backups and read-back verification protect media writes. The original Takeout should not be the target; use a backed-up working copy.

## 13. JSON archival

`--move-json DIR` is in-place only. A dry run records the plan. An applied move occurs only after a uniquely matched media result is fully successful.

- Do not move for conflict, ambiguity, error, `NO_JSON`, `NO_DATE`, or `JSON_TIME_MTIME_ONLY`.
- Never move album metadata implicitly.
- Preserve the sidecar path relative to INPUT.
- Reject a destination inside INPUT or the repository's `sources/`.
- Never overwrite or invent a collision name.
- For cross-filesystem safety, create exclusively, copy, fsync, compare size and bytes, copy file metadata, and only then unlink the source.
- Maintain an append-only, UTF-8-no-BOM `_sidecar_index.csv` with media path, original sidecar path, moved sidecar path, and `MOVED` status.
- Roll back the sidecar if index update fails where possible.

After archival, rescanning the original working tree produces `NO_JSON` because its sidecars have moved. This is archival, not deletion without preservation.

## 14. Dry-run

Dry-run is the default and does not create output media, mutate metadata or filesystem times, or move JSON. A requested report is intentionally written because it is the result of the dry run. The same analysis and planning logic is used for dry and applied runs.

## 15. Audit report

CSV is UTF-8 with a BOM by default for spreadsheet compatibility; `--csv-no-bom` disables the BOM. JSONL is UTF-8 without a BOM.

The implemented columns are:

```text
file, relative_path, album_name, media_type, file_type,
json_sidecar, json_match_tier, json_candidates,
existing_datetime, existing_datetime_source, exif_offset, gps_datetime,
json_photo_taken_time, json_creation_time,
difference_seconds, implied_offset_seconds,
selected_datetime, selected_datetime_source,
timezone_source, timezone_offset, confidence,
planned_metadata_action, planned_mtime_action,
planned_json_action, planned_json_destination,
status, old_mtime, new_mtime, error, message
```

### 15.1 Status values

| Status | Meaning |
| --- | --- |
| `NO_CHANGE` | Already correct; no redundant write |
| `OK_EXIF` | Existing trusted capture time without usable JSON |
| `EXIF_JSON_MATCH` | Existing time and JSON match within tolerance |
| `EXIF_JSON_MATCH_TZ_EXPLICIT` | Explicit media offset or CLI evidence explains the difference |
| `EXIF_JSON_MATCH_TZ_GPS` | GPS independently explains it |
| `EXIF_JSON_MATCH_TZ_INFERRED` | Consistent sibling evidence explains it |
| `EXIF_JSON_POSSIBLE_TZ` | Timezone-shaped difference without independent evidence |
| `EXIF_JSON_CONFLICT` | Unexplained difference; no repair |
| `JSON_TIME_USED` | `photoTakenTime` used with established timezone |
| `JSON_TIME_MTIME_ONLY` | UTC instant used for `mtime`; local metadata skipped |
| `NO_JSON` | No uniquely matched sidecar |
| `NO_DATE` | No allowed capture source |
| `AMBIGUOUS_JSON` | Non-unique match or failed 1:1 constraint |
| `UNSUPPORTED` | Enum value; current pipeline normally reports unsupported metadata format in `message` |
| `VERIFY_FAILED` | Read-back verification failed |
| `OUTPUT_EXISTS` | Different output exists and overwrite is disabled |
| `SKIPPED` | Reserved enum value, not normally emitted |
| `ERROR` | Processing/I/O error |

`TIMEZONE_REQUIRED_FOR_METADATA` belongs to `message`; `SKIP_DESTINATION_EXISTS` belongs to `planned_json_action`. They are not statuses.

Console output summarizes counts. Exit codes are 0 for normal results, 1 for conflict/ambiguity/`NO_DATE`, 2 for error/verification failure, and 3 for fatal argument/environment/input errors or cancellation.

## 16. Error handling

Malformed or unusable JSON, invalid timestamps, ExifTool failure, unreadable files, zero-length files, output collisions, and JSON archival failures must be reported without leaving a partial media success. One file should not normally stop the whole run. Fatal startup validation stops before mutation.

The original design additionally proposed multi-encoding JSON fallback, symlink following, preflight capacity checks, signal recovery, and specialized EXIF normalization. Only behavior supported by current tests and code should be claimed operational.

## 17. Idempotency

Before writing, compare expected metadata and `mtime` with the target. If both are correct, return `NO_CHANGE` and do not call ExifTool. In copy mode the comparison is against output. Acceptance verifies a second applied copy-mode run produces 22 `NO_CHANGE` rows and unchanged output SHA-256 values.

After `--move-json`, a repeat scan is expected to produce `NO_JSON`, because JSON has intentionally moved. This differs from the historical `--resume` proposal, which is not implemented.

## 18. File formats

Case-insensitive discovery includes `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.gif`, `.webp`, `.dng`, `.heic`, `.heif`, `.mp4`, `.mov`, `.m4v`, `.3gp`, `.avi`, `.mkv`, `.mpg`, and `.mts`.

| Format | Analyze | Set `mtime` | Write capture metadata |
| --- | --- | --- | --- |
| JPEG | yes | yes | yes |
| TIFF | yes | yes | yes |
| PNG | yes | yes | yes, via selected XMP/PNG tags |
| HEIC/HEIF | yes | yes where a date is selected | no in v1.0 |
| Video | yes | yes where a date is selected | no in v1.0 |
| GIF/WebP/DNG/other discovered types | yes | yes where a date is selected | no |

Live Photo/Motion Photo pairs receive no special pairing in v1.0.

## 19. CLI: implemented versus proposed

Current basic form:

```text
photo-date-restore INPUT (--output DIR | --in-place) [options]
```

Implemented options are documented in [usage.md](usage.md) and verified with `--help`: `--output`, `--in-place`, `--apply`, `--dry-run`, `--yes`, `--timezone`, report options, `--overwrite-output`, `--move-json`, conflict/tz tolerances, ExifTool path, and version handling.

The original design also listed `--limit`, `--jobs`, `--resume`, verbose/quiet, JSON fallback, prefer JSON, filename date, conflict policy, UTC mode, geo timezone, sibling controls, metadata/mtime toggles, birth time, add offset, ModifyDate, PNG eXIf, HEIC/video, xattr, filters, symlink following, weak match, JSON copying, album metadata copying, skip unresolved, move album metadata, and hashing. These are historical/future proposals and must not be presented as available commands.

## 20. Module structure

The current package contains `cli`, `pipeline`, `models`, `sidecar`, `jsonmeta`, `metaread`, `tz`, `decide`, `exiftool_client`, `mediawrite`, `fsdates`, and `report`. Pure decision and matching logic remains separated enough for unit testing. The proposed `config`, `scan`, `applier`, `jsonvault`, and `errors` modules were not introduced merely to mirror the design diagram.

Python compatibility is 3.9 or later. Runtime Python dependencies are standard-library only; `timezonefinder` remains an optional `geo` extra but current CLI does not expose geo inference. ExifTool is an external executable.

## 21. Test strategy

Tests cover:

- sidecar classification, NFC, supplemental suffixes, duplicate suffixes, truncation, case ordering, 1:1 ambiguity;
- datetime whitelist and priority;
- exact, near, explicit, GPS, inferred, possible-timezone, conflict, 14-hour boundary, JSON-used, mtime-only, and no-date decisions;
- timezone arithmetic and sibling minimum count;
- copy mode, in-place mode, metadata writes, verification, output collision, idempotency;
- JSON move success, dry-run, relative paths, destination collision, status exclusion, index append/idempotency, cross-filesystem-safe failure and rollback;
- read-only acceptance against real Takeout data.

The current suite has 81 tests. The historical design proposed a different directory layout and fixture generator; the behavioral coverage, not that layout, is authoritative.

### 21.1 Protected-source acceptance

Before and after acceptance work, compare every source file by relative path, file count, size, `mtime_ns`, and SHA-256. Tests use output under a temporary directory. Any in-place test uses a temporary copy. No temporary file or output belongs under `sources/`.

## 22. Generalized acceptance expectations

Validate multiple generalized Takeout albums without publishing their source-specific values.

- Sidecars match uniquely at T1, and trustworthy existing EXIF/XMP is not rewritten.
- With GPS or same-directory evidence, an EXIF/JSON difference representing a timezone is not a conflict.
- Without confirmed timezone evidence, use `JSON_TIME_MTIME_ONLY` and do not write capture metadata.
- Never select `creationTime` or `XMP:MetadataDate` as capture time.
- Copy-mode output contains media only; a second applied run is `NO_CHANGE` without unnecessary ExifTool writes.
- Protected input remains unchanged by path, count, size, `mtime_ns`, and SHA-256.
- Test in-place and JSON archival only on a temporary copy.

## 23. Resolved and future design questions

The original design recorded decisions for human review. Current v1.0 resolves them as follows:

| Topic | v1.0 position |
| --- | --- |
| Default timezone | none; do not use system-local; mtime-only without evidence |
| `creationTime` fallback | off and unimplemented |
| Birth time | no explicit control |
| Edited-file selection | no special user option |
| Album export/index | outside current scope |
| HEIC/video metadata writes | unimplemented pending real samples |
| GPS/descriptions/people write-back | future work |
| Cloud-synced in-place | avoid original data; use warning and backups operationally |
| Add offset to existing EXIF | off/unimplemented; existing metadata remains untouched |
| Live/Motion pairing | future work |
| Parallelism | sequential only; no `--jobs` |
| Report CSV BOM | enabled by default |

## 24. Implementation history and future phases

The original plan separated read-only analysis, copy mode, in-place/JSON archival, timezone hardening, and format expansion. v1.0 now implements analysis, copy mode, in-place mode, safe JSON archival, and core timezone evidence in the present module structure. `--resume`, broader error-handling proposals, geo inference, HEIC/video writes, Live Photo pairing, and parallelism remain future work. They must be backed by real samples and focused tests before enablement.

## Appendix A. External implementation and issue research

The design borrowed from GooglePhotosTakeoutHelper: 51-character truncation handling, duplicate-marker placement, localized edited suffix concepts, NFC normalization, extension-less matching, and `photoTakenTime` priority. It deliberately improves safety by supporting supplemental-metadata names, detecting ambiguity, enforcing 1:1 matching, requiring title evidence for derived matches, avoiding filename-date guesses, writing supported capture metadata with verification, defaulting to copy mode, and treating timezone explicitly.

The 2026 Takeout sample confirms that `.supplemental-metadata.json` support is a requirement, not an optional compatibility path. The tool remains a macOS-friendly, CLI, original-preserving alternative rather than a file organizer.

## Appendix B. Generalized evidence summary

Generalized samples demonstrate that local EXIF time and JSON UTC can represent the same instant with a timezone offset; GPS or sibling evidence determines whether that relationship is confirmed. Separate samples demonstrate that `MetadataDate` and `creationTime` are not capture-time sources. Actual album names, filenames, timestamps, coordinates, and counts are intentionally omitted.

## Appendix C. Detailed matching record

This appendix translates the lower-level rules retained in Japanese sections 5 and 6.

### C.1 Media-sidecar predicate

```text
is_media_sidecar(j) :=
      j is a valid JSON object
  AND "title" is a nonempty string
  AND ("photoTakenTime" has timestamp OR "creationTime" has timestamp)
```

A false result is album metadata or unknown JSON. It is not deleted or moved. Matching never crosses a directory boundary.

### C.2 Sidecar filename grammar

```text
json_filename = stem [supplemental_suffix] [duplicate_suffix] ".json"

supplemental_suffix = a literal prefix of ".supplemental-metadata"
duplicate_suffix    = "(" digits ")"
```

The suffix rule accepts the complete suffix and truncations such as `.supplemental-metadat`, `.supple`, or `.s`, but not an arbitrary `.s*` string. Each candidate has normalized `K_title`, `K_stem`, and optional `K_dup`. NFC and surrounding-whitespace normalization precede comparison. Case-sensitive comparison is first; casefold is a lower stage.

### C.3 Media-derived keys

In descending trust order, matching may consider:

1. the basename unchanged;
2. removal of a localized edited suffix (`-edited`, `-編集済み`, `-bearbeitet`, `-bewerkt`, `-edytowane`, `-modificato`, `-modifié`, `-ha editado`, `-editat`, `-effects`, `-smile`, `-mix`);
3. duplicate-marker relocation, such as `image(11).jpg` versus `image.jpg(11).json`;
4. extension removal;
5. Google's 51-character JSON-name truncation behavior;
6. removal of `(n)`, which is weak and cannot stand alone.

Historical T5 weak matching required a future `--allow-weak-match`; v1.0 implements only verified tiers. If multiple candidates tie at the highest tier, or a JSON would be assigned to two media files, all involved results are ambiguous. A weak candidate does not become an assignment merely to improve coverage.

### C.4 Datetime source tables

Allowed candidates in original design priority:

| Priority | Source | Meaning | Time basis | v1.0 treatment |
| --- | --- | --- | --- | --- |
| 1 | EXIF `DateTimeOriginal` plus subsecond/offset | original capture | local plus optional offset | preferred |
| 2 | EXIF `CreateDate` | digitization/capture | local | used if priority 1 absent |
| 3 | QuickTime `Keys:CreationDate` | video capture | explicit offset | readable candidate where supported |
| 4 | QuickTime `CreateDate` | video creation | UTC storage | read with QuickTime UTC semantics |
| 5 | approved XMP `DateCreated` / EXIF XMP original | capture | local or offset | whitelisted |
| 6 | JSON `photoTakenTime.timestamp` | capture instant | UTC | restoration source when existing capture time is absent |
| 7 | IFD0 `ModifyDate` | file-level update | local | historical low-trust proposal, not a reason to overwrite stronger data |
| 8 | JSON `creationTime.timestamp` | Google registration/upload | UTC | report-only; never selected in v1.0 |
| 9 | filename-embedded date | guess | unknown | not implemented |

Explicitly excluded:

| Source | Actual meaning |
| --- | --- |
| `XMP-xmp:MetadataDate` / `XMP-xmp:ModifyDate` | metadata edit time |
| `ICC-header:ProfileDateTime` | ICC profile creation time, often a constant |
| filesystem modify/access/inode-change timestamps | Takeout extraction or filesystem activity |
| album metadata `date` | album creation/registration |
| standalone QuickTime `MediaModifyDate` | encoding/update time |

### C.5 Detailed match classification

| Classification | Condition | Result |
| --- | --- | --- |
| exact | `abs(delta) <= 2` seconds | `EXIF_JSON_MATCH`, high confidence |
| near | 2 to configured 60 seconds | `EXIF_JSON_MATCH`, record delta |
| explicit timezone | quarter-hour offset within 90 seconds and same explicit tag or CLI offset | `EXIF_JSON_MATCH_TZ_EXPLICIT`, high |
| GPS timezone | same offset independently obtained from GPS UTC | `EXIF_JSON_MATCH_TZ_GPS`, high |
| inferred timezone | no file-local evidence, but at least three same-directory explicit/GPS confirmations agree | `EXIF_JSON_MATCH_TZ_INFERRED`, medium |
| possible timezone | quarter-hour shape within ±14 hours but no independent support | `EXIF_JSON_POSSIBLE_TZ`, low |
| unclear conflict | within ±14 hours but not a supported offset shape | `EXIF_JSON_CONFLICT` |
| major conflict | beyond ±14 hours | `EXIF_JSON_CONFLICT` |

Fifteen minutes is the minimum granularity covering Nepal +05:45 and Eucla +08:45. Ninety seconds absorbs GPS fix delay and clock drift. Fourteen hours includes UTC+14 but rejects a day-scale mismatch.

## Appendix D. Detailed mode and write record

### D.1 ExifTool selection matrix

| Concern | ExifTool | piexif/Pillow-style alternatives |
| --- | --- | --- |
| JPEG/TIFF non-reencoding write | strong | EXIF reconstruction or image re-encoding risk |
| PNG metadata | supported | limited |
| HEIC/QuickTime potential | supported but requires real-sample validation | weak or read-only |
| MakerNote preservation | strong | reconstruction can damage vendor data |
| offset tags and QuickTime UTC | explicit support | easy to implement incorrectly |
| backup and read-back | integrated | custom work required |

The original plan proposed an ExifTool stay-open process for throughput and a read-only fallback when ExifTool is absent. Current CLI requires ExifTool discovery before running, including dry-run; documentation follows current behavior.

### D.2 Per-format historical write design

JPEG/TIFF writes missing `DateTimeOriginal`, `CreateDate`, `OffsetTimeOriginal`, and `OffsetTimeDigitized`; it deliberately does not treat IFD0 `ModifyDate` as capture time. PNG uses Photoshop/XMP creation tags and `PNG:CreationTime`; an eXIf chunk remained an unimplemented compatibility option. The video proposal would write QuickTime create/modify fields under `-api QuickTimeUTC=1` and an offset-bearing `Keys:CreationDate`, but no video metadata write is enabled in v1.0.

Verification sequence:

```text
1. Read the written file again with ExifTool.
2. Compare expected datetime to the second.
3. Compare a written offset.
4. Confirm file type, dimensions where applicable, and nonzero size.
5. On failure, report VERIFY_FAILED and restore the in-place backup.
6. On success, remove <file>_original.
```

### D.3 Filesystem timestamps

| Timestamp | Meaning | Policy |
| --- | --- | --- |
| `mtime` | content modification | set to selected absolute capture instant with `os.utime()` |
| `atime` | access | implementation supplies it as required by `os.utime()` |
| `birthtime` | filesystem creation | no portable explicit write; APFS may lower it as a side effect |
| `ctime` | inode metadata change | kernel-managed; never set |

The historical `--no-set-mtime` and `--force-birthtime` alternatives are not current CLI options.

### D.4 Copy sequence and output policy

The original detailed sequence was: create the output directory, copy bytes without carrying source filesystem metadata, apply missing media metadata, set `mtime`, verify, and remove a failed output. The current implementation performs the same core copy/write/mtime ordering through `pipeline.py`.

| Item | Policy |
| --- | --- |
| Input | read-only |
| Path | preserve relative to INPUT |
| Output content | media only |
| Sidecars and album JSON | remain at input |
| Apple noise | ignore `.DS_Store` and `._*` |
| Unresolved media | copy unchanged in applied copy mode, without repair |
| Existing output | `NO_CHANGE` if already correct; otherwise `OUTPUT_EXISTS` unless overwrite is explicit |

Keeping JSON out of the repaired output prevents reprocessing and keeps the destination usable as a clean media library. It is safe because INPUT retains JSON and the audit report records the mapping. Historical `--copy-json` and `--copy-album-metadata` proposals are not implemented.

### D.5 JSON archive layout and index

Example:

```text
INPUT/
└── album/media.jpg

JSON_BACKUP/
├── album/media.jpg.supplemental-metadata.json
└── _sidecar_index.csv
```

Index columns:

```text
media_relative_path
original_sidecar_relative_path
moved_sidecar_relative_path
status
```

The source is removed only after exclusive destination creation, byte verification, and metadata preservation. Index failure attempts rollback. Repeated index entries are not added. Destination collision leaves both existing files untouched and is not recorded as a successful move.

### D.6 Dry-run boundary

Dry-run performs scanning, matching, metadata reads, decisions, comparisons, planning, and an explicitly requested audit report. It does not copy media, create output directories, write metadata, change `mtime`, or move JSON. The original no-op-applier architecture was a proposal; the current pipeline enforces the same external boundary without that class hierarchy.

## Appendix E. Detailed report and error record

### E.1 Field semantics

| Field group | Purpose |
| --- | --- |
| `file`, `relative_path`, `album_name`, `media_type`, `file_type` | identity and placement |
| `json_sidecar`, `json_match_tier`, `json_candidates` | matching evidence and ambiguity |
| `existing_datetime`, `existing_datetime_source`, `exif_offset`, `gps_datetime` | trusted media evidence |
| `json_photo_taken_time`, `json_creation_time` | Takeout evidence; the latter is audit-only |
| `difference_seconds`, `implied_offset_seconds` | comparison arithmetic |
| `selected_datetime`, `selected_datetime_source` | selected capture representation |
| `timezone_source`, `timezone_offset`, `confidence` | timezone evidence |
| `planned_metadata_action`, `planned_mtime_action`, `planned_json_action`, `planned_json_destination` | planned or completed mutations |
| `status`, `old_mtime`, `new_mtime`, `error`, `message` | outcome and diagnostics |

The original design proposed automatically placing an unspecified report beneath output or the current directory. Current implementation writes a report only when `--report` is provided.

### E.2 Original error requirements versus current verification

The preserved design requires malformed JSON, invalid timestamps, ExifTool failures, unreadable or zero-length files, insufficient capacity, interrupted writes, and invalid EXIF date forms to fail closed for the affected file. It also proposed UTF-8, UTF-8-SIG, then CP932 JSON decoding; symlink-loop protection; preflight free-space validation; and signal-aware rollback.

Not every proposed path exists in current code. The pre-v1.0 safety fixes now fail invalid timezone names before processing, report matching malformed/unreadable/required-value-invalid sidecars as `ERROR`, and show the planned absolute `new_mtime` during dry-run. The current CLI still checks ExifTool even for dry-run; broader historical proposals remain non-capabilities unless implemented and tested.

### E.3 Idempotency properties

```text
metadata_ok := every expected tag is present and matches to the second
mtime_ok    := current mtime matches the expected instant within filesystem tolerance
metadata_ok AND mtime_ok => NO_CHANGE and no ExifTool write
```

Desired and tested properties are: the second applied copy run is all `NO_CHANGE`; no output bytes change on the second run; fixed tag names prevent metadata multiplication; verified in-place completion leaves no `_original`; and JSON archival is never repeated around a destination collision.

The historical `--resume REPORT` idea would have skipped completed rows from a prior audit. It is not implemented and is not required for current idempotency.

## Appendix F. Historical CLI proposal inventory

The full original option inventory is retained here so the English design does not erase future decisions. Only options also listed in current `--help` are implemented.

```text
Implemented now:
  INPUT
  -o/--output DIR | --in-place
  --apply, --dry-run, -y/--yes
  --timezone TZ
  --report PATH, --report-format {csv,jsonl}, --csv-no-bom
  --overwrite-output, --move-json DIR
  --conflict-seconds N, --tz-tolerance N
  --exiftool PATH, --version (subject to required parser arguments)

Historical proposals, not implemented:
  --limit N, --jobs N, --resume REPORT
  --verbose, --quiet
  --json-fallback {none,creation-time}, --prefer-json, --filename-date
  --on-conflict {skip,report-only,use-exif,use-json}
  --utc, --tz-from-geo, --no-tz-from-siblings, --no-write-offset
  --no-write-exif, --no-set-mtime, --force-birthtime
  --add-offset, --write-modifydate, --png-exif
  --enable-heic, --enable-video, --preserve-xattr
  --include-ext, --exclude-ext, --edited-policy
  --follow-symlinks, --allow-weak-match
  --copy-json, --copy-album-metadata, --skip-unresolved
  --move-album-metadata, --hash
```

The fail-safe changes from the earliest command sketch were deliberate: dry-run became default, `--apply` became explicit, and the output mode became a required mutually exclusive choice.

## Appendix G. Detailed module proposal and actual mapping

The historical layout proposed `config`, `scan`, a stay-open `exiftool` session, `applier`, `jsonvault`, and `errors`, plus unit/integration/acceptance subdirectories. The implementation instead maps responsibilities as follows:

| Responsibility | Current module |
| --- | --- |
| parser, option validation, exit codes | `cli.py` |
| recursive scan, two-pass timezone inference, row construction, apply, JSON archive | `pipeline.py` |
| data structures and enums | `models.py` |
| sidecar matching | `sidecar.py` |
| JSON parsing | `jsonmeta.py` |
| tag whitelist extraction | `metaread.py` |
| offset arithmetic | `tz.py` |
| pure datetime decision | `decide.py` |
| ExifTool invocation and backup helpers | `exiftool_client.py` |
| format-dispatched write and verification | `mediawrite.py` |
| filesystem time | `fsdates.py` |
| CSV/JSONL output | `report.py` |

`sidecar`, `tz`, and `decide` remain the pure logical core. The design requires Python 3.9 compatibility and standard-library runtime dependencies, with `timezonefinder` only in the optional `geo` extra.

## Appendix H. Detailed test matrix

### H.1 Sidecar matching cases

1. classic `<media>.json`;
2. full supplemental-metadata suffix;
3. literal truncated supplemental suffixes down to `.s`;
4. similar but nonliteral suffix rejection;
5. 51-character stem truncation with exact title support;
6. duplicate-marker relocation with a title lacking `(n)`;
7. original and duplicate media coexisting with 1:1 assignments;
8. localized edited suffixes;
9. NFD filename versus NFC title (`が`, `ダ`, `é`);
10. extension case mismatch at a lower comparison stage;
11. one JSON matching two media: both ambiguous;
12. two same-tier JSONs for one media: ambiguous;
13. locale-specific album metadata exclusion;
14. JSON without both accepted time objects excluded as sidecar;
15. no JSON: `NO_JSON`;
16. extension-less media.

### H.2 Datetime and timezone cases

| Case | Expected |
| --- | --- |
| delta 0 | `EXIF_JSON_MATCH` |
| +09:00 with explicit +09:00 | `_TZ_EXPLICIT` |
| +09:00 with GPS only | `_TZ_GPS` |
| +09:00 with three or more strong siblings | `_TZ_INFERRED` |
| +09:00 without support | `POSSIBLE_TZ` |
| -+09:00 with GPS | `_TZ_GPS`, -09:00 |
| +20,700 Nepal or +31,500 Eucla with GPS | `_TZ_GPS` |
| 7,237, not quarter-hour-shaped | conflict |
| 86,400 | conflict |
| 50,400 with GPS | timezone match at boundary |
| 50,401 | conflict beyond boundary |
| no EXIF, JSON plus timezone | `JSON_TIME_USED` |
| no EXIF, JSON without timezone | `JSON_TIME_MTIME_ONLY` and reason code |
| only `creationTime` | `NO_DATE` |
| only `MetadataDate` or filesystem date | not a candidate |
| only approved XMP `DateCreated` | candidate |

The original plan also called for EXIF `24:00:00` normalization, zero-date rejection, invalid epoch/future rejection, GPS delay tolerance, sibling disagreement tests, and `0.0/0.0` geo handling.

### H.3 Fixture and acceptance strategy

The historical fixture plan generated tiny JPEG/PNG images, added EXIF variants with ExifTool, optionally generated a one-second MP4 with ffmpeg, and generated JSON for the complete matrix without committing binary fixtures. The current tests use their existing fixture strategy; they must not be redesigned merely to mimic the plan.

Acceptance snapshots record `(relative_path, size, mtime_ns, sha256)` for every protected source file before and after. Copy-mode output goes to `tmp_path`; in-place tests use copied fixtures. CI should treat `sources/` as read-only.

## Appendix I. Original acceptance and phase record

The original completion expectations covered unique matching, no unresolved results in the verified sample, media-only output, idempotent second runs, unchanged protected-source hashes and times, successful read-back, and no unintended backups. Those behavioral expectations are implemented and tested.

The historical phases were:

1. read-only analysis and decision engine;
2. copy mode with write verification and idempotency;
3. in-place mode and JSON archival;
4. expanded timezone resolution and robustness, originally also listing `--resume`;
5. HEIC/video/Live Photo and parallel expansion after real samples.

Current v1.0 covers the safe core of phases 1–4 but does not imply completion of every option listed in the historical plan.

"""Audit report writer (CSV / JSONL). Design reference: docs/design.md §15."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

from .models import Status

REPORT_COLUMNS: List[str] = [
    "file",
    "relative_path",
    "album_name",
    "media_type",
    "file_type",
    "json_sidecar",
    "json_match_tier",
    "json_candidates",
    "existing_datetime",
    "existing_datetime_source",
    "exif_offset",
    "gps_datetime",
    "json_photo_taken_time",
    "json_creation_time",
    "difference_seconds",
    "implied_offset_seconds",
    "selected_datetime",
    "selected_datetime_source",
    "timezone_source",
    "timezone_offset",
    "confidence",
    "planned_metadata_action",
    "planned_mtime_action",
    "planned_json_action",
    "planned_json_destination",
    "status",
    "old_mtime",
    "new_mtime",
    "error",
    "message",
]


def write_csv(rows: Iterable[dict], path: Path, bom: bool = True) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})


def write_jsonl(rows: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_report(rows: Iterable[dict], path: Path, fmt: str = None, csv_bom: bool = True) -> None:
    rows = list(rows)
    fmt = fmt or ("jsonl" if str(path).endswith(".jsonl") else "csv")
    if fmt == "jsonl":
        write_jsonl(rows, path)
    else:
        write_csv(rows, path, bom=csv_bom)


def summarize(rows: Iterable[dict]) -> dict:
    counts: dict = {}
    for row in rows:
        status = row.get("status", "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def format_progress_line(index: int, row: dict) -> str:
    """One-line progress text shared by the CLI and GUI frontends."""
    name = row.get("relative_path") or row.get("file") or ""
    return f"[{index}] {name} — {describe_status(row.get('status', ''))}"


STATUS_DESCRIPTIONS = {
    Status.NO_CHANGE.value: "Already up to date; no change needed",
    Status.OK_EXIF.value: "Kept the existing capture date already in the file",
    Status.EXIF_JSON_MATCH.value: "Existing date matched Google metadata",
    Status.EXIF_JSON_MATCH_TZ_EXPLICIT.value:
        "Existing date matched Google metadata (time zone from the file)",
    Status.EXIF_JSON_MATCH_TZ_GPS.value:
        "Existing date matched Google metadata (time zone from GPS)",
    Status.EXIF_JSON_MATCH_TZ_INFERRED.value:
        "Existing date matched Google metadata (time zone inferred from the album)",
    Status.EXIF_JSON_POSSIBLE_TZ.value:
        "Left unchanged: dates may match, but the time zone is uncertain",
    Status.EXIF_JSON_CONFLICT.value:
        "Skipped: the file date and Google metadata disagree",
    Status.JSON_TIME_USED.value: "Date restored from Google metadata",
    Status.JSON_TIME_MTIME_ONLY.value:
        "File date restored; embedded metadata left unchanged",
    Status.NO_JSON.value: "Skipped: no Google metadata found for this file",
    Status.NO_DATE.value: "Skipped: no usable date was found",
    Status.AMBIGUOUS_JSON.value: "Skipped: matching Google metadata was ambiguous",
    Status.UNSUPPORTED.value: "Skipped: this file type is not supported",
    Status.VERIFY_FAILED.value: "Failed: the written date could not be verified",
    Status.OUTPUT_EXISTS.value: "Skipped: a file already exists in the output folder",
    Status.SKIPPED.value: "Skipped",
    Status.ERROR.value: "Failed: an error occurred",
}


def describe_status(status: str) -> str:
    """Human-readable text for a status. Unknown values fall back to the raw code."""
    return STATUS_DESCRIPTIONS.get(status, status or "")

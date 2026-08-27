"""Audit report writer (CSV / JSONL). Design reference: docs/design.md §15."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

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

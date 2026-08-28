"""Human-readable progress formatting must not change audit report data."""
import csv
import json

from photo_date_restore.models import Status
from photo_date_restore.report import (
    STATUS_DESCRIPTIONS,
    describe_status,
    format_progress_line,
    write_csv,
    write_jsonl,
)


def test_every_status_has_a_description_and_unknown_status_falls_back():
    for status in Status:
        assert status.value in STATUS_DESCRIPTIONS
    assert describe_status("FUTURE_STATUS") == "FUTURE_STATUS"
    assert describe_status("") == ""


def test_format_progress_line_uses_description_and_em_dash():
    assert format_progress_line(3, {"relative_path": "album/photo.jpg", "status": "NO_JSON"}) == (
        "[3] album/photo.jpg — Skipped: no Google metadata found for this file"
    )


def test_audit_writers_keep_raw_status_codes(tmp_path):
    row = {"relative_path": "album/photo.jpg", "status": Status.NO_JSON.value}
    csv_path = tmp_path / "report.csv"
    jsonl_path = tmp_path / "report.jsonl"

    write_csv([row], csv_path)
    write_jsonl([row], jsonl_path)

    with open(csv_path, newline="", encoding="utf-8-sig") as stream:
        assert next(csv.DictReader(stream))["status"] == Status.NO_JSON.value
    assert json.loads(jsonl_path.read_text())["status"] == Status.NO_JSON.value

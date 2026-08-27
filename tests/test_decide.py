from datetime import datetime, timezone

from photo_date_restore.decide import decide
from photo_date_restore.models import DateCandidate, SidecarInfo, Status, TzSource


def sidecar(photo_taken_time, creation_time=None, title="t"):
    return SidecarInfo(path="j.json", title=title, photo_taken_time=photo_taken_time, creation_time=creation_time)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_exif_json_exact_match():
    existing = DateCandidate(value=datetime(2017, 11, 6, 23, 40, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(existing, sidecar(utc(2017, 11, 6, 23, 40, 23)))
    assert d.status == Status.EXIF_JSON_MATCH
    assert d.planned_metadata_action == "NONE"
    assert d.planned_mtime_action == "SET"


def test_exif_json_match_tz_gps_real_data_case():
    existing = DateCandidate(value=datetime(2017, 11, 7, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    gps = utc(2017, 11, 6, 23, 40, 13)
    d = decide(existing, sidecar(utc(2017, 11, 6, 23, 40, 23)), gps_utc=gps)
    assert d.status == Status.EXIF_JSON_MATCH_TZ_GPS
    assert d.timezone_source == TzSource.GPS
    assert d.timezone_offset_seconds == 32400
    assert d.planned_metadata_action == "NONE"  # never rewrite existing EXIF


def test_exif_json_match_tz_explicit_offset_tag():
    existing = DateCandidate(value=datetime(2017, 11, 7, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(existing, sidecar(utc(2017, 11, 6, 23, 40, 23)), explicit_offset_seconds=32400)
    assert d.status == Status.EXIF_JSON_MATCH_TZ_EXPLICIT
    assert d.timezone_source == TzSource.EXPLICIT


def test_exif_json_match_tz_inferred_from_siblings():
    existing = DateCandidate(value=datetime(2017, 11, 7, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(
        existing,
        sidecar(utc(2017, 11, 6, 23, 40, 23)),
        sibling_offset_seconds=32400,
        sibling_count=17,
    )
    assert d.status == Status.EXIF_JSON_MATCH_TZ_INFERRED
    assert d.timezone_source == TzSource.INFERRED


def test_exif_json_possible_tz_single_file_no_corroboration():
    existing = DateCandidate(value=datetime(2017, 11, 7, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(existing, sidecar(utc(2017, 11, 6, 23, 40, 23)))
    assert d.status == Status.EXIF_JSON_POSSIBLE_TZ
    assert d.planned_metadata_action == "NONE"


def test_exif_json_conflict_not_quarter_hour():
    existing = DateCandidate(value=datetime(2017, 11, 7, 10, 45, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(existing, sidecar(utc(2017, 11, 6, 23, 40, 23)))
    # Δ = 39900s, 300s away from the nearest 900s multiple (39600) — outside tolerance.
    assert d.status == Status.EXIF_JSON_CONFLICT
    assert d.planned_metadata_action == "NONE"
    assert d.planned_mtime_action == "NONE"


def test_exif_json_conflict_major_day_difference():
    existing = DateCandidate(value=datetime(2017, 11, 8, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(existing, sidecar(utc(2017, 11, 6, 23, 40, 23)))
    assert d.status == Status.EXIF_JSON_CONFLICT


def test_ok_exif_no_json():
    existing = DateCandidate(value=datetime(2017, 11, 7, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    d = decide(existing, None)
    assert d.status == Status.OK_EXIF
    assert d.planned_metadata_action == "NONE"
    assert d.planned_mtime_action == "NONE"


def test_json_time_used_when_timezone_resolved_via_cli():
    d = decide(None, sidecar(utc(2026, 3, 25, 12, 59, 54)), cli_offset_seconds=32400)
    assert d.status == Status.JSON_TIME_USED
    assert d.selected_datetime_source == "PHOTO_TAKEN_TIME"
    assert d.selected_datetime == datetime(2026, 3, 25, 21, 59, 54)
    assert d.planned_metadata_action == "WRITE"
    assert d.planned_mtime_action == "SET"


def test_json_time_mtime_only_when_timezone_unknown():
    d = decide(None, sidecar(utc(2026, 3, 25, 12, 59, 54)))
    assert d.status == Status.JSON_TIME_MTIME_ONLY
    assert d.planned_metadata_action == "SKIP_TIMEZONE_REQUIRED"
    assert d.planned_mtime_action == "SET"
    assert d.mtime_datetime == utc(2026, 3, 25, 12, 59, 54)
    assert "TIMEZONE_REQUIRED_FOR_METADATA" in d.message


def test_json_time_mtime_only_ignores_weak_single_sibling():
    d = decide(None, sidecar(utc(2026, 3, 25, 12, 59, 54)), sibling_offset_seconds=32400, sibling_count=1)
    assert d.status == Status.JSON_TIME_MTIME_ONLY


def test_no_date_when_nothing_available():
    d = decide(None, None)
    assert d.status == Status.NO_DATE
    assert d.planned_metadata_action == "NONE"
    assert d.planned_mtime_action == "NONE"


def test_no_date_when_sidecar_has_no_phototakentime():
    d = decide(None, sidecar(None))
    assert d.status == Status.NO_DATE


def test_cli_offset_ranked_below_gps_when_both_present():
    # GPS evidence must win even if --timezone disagrees (design §8.2 追補).
    existing = DateCandidate(value=datetime(2017, 11, 7, 8, 40, 23), source_tag="EXIF:DateTimeOriginal")
    gps = utc(2017, 11, 6, 23, 40, 13)
    d = decide(
        existing,
        sidecar(utc(2017, 11, 6, 23, 40, 23)),
        gps_utc=gps,
        cli_offset_seconds=32400,
    )
    assert d.status == Status.EXIF_JSON_MATCH_TZ_GPS
    assert d.timezone_source == TzSource.GPS

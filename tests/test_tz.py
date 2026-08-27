from datetime import datetime, timezone

from photo_date_restore.tz import (
    format_offset,
    gps_derived_offset,
    implied_offset_seconds,
    round_to_quarter_hour,
)


def test_round_to_quarter_hour_exact():
    assert round_to_quarter_hour(32400) == 32400  # +09:00


def test_round_to_quarter_hour_within_tolerance():
    assert round_to_quarter_hour(32400 + 10) == 32400
    assert round_to_quarter_hour(32400 - 10) == 32400


def test_round_to_quarter_hour_nepal_and_eucla():
    assert round_to_quarter_hour(20700) == 20700  # +05:45
    assert round_to_quarter_hour(31500) == 31500  # +08:45


def test_round_to_quarter_hour_rejects_non_quarter_hour():
    # 300s off any 900s multiple is well outside the +/-90s tolerance.
    assert round_to_quarter_hour(7200 + 300) is None


def test_round_to_quarter_hour_boundary_14h():
    assert round_to_quarter_hour(50400) == 50400  # exactly +14:00, still valid
    # Nearest quarter-hour to this delta is +14:15, which exceeds the 14h cap.
    assert round_to_quarter_hour(51300) is None


def test_round_to_quarter_hour_rejects_beyond_14h():
    assert round_to_quarter_hour(15 * 3600) is None


def test_implied_offset_seconds_matches_real_data():
    local_naive = datetime(2017, 11, 7, 8, 40, 23)
    json_utc = datetime(2017, 11, 6, 23, 40, 23, tzinfo=timezone.utc)
    assert implied_offset_seconds(local_naive, json_utc) == 32400


def test_gps_derived_offset_absorbs_fix_delay():
    local_naive = datetime(2017, 11, 7, 8, 40, 23)
    gps_utc = datetime(2017, 11, 6, 23, 40, 13, 390000, tzinfo=timezone.utc)
    assert gps_derived_offset(local_naive, gps_utc) == 32400


def test_format_offset():
    assert format_offset(32400) == "+09:00"
    assert format_offset(-32400) == "-09:00"
    assert format_offset(20700) == "+05:45"

from datetime import datetime, timezone

from photo_date_restore.fsdates import get_mtime, mtime_matches, set_mtime


def test_set_and_get_mtime_roundtrip(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    target = datetime(2017, 11, 7, 8, 40, 23, tzinfo=timezone.utc)
    set_mtime(f, target)
    got = get_mtime(f)
    assert abs((got - target).total_seconds()) < 1


def test_mtime_matches_within_tolerance(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    target = datetime(2017, 11, 7, 8, 40, 23, tzinfo=timezone.utc)
    set_mtime(f, target)
    assert mtime_matches(f, target) is True
    assert mtime_matches(f, datetime(2020, 1, 1, tzinfo=timezone.utc)) is False

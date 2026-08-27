from datetime import datetime

from photo_date_restore.metaread import (
    extract_existing_candidate,
    extract_explicit_offset_seconds,
    extract_gps_datetime,
    parse_exif_datetime,
)


def test_priority_prefers_datetime_original():
    tags = {
        "EXIF:DateTimeOriginal": "2017:11:07 08:40:23",
        "EXIF:CreateDate": "2017:11:07 09:00:00",
    }
    c = extract_existing_candidate(tags)
    assert c.source_tag == "EXIF:DateTimeOriginal"
    assert c.value == datetime(2017, 11, 7, 8, 40, 23)


def test_falls_back_to_create_date():
    tags = {"EXIF:CreateDate": "2017:11:07 09:00:00"}
    c = extract_existing_candidate(tags)
    assert c.source_tag == "EXIF:CreateDate"


def test_falls_back_to_xmp_photoshop_date_created():
    # ExifTool's -G0 output collapses XMP-photoshop:DateCreated to "XMP:DateCreated".
    tags = {"XMP:DateCreated": "2017:11:07 08:48:03"}
    c = extract_existing_candidate(tags)
    assert c.source_tag == "XMP:DateCreated"


def test_ignores_blacklisted_tags():
    tags = {
        "XMP:MetadataDate": "2026:03:26 13:59:54+09:00",
        "ICC-header:ProfileDateTime": "1998:02:09 00:00:00",
        "File:FileModifyDate": "2026:08:26 20:05:00+09:00",
    }
    assert extract_existing_candidate(tags) is None


def test_modify_date_is_last_resort():
    tags = {"EXIF:ModifyDate": "2017:11:07 08:40:23"}
    c = extract_existing_candidate(tags)
    assert c.source_tag == "EXIF:ModifyDate"


def test_no_tags_present():
    assert extract_existing_candidate({}) is None


def test_midnight_24_00_00_normalizes_to_next_day():
    dt = parse_exif_datetime("2020:01:01 24:00:00")
    assert dt == datetime(2020, 1, 2, 0, 0, 0)


def test_zero_date_is_none():
    assert parse_exif_datetime("0000:00:00 00:00:00") is None


def test_explicit_offset_parsing():
    assert extract_explicit_offset_seconds({"EXIF:OffsetTimeOriginal": "+09:00"}) == 32400
    assert extract_explicit_offset_seconds({"EXIF:OffsetTimeOriginal": "-05:30"}) == -19800
    assert extract_explicit_offset_seconds({}) is None


def test_gps_datetime_parsing_is_aware_utc():
    dt = extract_gps_datetime({"Composite:GPSDateTime": "2017:11:06 23:40:13.39Z"})
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0
    assert dt.replace(tzinfo=None) == datetime(2017, 11, 6, 23, 40, 13, 390000)

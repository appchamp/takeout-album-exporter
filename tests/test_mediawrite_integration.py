"""Integration tests for mediawrite.write_media_datetime against real ExifTool.

Operates only on copies made into tmp_path — never touches sources/Takeout.
"""
from datetime import datetime

from photo_date_restore import exiftool_client as et
from photo_date_restore.mediawrite import write_media_datetime

from conftest import copy_sample, requires_exiftool, requires_real_samples


@requires_exiftool
@requires_real_samples
def test_write_jpeg_datetime_preserves_dimensions_and_verifies(tmp_path):
    jpg = copy_sample("Google フォト/集合写真/DSC08207.jpg", tmp_path)
    before = et.read_tags(jpg)
    outcome = write_media_datetime("JPEG", jpg, datetime(2026, 3, 25, 21, 59, 54), 32400)
    assert outcome.success
    assert outcome.verified, outcome.error

    after = et.read_tags(jpg)
    assert after["EXIF:DateTimeOriginal"] == "2026:03:25 21:59:54"
    assert after["EXIF:OffsetTimeOriginal"] == "+09:00"
    assert after["File:ImageWidth"] == before["File:ImageWidth"]
    assert after["File:ImageHeight"] == before["File:ImageHeight"]
    assert after["File:FileType"] == "JPEG"

    et.discard_original_backup(jpg)
    assert not jpg.with_name(jpg.name + "_original").exists()


@requires_exiftool
@requires_real_samples
def test_write_jpeg_preserves_existing_xmp_and_icc(tmp_path):
    jpg = copy_sample("Google フォト/集合写真/DSC08207.jpg", tmp_path)
    before_all = et.read_tags(jpg)  # sanity: has some metadata already (XMP:MetadataDate)
    assert "XMP:MetadataDate" in before_all

    outcome = write_media_datetime("JPEG", jpg, datetime(2026, 3, 25, 21, 59, 54), 32400)
    assert outcome.success and outcome.verified

    after_all = et.read_tags(jpg)
    assert after_all.get("XMP:MetadataDate") == before_all.get("XMP:MetadataDate")
    et.discard_original_backup(jpg)


@requires_exiftool
@requires_real_samples
def test_write_png_datetime_via_xmp(tmp_path):
    png = copy_sample("Google フォト/第１９回図書館総合展/IMG_6498.PNG", tmp_path)
    outcome = write_media_datetime("PNG", png, datetime(2017, 11, 7, 8, 48, 3), 32400)
    assert outcome.success
    assert outcome.verified, outcome.error

    after = et.read_tags(png)
    assert after["XMP:DateCreated"] == "2017:11:07 08:48:03+09:00"
    assert after["File:FileType"] == "PNG"
    et.discard_original_backup(png)


@requires_exiftool
@requires_real_samples
def test_idempotent_second_write_is_a_noop_value(tmp_path):
    jpg = copy_sample("Google フォト/集合写真/DSC08211.jpg", tmp_path)
    dt = datetime(2026, 3, 25, 21, 57, 10)
    write_media_datetime("JPEG", jpg, dt, 32400)
    et.discard_original_backup(jpg)
    size_after_first = jpg.stat().st_size

    outcome2 = write_media_datetime("JPEG", jpg, dt, 32400)
    assert outcome2.success and outcome2.verified
    et.discard_original_backup(jpg)
    # Re-writing the identical value must not grow the file a second time.
    assert jpg.stat().st_size == size_after_first

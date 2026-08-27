"""Integration tests for pipeline.run() using copies of the real sample data.

Never touches sources/Takeout; every test copies into tmp_path first.
"""
import csv
import shutil
from pathlib import Path

import photo_date_restore.pipeline as pipeline_module
from photo_date_restore.models import Status
from photo_date_restore.pipeline import Options, run

from conftest import SOURCES_TAKEOUT, requires_exiftool, requires_real_samples


def make_takeout_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "Takeout"
    shutil.copytree(SOURCES_TAKEOUT, dest)
    return dest


@requires_exiftool
@requires_real_samples
def test_dry_run_makes_no_filesystem_changes(tmp_path):
    src = make_takeout_copy(tmp_path)
    before = _snapshot(src)
    out = tmp_path / "out"
    rows = run(Options(input=src, output=out, apply=False))
    after = _snapshot(src)
    assert before == after
    assert not out.exists()
    assert len(rows) == 22  # 18 + 4 media files


@requires_exiftool
@requires_real_samples
def test_library_expo_album_gps_tz_inferred(tmp_path):
    src = make_takeout_copy(tmp_path)
    out = tmp_path / "out"
    rows = run(Options(input=src, output=out, apply=False))
    album_rows = [r for r in rows if r["album_name"] == "第１９回図書館総合展"]
    jpg_rows = [r for r in album_rows if r["file_type"] == "JPEG"]
    assert len(jpg_rows) == 17
    for r in jpg_rows:
        assert r["status"] == Status.EXIF_JSON_MATCH_TZ_GPS.value
        assert r["difference_seconds"] == 32400
        assert r["timezone_source"] == "GPS"
        assert r["planned_metadata_action"] == "NONE"

    png_rows = [r for r in album_rows if r["file_type"] == "PNG"]
    assert len(png_rows) == 1
    # IMG_6498.PNG has XMP:DateCreated (whitelisted, §6.1) so it takes the
    # case-A (existing-metadata) path; siblings' GPS-confirmed +09:00 backs
    # the match since the PNG itself has no GPS/offset tag of its own.
    assert png_rows[0]["status"] == Status.EXIF_JSON_MATCH_TZ_INFERRED.value
    assert png_rows[0]["timezone_source"] == "INFERRED"
    assert png_rows[0]["planned_metadata_action"] == "NONE"


@requires_exiftool
@requires_real_samples
def test_group_photo_album_without_timezone_is_mtime_only(tmp_path):
    src = make_takeout_copy(tmp_path)
    out = tmp_path / "out"
    rows = run(Options(input=src, output=out, apply=False))
    album_rows = [r for r in rows if r["album_name"] == "集合写真"]
    assert len(album_rows) == 4
    for r in album_rows:
        assert r["status"] == Status.JSON_TIME_MTIME_ONLY.value
        assert "TIMEZONE_REQUIRED_FOR_METADATA" in r["message"]
        assert r["planned_metadata_action"] == "SKIP_TIMEZONE_REQUIRED"


@requires_exiftool
@requires_real_samples
def test_group_photo_album_with_explicit_timezone_writes_metadata(tmp_path):
    src = make_takeout_copy(tmp_path)
    out = tmp_path / "out"
    rows = run(Options(input=src, output=out, apply=False, timezone="Asia/Tokyo"))
    album_rows = [r for r in rows if r["album_name"] == "集合写真"]
    for r in album_rows:
        assert r["status"] == Status.JSON_TIME_USED.value
        assert r["timezone_source"] == "CLI"


@requires_exiftool
@requires_real_samples
def test_sibling_inference_still_wins_over_cli_timezone(tmp_path):
    # Regression: --timezone must not pre-empt a same-directory GPS-confirmed
    # sibling match just because it was available before siblings were known
    # (design §8.2 追補 priority: EXPLICIT > GPS > INFERRED > CLI).
    src = make_takeout_copy(tmp_path)
    out = tmp_path / "out"
    rows = run(Options(input=src, output=out, apply=False, timezone="Asia/Tokyo"))
    png_rows = [r for r in rows if r["file_type"] == "PNG"]
    assert len(png_rows) == 1
    assert png_rows[0]["status"] == Status.EXIF_JSON_MATCH_TZ_INFERRED.value
    assert png_rows[0]["timezone_source"] == "INFERRED"


@requires_exiftool
@requires_real_samples
def test_copy_apply_then_idempotent_second_run(tmp_path, monkeypatch):
    src = make_takeout_copy(tmp_path)
    src_snapshot_before = _snapshot(src)
    out = tmp_path / "out"

    rows1 = run(Options(input=src, output=out, apply=True, timezone="Asia/Tokyo"))
    assert all(r["status"] != Status.ERROR.value for r in rows1)
    assert all(r["status"] != Status.AMBIGUOUS_JSON.value for r in rows1)
    assert all(r["status"] != Status.EXIF_JSON_CONFLICT.value for r in rows1)

    # sources/ (the copy standing in for it) must be untouched by copy mode.
    assert _snapshot(src) == src_snapshot_before

    out_files = sorted(p for p in out.rglob("*") if p.is_file())
    assert len(out_files) == 22
    assert all(not name.endswith(".json") for name in (p.name for p in out_files))
    out_hashes_1 = {p: _sha256(p) for p in out_files}

    write_calls = []
    original_write = pipeline_module.write_media_datetime

    def counted_write(*args, **kwargs):
        write_calls.append(args[1])
        return original_write(*args, **kwargs)

    monkeypatch.setattr("photo_date_restore.pipeline.write_media_datetime", counted_write)
    rows2 = run(Options(input=src, output=out, apply=True, timezone="Asia/Tokyo"))
    statuses2 = {r["status"] for r in rows2}
    assert statuses2 == {Status.NO_CHANGE.value}
    assert write_calls == []

    out_hashes_2 = {p: _sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}
    assert out_hashes_1 == out_hashes_2

    # No leftover ExifTool backups.
    assert not list(out.rglob("*_original"))


@requires_exiftool
@requires_real_samples
def test_in_place_on_a_copy_never_touches_the_real_source(tmp_path):
    # This exercises --in-place, but ONLY against a tmp_path copy — never
    # against sources/Takeout itself (forbidden by the task).
    src = make_takeout_copy(tmp_path)
    real_source_snapshot = _snapshot(SOURCES_TAKEOUT)

    rows = run(Options(input=src, in_place=True, apply=True, timezone="Asia/Tokyo"))
    assert any(r["status"] == Status.JSON_TIME_USED.value for r in rows)

    assert _snapshot(SOURCES_TAKEOUT) == real_source_snapshot
    assert not list(src.rglob("*_original"))
    # JSON sidecars remain (no --move-json requested).
    assert list(src.rglob("*.supplemental-metadata.json"))


@requires_exiftool
@requires_real_samples
def test_in_place_move_json_builds_index_on_a_copy_and_second_run_is_no_json(tmp_path, monkeypatch):
    src = make_takeout_copy(tmp_path)
    real_source_snapshot = _snapshot(SOURCES_TAKEOUT)
    vault = tmp_path / "json-vault"

    rows1 = run(Options(
        input=src,
        in_place=True,
        apply=True,
        timezone="Asia/Tokyo",
        move_json=vault,
    ))

    assert len(rows1) == 22
    assert {row["planned_json_action"] for row in rows1} == {"MOVED"}
    assert not list(src.rglob("*.supplemental-metadata.json"))
    assert len(list(src.rglob("メタデータ.json"))) == 2
    index = vault / "_sidecar_index.csv"
    with index.open(newline="", encoding="utf-8") as f:
        index_rows = list(csv.DictReader(f))
    assert len(index_rows) == 22
    assert set(index_rows[0]) == set(pipeline_module.SIDECAR_INDEX_COLUMNS)
    assert {row["status"] for row in index_rows} == {"MOVED"}

    index_before = index.read_bytes()
    write_calls = []

    def unexpected_write(*args, **kwargs):
        write_calls.append(args)
        raise AssertionError("second run must not write metadata without a sidecar")

    monkeypatch.setattr(pipeline_module, "write_media_datetime", unexpected_write)
    rows2 = run(Options(
        input=src,
        in_place=True,
        apply=True,
        timezone="Asia/Tokyo",
        move_json=vault,
    ))

    assert {row["status"] for row in rows2} == {Status.NO_JSON.value}
    assert {row["planned_json_action"] for row in rows2} == {"SKIP_STATUS"}
    assert write_calls == []
    assert index.read_bytes() == index_before
    assert _snapshot(SOURCES_TAKEOUT) == real_source_snapshot


def _snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, _sha256(p))
    return out


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

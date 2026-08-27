import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from photo_date_restore import exiftool_client as et
from photo_date_restore import jsonmeta
from photo_date_restore.models import Status
from photo_date_restore.pipeline import Options, run


TAKEN_TIMESTAMP = "1577836800"  # 2020-01-01T00:00:00Z
TAKEN_UTC = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _media(tmp_path: Path) -> Path:
    media = tmp_path / "input" / "album" / "image.jpg"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"unchanged-media")
    return media


def _sidecar(media: Path, content=None) -> Path:
    sidecar = media.with_name(media.name + ".supplemental-metadata.json")
    if content is None:
        content = json.dumps({
            "title": media.name,
            "photoTakenTime": {"timestamp": TAKEN_TIMESTAMP},
        })
    sidecar.write_text(content, encoding="utf-8")
    return sidecar


def _mock_no_existing_metadata(monkeypatch):
    def fake_read(paths, exiftool_path="exiftool"):
        return {str(path): {"File:FileType": "JPEG"} for path in paths}

    monkeypatch.setattr(et, "read_tags_batch", fake_read)


def _media_snapshot(media: Path):
    stat = media.stat()
    return media.read_bytes(), stat.st_size, stat.st_mtime_ns


def test_no_sidecar_is_no_json(tmp_path, monkeypatch):
    media = _media(tmp_path)
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", output=tmp_path / "out"))

    assert len(rows) == 1
    assert rows[0]["status"] == Status.NO_JSON.value
    assert rows[0]["json_sidecar"] == ""
    assert media.exists()


def test_malformed_sidecar_is_error_with_reported_cause(tmp_path, monkeypatch):
    media = _media(tmp_path)
    sidecar = _sidecar(media, "{not valid json")
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", output=tmp_path / "out"))

    assert len(rows) == 1
    assert rows[0]["status"] == Status.ERROR.value
    assert rows[0]["json_sidecar"] == sidecar.name
    assert "SIDECAR_PARSE_ERROR" in rows[0]["error"]
    assert "could not decode/parse" in rows[0]["error"]
    assert rows[0]["planned_metadata_action"] == "NONE"
    assert rows[0]["planned_mtime_action"] == "NONE"
    assert not (tmp_path / "out").exists()


def test_sidecar_filename_with_missing_required_times_is_error(tmp_path, monkeypatch):
    media = _media(tmp_path)
    sidecar = _sidecar(media, json.dumps({"title": media.name}))
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", output=tmp_path / "out"))

    assert rows[0]["status"] == Status.ERROR.value
    assert rows[0]["json_sidecar"] == sidecar.name
    assert "no usable photoTakenTime or creationTime" in rows[0]["error"]
    assert not (tmp_path / "out").exists()


def test_valid_sidecar_keeps_existing_behavior(tmp_path, monkeypatch):
    media = _media(tmp_path)
    _sidecar(media)
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", output=tmp_path / "out"))

    assert rows[0]["status"] == Status.JSON_TIME_MTIME_ONLY.value
    assert rows[0]["planned_mtime_action"] == "SET"


def test_malformed_sidecar_does_not_stop_other_media(tmp_path, monkeypatch):
    bad_media = _media(tmp_path)
    _sidecar(bad_media, "{not valid json")
    good_media = bad_media.with_name("good.jpg")
    good_media.write_bytes(b"good-media")
    _sidecar(good_media)
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", output=tmp_path / "out"))
    by_name = {Path(row["file"]).name: row for row in rows}

    assert by_name["image.jpg"]["status"] == Status.ERROR.value
    assert by_name["image.jpg"]["status"] != Status.AMBIGUOUS_JSON.value
    assert by_name["good.jpg"]["status"] == Status.JSON_TIME_MTIME_ONLY.value


def test_malformed_sidecar_apply_leaves_media_unchanged(tmp_path, monkeypatch):
    media = _media(tmp_path)
    sidecar = _sidecar(media, "{not valid json")
    before_media = _media_snapshot(media)
    before_sidecar = sidecar.read_bytes()
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", in_place=True, apply=True))

    assert rows[0]["status"] == Status.ERROR.value
    assert _media_snapshot(media) == before_media
    assert sidecar.read_bytes() == before_sidecar


def test_malformed_sidecar_is_not_moved(tmp_path, monkeypatch):
    media = _media(tmp_path)
    sidecar = _sidecar(media, "{not valid json")
    vault = tmp_path / "vault"
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(
        input=tmp_path / "input",
        in_place=True,
        apply=True,
        move_json=vault,
    ))

    assert rows[0]["status"] == Status.ERROR.value
    assert rows[0]["planned_json_action"] == "SKIP_STATUS"
    assert sidecar.exists()
    assert not vault.exists()


def test_unreadable_sidecar_is_reported_as_error(tmp_path, monkeypatch):
    media = _media(tmp_path)
    sidecar = _sidecar(media)
    original_load = jsonmeta.load_sidecar

    def fail_selected_sidecar(path):
        if path == sidecar:
            raise jsonmeta.JsonParseError(f"could not read {path}: permission denied")
        return original_load(path)

    monkeypatch.setattr(jsonmeta, "load_sidecar", fail_selected_sidecar)
    _mock_no_existing_metadata(monkeypatch)

    rows = run(Options(input=tmp_path / "input", output=tmp_path / "out"))

    assert rows[0]["status"] == Status.ERROR.value
    assert "permission denied" in rows[0]["error"]
    assert not (tmp_path / "out").exists()


def test_mtime_only_dry_run_reports_apply_value_without_changing_file(tmp_path, monkeypatch):
    media = _media(tmp_path)
    _sidecar(media)
    before = _media_snapshot(media)
    _mock_no_existing_metadata(monkeypatch)

    dry_rows = run(Options(input=tmp_path / "input", in_place=True, apply=False))

    assert dry_rows[0]["status"] == Status.JSON_TIME_MTIME_ONLY.value
    assert dry_rows[0]["planned_mtime_action"] == "SET"
    assert datetime.fromisoformat(dry_rows[0]["new_mtime"]) == TAKEN_UTC
    assert _media_snapshot(media) == before

    apply_rows = run(Options(input=tmp_path / "input", in_place=True, apply=True))

    assert datetime.fromisoformat(apply_rows[0]["new_mtime"]) == TAKEN_UTC
    assert media.stat().st_mtime == pytest.approx(TAKEN_UTC.timestamp(), abs=0.001)
    assert apply_rows[0]["new_mtime"] == dry_rows[0]["new_mtime"]

"""Focused tests for safe --move-json behavior."""
import csv
import json
from pathlib import Path

import pytest

import photo_date_restore.pipeline as pipeline_module
from photo_date_restore import exiftool_client as et
from photo_date_restore.models import Status
from photo_date_restore.pipeline import Options, run


TAKEN_TIMESTAMP = "1577836800"  # 2020-01-01T00:00:00Z


def _media(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media-bytes")
    return path


def _sidecar(media: Path, suffix: str = ".json") -> Path:
    path = media.with_name(media.name + suffix)
    path.write_text(
        json.dumps({"title": media.name, "photoTakenTime": {"timestamp": TAKEN_TIMESTAMP}}),
        encoding="utf-8",
    )
    return path


def _album_metadata(directory: Path) -> Path:
    path = directory / "メタデータ.json"
    path.write_text(json.dumps({"title": directory.name}), encoding="utf-8")
    return path


def _mock_tags(monkeypatch, existing_by_name=None):
    existing_by_name = existing_by_name or {}

    def fake_read(paths, exiftool_path="exiftool"):
        records = {}
        for path in paths:
            existing = existing_by_name.get(path.name, "2020:01:01 00:00:00")
            tags = {"File:FileType": "JPEG"}
            if existing is not None:
                tags["EXIF:DateTimeOriginal"] = existing
            records[str(path)] = tags
        return records

    monkeypatch.setattr(et, "read_tags_batch", fake_read)


def test_move_json_dry_run_only_reports_plan(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album-a/IMG_0001.JPG")
    sidecar = _sidecar(media, ".supplemental-metadata.json")
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    rows = run(Options(input=root, in_place=True, apply=False, move_json=vault))

    assert sidecar.exists()
    assert not vault.exists()
    assert rows[0]["planned_json_action"] == "MOVE"
    assert rows[0]["planned_json_destination"] == str(
        vault / "album-a/IMG_0001.JPG.supplemental-metadata.json"
    )


def test_apply_moves_only_successful_sidecar(tmp_path, monkeypatch):
    root = tmp_path / "input"
    good_media = _media(root, "album/good.jpg")
    bad_media = _media(root, "album/conflict.jpg")
    good_json = _sidecar(good_media)
    bad_json = _sidecar(bad_media)
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch, {"conflict.jpg": "2020:01:01 00:05:00"})

    rows = run(Options(input=root, in_place=True, apply=True, move_json=vault))
    by_name = {Path(row["file"]).name: row for row in rows}

    assert not good_json.exists()
    assert (vault / "album/good.jpg.json").read_bytes()
    assert bad_json.exists()
    assert not (vault / "album/conflict.jpg.json").exists()
    assert by_name["good.jpg"]["planned_json_action"] == "MOVED"
    assert by_name["conflict.jpg"]["status"] == Status.EXIF_JSON_CONFLICT.value
    assert by_name["conflict.jpg"]["planned_json_action"] == "SKIP_STATUS"
    index = vault / "_sidecar_index.csv"
    assert not index.read_bytes().startswith(b"\xef\xbb\xbf")
    with index.open(newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == [{
            "media_relative_path": "album/good.jpg",
            "original_sidecar_relative_path": "album/good.jpg.json",
            "moved_sidecar_relative_path": "album/good.jpg.json",
            "status": "MOVED",
        }]


def test_ambiguous_json_is_not_moved(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    first = _sidecar(media)
    second = _sidecar(media, ".supplemental-metadata.json")
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    rows = run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert rows[0]["status"] == Status.AMBIGUOUS_JSON.value
    assert rows[0]["planned_json_action"] == "SKIP_STATUS"
    assert first.exists() and second.exists()
    assert not vault.exists()


def test_album_metadata_is_never_moved(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    sidecar = _sidecar(media)
    album_json = _album_metadata(media.parent)
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert not sidecar.exists()
    assert album_json.exists()
    assert not (vault / "album/メタデータ.json").exists()


def test_move_preserves_relative_path_and_never_moves_media(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "a/b/c/image.jpg")
    original_media = media.read_bytes()
    sidecar = _sidecar(media)
    original_json = sidecar.read_bytes()
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert media.exists() and media.read_bytes() == original_media
    assert not sidecar.exists()
    assert (vault / "a/b/c/image.jpg.json").read_bytes() == original_json


def test_destination_collision_never_overwrites(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    sidecar = _sidecar(media)
    vault = tmp_path / "vault"
    collision = vault / "album/image.jpg.json"
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing-backup")
    _mock_tags(monkeypatch)

    rows = run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert sidecar.exists()
    assert collision.read_bytes() == b"existing-backup"
    assert rows[0]["planned_json_action"] == "SKIP_DESTINATION_EXISTS"
    assert "JSON_DESTINATION_EXISTS" in rows[0]["message"]
    assert not (vault / "_sidecar_index.csv").exists()


def test_second_run_after_move_is_non_destructive(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    _sidecar(media)
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    first = run(Options(input=root, in_place=True, apply=True, move_json=vault))
    moved = vault / "album/image.jpg.json"
    moved_bytes = moved.read_bytes()
    media_bytes = media.read_bytes()
    second = run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert first[0]["planned_json_action"] == "MOVED"
    assert second[0]["status"] == Status.NO_JSON.value
    assert second[0]["planned_json_action"] == "SKIP_STATUS"
    assert moved.read_bytes() == moved_bytes
    assert media.read_bytes() == media_bytes
    with (vault / "_sidecar_index.csv").open(newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 1


def test_mtime_only_partial_result_keeps_sidecar(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    sidecar = _sidecar(media)
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch, {"image.jpg": None})

    rows = run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert rows[0]["status"] == Status.JSON_TIME_MTIME_ONLY.value
    assert rows[0]["planned_json_action"] == "SKIP_STATUS"
    assert sidecar.exists()
    assert not vault.exists()


def test_move_json_rejects_copy_mode_and_destination_inside_input(tmp_path):
    root = tmp_path / "input"
    root.mkdir()

    with pytest.raises(ValueError, match="requires --in-place"):
        run(Options(input=root, output=tmp_path / "out", move_json=tmp_path / "vault"))
    with pytest.raises(ValueError, match="outside INPUT"):
        run(Options(input=root, in_place=True, move_json=root / "vault"))


def test_move_json_rejects_destination_under_sources(tmp_path, monkeypatch):
    root = tmp_path / "input"
    root.mkdir()
    protected = tmp_path / "sources"
    monkeypatch.setattr(pipeline_module, "PROTECTED_SOURCES_ROOT", protected)

    with pytest.raises(ValueError, match="outside sources/"):
        run(Options(input=root, in_place=True, apply=True, move_json=protected / "vault"))


def test_existing_index_is_preserved_and_duplicate_mapping_is_not_added(tmp_path, monkeypatch):
    root = tmp_path / "input"
    first_media = _media(root, "album/first.jpg")
    second_media = _media(root, "album/second.jpg")
    _sidecar(first_media)
    _sidecar(second_media)
    vault = tmp_path / "vault"
    vault.mkdir()
    index = vault / "_sidecar_index.csv"
    fieldnames = [*pipeline_module.SIDECAR_INDEX_COLUMNS, "note"]
    with index.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "media_relative_path": "album/first.jpg",
            "original_sidecar_relative_path": "album/first.jpg.json",
            "moved_sidecar_relative_path": "album/first.jpg.json",
            "status": "MOVED",
            "note": "keep me",
        })
    _mock_tags(monkeypatch)

    run(Options(input=root, in_place=True, apply=True, move_json=vault))

    with index.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["note"] == "keep me"
    assert rows[1]["media_relative_path"] == "album/second.jpg"
    assert rows[1]["note"] == ""


def test_index_failure_rolls_sidecar_back_and_reports_error(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    sidecar = _sidecar(media)
    original = sidecar.read_bytes()
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    def fail_index(index_root, entry):
        raise OSError("simulated index failure")

    monkeypatch.setattr(pipeline_module, "_append_sidecar_index", fail_index)
    rows = run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert rows[0]["status"] == Status.ERROR.value
    assert rows[0]["planned_json_action"] == "ERROR"
    assert "simulated index failure" in rows[0]["error"]
    assert sidecar.read_bytes() == original
    assert not (vault / "album/image.jpg.json").exists()
    assert not (vault / "_sidecar_index.csv").exists()


def test_move_failure_is_reported_as_error(tmp_path, monkeypatch):
    root = tmp_path / "input"
    media = _media(root, "album/image.jpg")
    sidecar = _sidecar(media)
    vault = tmp_path / "vault"
    _mock_tags(monkeypatch)

    def fail_move(source, destination):
        raise OSError("simulated move failure")

    monkeypatch.setattr(pipeline_module, "_move_without_overwrite", fail_move)
    rows = run(Options(input=root, in_place=True, apply=True, move_json=vault))

    assert sidecar.exists()
    assert rows[0]["status"] == Status.ERROR.value
    assert rows[0]["planned_json_action"] == "ERROR"
    assert "simulated move failure" in rows[0]["error"]

"""Unit tests for photo_date_restore.jsonmeta."""
import json

import pytest

from photo_date_restore.jsonmeta import JsonParseError, load_sidecar


def write_json(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_media_sidecar_classified_correctly(tmp_path):
    p = write_json(tmp_path, "a.json", {
        "title": "a.jpg",
        "photoTakenTime": {"timestamp": "1510011623", "formatted": "x"},
        "creationTime": {"timestamp": "1510016412", "formatted": "x"},
    })
    info = load_sidecar(p)
    assert info.is_album_metadata is False
    assert info.title == "a.jpg"
    assert info.photo_taken_time.timestamp() == 1510011623
    assert info.creation_time.timestamp() == 1510016412


def test_album_metadata_excluded_no_timestamps(tmp_path):
    p = write_json(tmp_path, "メタデータ.json", {"title": "サンプルアルバム"})
    info = load_sidecar(p)
    assert info.is_album_metadata is True


def test_album_metadata_with_date_key_still_excluded(tmp_path):
    p = write_json(tmp_path, "メタデータ.json", {
        "title": "サンプルアルバム", "date": {"timestamp": "1774575640", "formatted": "x"},
    })
    info = load_sidecar(p)
    assert info.is_album_metadata is True


def test_negative_sidecar_timestamp_is_parse_error(tmp_path):
    p = write_json(tmp_path, "a.json", {
        "title": "a.jpg", "photoTakenTime": {"timestamp": "-5", "formatted": "x"},
    })
    with pytest.raises(JsonParseError, match="invalid photoTakenTime.timestamp"):
        load_sidecar(p)


def test_far_future_sidecar_timestamp_is_parse_error(tmp_path):
    p = write_json(tmp_path, "a.json", {
        "title": "a.jpg", "photoTakenTime": {"timestamp": "9999999999", "formatted": "x"},
    })
    with pytest.raises(JsonParseError, match="invalid photoTakenTime.timestamp"):
        load_sidecar(p)

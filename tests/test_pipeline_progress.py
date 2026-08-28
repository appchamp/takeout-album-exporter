"""Progress callback tests for the pipeline wrapper and metadata read batches."""
import json
import threading
from pathlib import Path

from photo_date_restore import exiftool_client as et
from photo_date_restore import pipeline
from photo_date_restore.models import Status
from photo_date_restore.pipeline import Options, process_directory, run
from photo_date_restore.report import write_report


def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "input"
    root.mkdir()
    (root / "one.jpg").write_bytes(b"one")
    child = root / "child"
    child.mkdir()
    (child / "two.jpg").write_bytes(b"two")
    return root


def test_run_without_progress_matches_explicit_none(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    monkeypatch.setattr(
        "photo_date_restore.pipeline.process_directory",
        lambda directory, _opts: [{"directory": directory.name}],
    )
    opts = Options(input=root, output=tmp_path / "out")

    assert run(opts) == run(opts, progress=None)


def test_progress_is_notified_once_per_discovered_directory(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    monkeypatch.setattr("photo_date_restore.pipeline.process_directory", lambda _directory, _opts: [])
    observed = []

    run(
        Options(input=root, output=tmp_path / "out"),
        progress=lambda done, total, directory: observed.append((done, total, directory)),
    )

    assert [done for done, _total, _directory in observed] == [1, 2]
    assert [total for _done, total, _directory in observed] == [2, 2]
    assert all(isinstance(directory, Path) for _done, _total, directory in observed)


def test_progress_exceptions_do_not_change_result(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    monkeypatch.setattr(
        "photo_date_restore.pipeline.process_directory",
        lambda directory, _opts: [{"directory": directory.name}],
    )
    opts = Options(input=root, output=tmp_path / "out")

    expected = run(opts)
    actual = run(opts, progress=lambda *_args: (_ for _ in ()).throw(RuntimeError("ignore me")))

    assert actual == expected


def test_file_progress_notifies_each_row_with_continuing_indexes(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)

    def fake_process_directory(directory, _opts, on_row=None):
        row = {"relative_path": f"{directory.name}.jpg", "status": "NO_CHANGE"}
        if on_row is not None:
            on_row(row)
        return [row]

    monkeypatch.setattr("photo_date_restore.pipeline.process_directory", fake_process_directory)
    observed = []

    rows = run(
        Options(input=root, output=tmp_path / "out"),
        file_progress=lambda index, row: observed.append((index, row)),
    )

    assert [index for index, _row in observed] == [1, 2]
    assert [row for _index, row in observed] == rows
    assert all("relative_path" in row and "status" in row for _index, row in observed)


def test_file_progress_exceptions_do_not_change_result(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)

    def fake_process_directory(directory, _opts, on_row=None):
        row = {"directory": directory.name}
        if on_row is not None:
            on_row(row)
        return [row]

    monkeypatch.setattr("photo_date_restore.pipeline.process_directory", fake_process_directory)
    opts = Options(input=root, output=tmp_path / "out")

    expected = run(opts, file_progress=None)
    actual = run(
        opts,
        file_progress=lambda *_args: (_ for _ in ()).throw(RuntimeError("ignore me")),
    )

    assert actual == expected


def test_directory_start_precedes_processing_once_per_directory(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    events = []

    def fake_process(directory, _opts):
        events.append(("process", directory))
        return []

    monkeypatch.setattr("photo_date_restore.pipeline.process_directory", fake_process)

    run(
        Options(input=root, output=tmp_path / "out"),
        directory_start=lambda done, total, directory: events.append(("start", done, total, directory)),
    )

    assert [event[0] for event in events] == ["start", "process", "start", "process"]
    assert [event[1] for event in events if event[0] == "start"] == [1, 2]


def test_directory_start_exceptions_do_not_change_result(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    monkeypatch.setattr(
        "photo_date_restore.pipeline.process_directory",
        lambda directory, _opts: [{"directory": directory.name}],
    )
    opts = Options(input=root, output=tmp_path / "out")

    assert run(opts) == run(
        opts, directory_start=lambda *_args: (_ for _ in ()).throw(RuntimeError("ignore me")),
    )


def test_cancel_returns_rows_finalized_before_the_event(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    event = threading.Event()
    observed = []

    def fake_process(_directory, _opts, on_row=None, cancel_event=None):
        rows = []
        for name in ("first", "second"):
            if cancel_event is not None and cancel_event.is_set():
                break
            row = {"relative_path": f"{name}.jpg", "status": "NO_CHANGE"}
            rows.append(row)
            if on_row is not None:
                on_row(row)
        return rows

    monkeypatch.setattr("photo_date_restore.pipeline.process_directory", fake_process)

    rows = run(
        Options(input=root, output=tmp_path / "out"),
        file_progress=lambda _index, row: (observed.append(row), event.set()),
        cancel_event=event,
    )

    assert rows == [{"relative_path": "first.jpg", "status": "NO_CHANGE"}]
    assert observed == rows


def _metadata_tree(tmp_path: Path, count: int = 3) -> Path:
    directory = tmp_path / "input" / "album"
    directory.mkdir(parents=True)
    for index in range(count):
        media = directory / f"image-{index:03d}.jpg"
        media.write_bytes(b"media")
        media.with_name(media.name + ".supplemental-metadata.json").write_text(
            json.dumps({"title": media.name, "photoTakenTime": {"timestamp": "1577836800"}}),
            encoding="utf-8",
        )
    return directory


def _fake_tags(paths, exiftool_path="exiftool"):
    return {str(path): {"File:FileType": "JPEG"} for path in reversed(paths)}


def test_metadata_reads_are_batched_and_report_progress(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 250)
    calls = []
    observed = []

    def fake_read(paths, exiftool_path="exiftool"):
        calls.append(list(paths))
        return _fake_tags(paths, exiftool_path)

    monkeypatch.setattr(et, "read_tags_batch", fake_read)
    rows = process_directory(
        directory, Options(input=tmp_path / "input", output=tmp_path / "out"),
        metadata_progress=lambda *args: observed.append(args),
    )

    assert [len(call) for call in calls] == [50, 50, 50, 50, 50]
    assert observed == [
        (directory, 0, 250), (directory, 50, 250), (directory, 100, 250),
        (directory, 150, 250), (directory, 200, 250), (directory, 250, 250),
    ]
    assert len(rows) == 250


def test_metadata_progress_exceptions_do_not_stop_pipeline(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 2)
    monkeypatch.setattr(et, "read_tags_batch", _fake_tags)

    rows = process_directory(
        directory, Options(input=tmp_path / "input", output=tmp_path / "out"),
        metadata_progress=lambda *_args: (_ for _ in ()).throw(RuntimeError("ignore me")),
    )

    assert len(rows) == 2


def test_cancel_after_first_metadata_batch_starts_no_second_batch_or_analysis(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 250)
    event = threading.Event()
    calls = []
    decisions = []

    def fake_read(paths, exiftool_path="exiftool"):
        calls.append(list(paths))
        event.set()  # Simulate Cancel arriving while the first blocking read runs.
        return _fake_tags(paths, exiftool_path)

    monkeypatch.setattr(et, "read_tags_batch", fake_read)
    monkeypatch.setattr(pipeline, "_decide_all", lambda *args: decisions.append(args) or {})

    rows = process_directory(
        directory, Options(input=tmp_path / "input", output=tmp_path / "out"), cancel_event=event,
    )

    assert rows == []
    assert [len(call) for call in calls] == [50]
    assert decisions == []


def test_metadata_reads_run_all_batches_without_cancel_event(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 250)
    calls = []

    def fake_read(paths, exiftool_path="exiftool"):
        calls.append(list(paths))
        return _fake_tags(paths, exiftool_path)

    monkeypatch.setattr(et, "read_tags_batch", fake_read)
    assert len(process_directory(directory, Options(input=tmp_path / "input", output=tmp_path / "out"))) == 250
    assert [len(call) for call in calls] == [50, 50, 50, 50, 50]


def test_batched_metadata_preserves_old_rows_status_timestamps_and_audit_report(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 4)
    media = sorted(directory.glob("*.jpg"))

    def fake_read(paths, exiftool_path="exiftool"):
        tags = {}
        for path in reversed(paths):
            tags[str(path)] = {
                "File:FileType": "JPEG",
                "EXIF:DateTimeOriginal": "2020:01:01 09:00:00",
            }
            if path.name != media[-1].name:
                tags[str(path)]["Composite:GPSDateTime"] = "2020:01:01 00:00:00Z"
        return tags

    monkeypatch.setattr(et, "read_tags_batch", fake_read)
    opts = Options(input=tmp_path / "input", output=tmp_path / "out")
    monkeypatch.setattr(pipeline, "EXIFTOOL_READ_BATCH_SIZE", 100)
    old_rows = process_directory(directory, opts)
    monkeypatch.setattr(pipeline, "EXIFTOOL_READ_BATCH_SIZE", 2)
    new_rows = process_directory(directory, opts)

    assert new_rows == old_rows
    assert {row["status"] for row in new_rows} == {
        Status.EXIF_JSON_MATCH_TZ_GPS.value, Status.EXIF_JSON_MATCH_TZ_INFERRED.value,
    }
    assert [row["status"] for row in new_rows] == [row["status"] for row in old_rows]
    assert [row["selected_datetime"] for row in new_rows] == [row["selected_datetime"] for row in old_rows]
    old_report = tmp_path / "old.csv"
    new_report = tmp_path / "new.csv"
    write_report(old_rows, old_report)
    write_report(new_rows, new_report)
    assert new_report.read_bytes() == old_report.read_bytes()


def test_batched_merge_keeps_media_path_mapping_independent_of_read_order(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 3)

    def fake_read(paths, exiftool_path="exiftool"):
        return {
            str(path): {"File:FileType": f"TYPE-{path.stem}"}
            for path in reversed(paths)
        }

    monkeypatch.setattr(et, "read_tags_batch", fake_read)
    monkeypatch.setattr(pipeline, "EXIFTOOL_READ_BATCH_SIZE", 1)
    rows = process_directory(directory, Options(input=tmp_path / "input", output=tmp_path / "out"))

    assert [row["file_type"] for row in rows] == [f"TYPE-{Path(row['file']).stem}" for row in rows]


def test_metadata_progress_is_emitted_for_dry_run_and_apply(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 1)
    monkeypatch.setattr(et, "read_tags_batch", _fake_tags)
    for apply in (False, True):
        observed = []
        run(
            Options(input=tmp_path / "input", output=tmp_path / f"out-{apply}", apply=apply),
            metadata_progress=lambda *args: observed.append(args),
        )
        assert observed == [(directory, 0, 1), (directory, 1, 1)]


def test_metadata_progress_starts_at_zero_and_uses_fifty_file_batches(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 120)
    monkeypatch.setattr(et, "read_tags_batch", _fake_tags)
    observed = []

    process_directory(
        directory, Options(input=tmp_path / "input", output=tmp_path / "out"),
        metadata_progress=lambda *args: observed.append(args),
    )

    assert observed == [
        (directory, 0, 120), (directory, 50, 120), (directory, 100, 120), (directory, 120, 120),
    ]


def test_metadata_progress_always_finishes_at_total_including_3662_files(tmp_path, monkeypatch):
    monkeypatch.setattr(et, "read_tags_batch", _fake_tags)

    for count in (120, 173, 3662):
        directory = _metadata_tree(tmp_path / str(count), count)
        observed = []
        process_directory(
            directory, Options(input=tmp_path / str(count) / "input", output=tmp_path / "out"),
            metadata_progress=lambda *args: observed.append(args),
        )

        assert observed[-1] == (directory, count, count)


def test_analysis_progress_starts_at_zero_and_always_finishes_at_total(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 120)
    monkeypatch.setattr(et, "read_tags_batch", _fake_tags)
    observed = []

    process_directory(
        directory, Options(input=tmp_path / "input", output=tmp_path / "out"),
        analysis_progress=lambda *args: observed.append(args),
    )

    assert observed[0] == (directory, 0, 120)
    assert observed[-1] == (directory, 120, 120)
    assert observed[1:-1] == [(directory, 50, 120), (directory, 100, 120)]


def test_cancel_during_first_pass_discards_directory_without_inference_or_rows(tmp_path, monkeypatch):
    directory = _metadata_tree(tmp_path, 3)
    event = threading.Event()
    monkeypatch.setattr(et, "read_tags_batch", _fake_tags)
    real_decide = pipeline.decide
    calls = []

    def cancel_after_first_decision(*args, **kwargs):
        event.set()
        return real_decide(*args, **kwargs)

    monkeypatch.setattr(pipeline, "decide", cancel_after_first_decision)
    monkeypatch.setattr(
        pipeline, "_infer_sibling_offset", lambda *args: calls.append("infer") or (None, 0),
    )
    monkeypatch.setattr(
        pipeline, "_redecide_with_siblings", lambda *args, **kwargs: calls.append("redecide") or {},
    )
    monkeypatch.setattr(
        pipeline, "_build_row", lambda *args: calls.append("row") or {},
    )

    rows = process_directory(
        directory, Options(input=tmp_path / "input", output=tmp_path / "out"), cancel_event=event,
    )

    assert rows == []
    assert calls == []

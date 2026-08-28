"""Progress callback tests for the pipeline wrapper."""
import threading
from pathlib import Path

from photo_date_restore.pipeline import Options, run


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

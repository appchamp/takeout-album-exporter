"""Progress callback tests for the pipeline wrapper."""
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

import pytest

import photo_date_restore.pipeline as pipeline_module
from photo_date_restore.cli import build_parser, main
from photo_date_restore.pipeline import Options, run


@pytest.mark.parametrize("timezone_name", ["Asia/Tokyo", "UTC", "Europe/London", "America/New_York"])
def test_cli_accepts_valid_iana_timezones(tmp_path, timezone_name):
    args = build_parser().parse_args([
        str(tmp_path),
        "--output", str(tmp_path / "out"),
        "--timezone", timezone_name,
    ])

    assert args.timezone == timezone_name


@pytest.mark.parametrize("timezone_name", ["Asia/Tokoyo", "Not/AZone"])
def test_invalid_timezone_is_cli_error_before_any_write(tmp_path, capsys, timezone_name):
    media = tmp_path / "photo.jpg"
    media.write_bytes(b"unchanged-media")
    before = (media.read_bytes(), media.stat().st_mtime_ns)
    output = tmp_path / "out"

    with pytest.raises(SystemExit) as exc_info:
        main([
            str(tmp_path),
            "--output", str(output),
            "--timezone", timezone_name,
            "--apply",
        ])

    assert exc_info.value.code != 0
    assert "invalid IANA timezone" in capsys.readouterr().err
    assert (media.read_bytes(), media.stat().st_mtime_ns) == before
    assert not output.exists()


def test_pipeline_rejects_invalid_timezone_before_discovery(tmp_path, monkeypatch):
    def unexpected_discovery(_root):
        raise AssertionError("invalid timezone must fail before input discovery")

    monkeypatch.setattr(pipeline_module, "discover_directories", unexpected_discovery)

    with pytest.raises(ValueError, match="invalid IANA timezone"):
        run(Options(input=tmp_path, output=tmp_path / "out", timezone="Not/AZone"))


def test_verbose_defaults_to_false_and_accepts_short_and_long_options(tmp_path):
    parser = build_parser()
    base = [str(tmp_path), "--output", str(tmp_path / "out")]

    assert parser.parse_args(base).verbose is False
    assert parser.parse_args(base + ["-v"]).verbose is True
    assert parser.parse_args(base + ["--verbose"]).verbose is True


def test_verbose_off_keeps_summary_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline_module.et, "find_exiftool", lambda _path: "exiftool")
    monkeypatch.setattr("photo_date_restore.cli.run", lambda _opts, file_progress=None: [
        {"relative_path": "a/b.jpg", "status": "EXIF_JSON_MATCH"},
    ])

    assert main([str(tmp_path), "--output", str(tmp_path / "out")]) == 0
    assert capsys.readouterr().out == "processed 1 files (dry-run)\n  EXIF_JSON_MATCH: 1\n"


def test_verbose_prints_rows_and_preserves_summary_and_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline_module.et, "find_exiftool", lambda _path: "exiftool")

    def fake_run(_opts, file_progress=None):
        row = {"relative_path": "a/b.jpg", "status": "EXIF_JSON_MATCH"}
        assert file_progress is not None
        file_progress(1, row)
        return [row]

    monkeypatch.setattr("photo_date_restore.cli.run", fake_run)

    assert main([str(tmp_path), "--output", str(tmp_path / "out"), "-v"]) == 0
    assert capsys.readouterr().out == (
        "[1] a/b.jpg — Existing date matched Google metadata\n"
        "processed 1 files (dry-run)\n"
        "  EXIF_JSON_MATCH: 1\n"
    )


def test_version_is_1_1_0(tmp_path, capsys):
    assert main([str(tmp_path), "--output", str(tmp_path / "out"), "--version"]) == 0
    assert capsys.readouterr().out == "photo-date-restore 1.1.0\n"

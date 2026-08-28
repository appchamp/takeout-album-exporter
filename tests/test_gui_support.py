"""Tkinter-free tests for GUI support helpers."""
from pathlib import Path

import pytest

from photo_date_restore import exiftool_client, pipeline
from photo_date_restore.cli import build_parser
from photo_date_restore.gui import support
from photo_date_restore.gui.support import GuiSettings, GuiValidationError
from photo_date_restore.report import format_progress_line


def test_locate_exiftool_prefers_path(monkeypatch):
    monkeypatch.setattr(support.shutil, "which", lambda _name: "/from/path/exiftool")

    assert support.locate_exiftool() == "/from/path/exiftool"


@pytest.mark.parametrize("fallback", support.EXIFTOOL_FALLBACK_PATHS)
def test_locate_exiftool_uses_macos_fallbacks(monkeypatch, fallback):
    monkeypatch.setattr(support.shutil, "which", lambda _name: None)
    monkeypatch.setattr(support.os.path, "isfile", lambda path: path == fallback)
    monkeypatch.setattr(support.os, "access", lambda path, _mode: path == fallback)

    assert support.locate_exiftool() == fallback


def test_locate_exiftool_raises_when_missing(monkeypatch):
    monkeypatch.setattr(support.shutil, "which", lambda _name: None)
    monkeypatch.setattr(support.os.path, "isfile", lambda _path: False)

    with pytest.raises(exiftool_client.ExifToolError, match="ExifTool was not found"):
        support.locate_exiftool()
    assert "brew install exiftool" in support.EXIFTOOL_MISSING_MESSAGE


def _valid_settings(tmp_path: Path) -> GuiSettings:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    return GuiSettings(input_dir=str(input_dir), output_dir=str(tmp_path / "out"))


@pytest.mark.parametrize(
    ("configure", "message"),
    [
        (lambda settings, _tmp_path: setattr(settings, "input_dir", ""), "Input folder is required."),
        (lambda settings, tmp_path: setattr(settings, "input_dir", str(tmp_path / "missing")), "Input folder does not exist"),
        (lambda settings, _tmp_path: setattr(settings, "output_dir", ""), "Output folder is required."),
    ],
)
def test_validate_settings_required_and_input_failures(tmp_path, configure, message):
    settings = _valid_settings(tmp_path)
    configure(settings, tmp_path)

    with pytest.raises(GuiValidationError, match=message):
        support.validate_settings(settings)


def test_validate_settings_rejects_output_file(tmp_path):
    settings = _valid_settings(tmp_path)
    output_file = tmp_path / "output-file"
    output_file.write_text("not a directory")
    settings.output_dir = str(output_file)

    with pytest.raises(GuiValidationError, match="Output path is not a directory"):
        support.validate_settings(settings)


def test_validate_settings_rejects_equal_and_overlapping_paths(tmp_path):
    settings = _valid_settings(tmp_path)
    input_dir = Path(settings.input_dir)

    settings.output_dir = str(input_dir)
    with pytest.raises(GuiValidationError, match="different from input"):
        support.validate_settings(settings)

    settings.output_dir = str(input_dir / "out")
    with pytest.raises(GuiValidationError, match="must not be inside input"):
        support.validate_settings(settings)

    outer = tmp_path / "outer"
    outer.mkdir()
    settings.input_dir = str(outer / "input")
    Path(settings.input_dir).mkdir()
    settings.output_dir = str(outer)
    with pytest.raises(GuiValidationError, match="Input folder must not be inside output"):
        support.validate_settings(settings)


def test_validate_settings_rejects_sources_output(tmp_path):
    settings = _valid_settings(tmp_path)
    settings.output_dir = str(pipeline.PROTECTED_SOURCES_ROOT / "gui-output")

    with pytest.raises(GuiValidationError, match="must not be inside sources"):
        support.validate_settings(settings)


def test_validate_settings_rejects_uncreatable_output_parent(tmp_path, monkeypatch):
    settings = _valid_settings(tmp_path)
    settings.output_dir = str(tmp_path / "new-parent" / "out")
    monkeypatch.setattr(support.os, "access", lambda _path, _mode: False)

    with pytest.raises(GuiValidationError, match="Output folder cannot be created"):
        support.validate_settings(settings)


def test_validate_settings_timezone_and_report_failures(tmp_path):
    settings = _valid_settings(tmp_path)
    settings.timezone = "Not/AZone"
    with pytest.raises(GuiValidationError, match="invalid IANA timezone"):
        support.validate_settings(settings)

    settings.timezone = ""
    settings.write_report = True
    with pytest.raises(GuiValidationError, match="Report path is required"):
        support.validate_settings(settings)

    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory")
    settings.report_path = str(blocked_parent / "report.csv")
    with pytest.raises(GuiValidationError, match="Report folder cannot be created"):
        support.validate_settings(settings)


def test_validate_settings_valid_unseen_output_creates_nothing(tmp_path):
    settings = _valid_settings(tmp_path)
    output = Path(settings.output_dir)

    support.validate_settings(settings)

    assert not output.exists()


def test_build_options_and_defaults_match_cli(tmp_path):
    settings = _valid_settings(tmp_path)
    settings.timezone = "Asia/Tokyo"
    opts = support.build_options(settings, "/usr/local/bin/exiftool")
    args = build_parser().parse_args([str(tmp_path), "--output", str(tmp_path / "cli-out")])

    assert opts.input == Path(settings.input_dir)
    assert opts.output == Path(settings.output_dir)
    assert opts.in_place is False
    assert opts.apply is False
    assert opts.timezone == "Asia/Tokyo"
    assert opts.exiftool_path == "/usr/local/bin/exiftool"
    assert opts.move_json is None
    assert args.apply == (not GuiSettings().dry_run)
    assert args.overwrite_output == GuiSettings().overwrite_output
    assert args.timezone == (GuiSettings().timezone or None)
    assert opts.conflict_seconds == args.conflict_seconds
    assert opts.tz_tolerance == args.tz_tolerance


def test_build_options_expands_user_paths():
    settings = GuiSettings(input_dir="~/x", output_dir="~/y")

    opts = support.build_options(settings, "/usr/local/bin/exiftool")

    assert opts.input == Path("~/x").expanduser()
    assert opts.output == Path("~/y").expanduser()


def test_summary_lines_mirror_cli_summary_shape():
    rows = [{"status": "Z"}, {"status": "A"}, {"status": "A"}]

    assert support.summary_lines(rows, apply=False) == [
        "processed 3 files (dry-run)", "  A: 2", "  Z: 1",
    ]
    assert support.summary_lines(rows, apply=True) == ["processed 3 files", "  A: 2", "  Z: 1"]


def test_gui_defaults_are_safe_and_verbose():
    assert GuiSettings().verbose is True
    assert GuiSettings().dry_run is True


def test_about_lines_match_source_metadata_and_include_project_url(monkeypatch):
    from photo_date_restore import __version__

    class Metadata:
        def get_all(self, name):
            assert name == "Project-URL"
            return ["Repository, https://github.com/kimipooh/takeout-album-exporter"]

    monkeypatch.setattr("importlib.metadata.version", lambda _name: __version__)
    monkeypatch.setattr("importlib.metadata.metadata", lambda _name: Metadata())
    lines = support.about_lines()

    license_lines = (Path(__file__).resolve().parents[1] / "LICENSE").read_text().splitlines()
    copyright_line = next(line for line in license_lines if line.startswith("Copyright (c)"))

    assert support.app_version() == __version__
    assert "Photo Date Restore" in lines
    assert f"Version {__version__}" in lines
    assert "MIT License" in lines
    assert copyright_line in lines
    assert "https://github.com/kimipooh/takeout-album-exporter" in lines


def test_format_progress_line_uses_relative_path_then_file():
    assert format_progress_line(1, {"relative_path": "a/b.jpg", "status": "OK"}) == "[1] a/b.jpg — OK"
    assert format_progress_line(2, {"file": "fallback.jpg", "status": "NO_CHANGE"}) == (
        "[2] fallback.jpg — Already up to date; no change needed"
    )


def test_app_version_falls_back_when_metadata_is_unavailable(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from photo_date_restore import __version__

    monkeypatch.setattr("importlib.metadata.version", lambda _name: (_ for _ in ()).throw(PackageNotFoundError))

    assert support.app_version() == __version__


def test_cancelled_lines():
    assert support.cancelled_lines([{}, {}]) == ["Processing cancelled.", "Processed: 2 files"]

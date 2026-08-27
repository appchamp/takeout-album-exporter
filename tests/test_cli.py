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

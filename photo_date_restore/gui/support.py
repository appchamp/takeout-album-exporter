"""Tkinter-free helpers for the photo-date-restore GUI."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .. import exiftool_client
from .. import pipeline
from .. import report
from ..pipeline import Options
from ..tz import validate_timezone_name

EXIFTOOL_FALLBACK_PATHS = ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool")

APP_DISPLAY_NAME = "Photo Date Restore"
APP_AUTHOR = "Kimiya Kitani"
APP_COPYRIGHT_YEAR = "2026"
APP_LICENSE = "MIT License"

EXIFTOOL_MISSING_MESSAGE = (
    "ExifTool was not found.\n"
    "\n"
    "This application requires ExifTool.\n"
    "\n"
    "If you use Homebrew, install it with:\n"
    "\n"
    "    brew install exiftool"
)


def locate_exiftool(explicit: Optional[str] = None) -> str:
    """Return an executable ExifTool path for a GUI-launched application."""
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit
    found = shutil.which("exiftool")
    if found:
        return found
    for path in EXIFTOOL_FALLBACK_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise exiftool_client.ExifToolError(EXIFTOOL_MISSING_MESSAGE)


@dataclass
class GuiSettings:
    input_dir: str = ""
    output_dir: str = ""
    dry_run: bool = True
    timezone: str = ""
    overwrite_output: bool = False
    write_report: bool = False
    report_path: str = ""
    report_format: str = "csv"
    verbose: bool = True


def app_version() -> str:
    """Return the installed package version, falling back to the source value."""
    try:
        from importlib.metadata import version

        return version("photo-date-restore")
    except Exception:
        from .. import __version__

        return __version__


def project_url() -> str:
    """Repository URL from package metadata. Empty when unavailable."""
    try:
        from importlib.metadata import metadata

        entries = metadata("photo-date-restore").get_all("Project-URL") or []
        by_label = {}
        for entry in entries:
            label, _, url = entry.partition(",")
            by_label[label.strip().lower()] = url.strip()
        return by_label.get("repository") or by_label.get("homepage") or ""
    except Exception:
        return ""


def about_lines() -> List[str]:
    """Tkinter-free About text used by the GUI dialog."""
    lines = [
        APP_DISPLAY_NAME,
        f"Version {app_version()}",
        "",
        f"Copyright (c) {APP_COPYRIGHT_YEAR} {APP_AUTHOR}",
        APP_LICENSE,
    ]
    url = project_url()
    if url:
        lines.extend(["", "Project:", url])
    return lines


class GuiValidationError(Exception):
    """User-correctable problem with the GUI form."""


def _resolve_user_path(value: str) -> Path:
    return Path(value).expanduser()


def _nearest_existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _require_creatable_parent(path: Path, message_prefix: str) -> None:
    ancestor = _nearest_existing_ancestor(path)
    if not ancestor.is_dir() or not os.access(ancestor, os.W_OK):
        raise GuiValidationError(f"{message_prefix}: {path}")


def validate_settings(settings: GuiSettings) -> None:
    """Validate GUI inputs without creating directories or files."""
    if not settings.input_dir.strip():
        raise GuiValidationError("Input folder is required.")
    input_path = _resolve_user_path(settings.input_dir)
    if not input_path.exists() or not input_path.is_dir():
        raise GuiValidationError(f"Input folder does not exist or is not a directory: {input_path}")

    if not settings.output_dir.strip():
        raise GuiValidationError("Output folder is required.")
    output_path = _resolve_user_path(settings.output_dir)
    if output_path.exists() and not output_path.is_dir():
        raise GuiValidationError(f"Output path is not a directory: {output_path}")

    input_resolved = input_path.resolve()
    output_resolved = output_path.resolve()
    if output_resolved == input_resolved:
        raise GuiValidationError("Output folder must be different from input folder.")
    if input_resolved in output_resolved.parents:
        raise GuiValidationError("Output folder must not be inside input folder.")
    if output_resolved in input_resolved.parents:
        raise GuiValidationError("Input folder must not be inside output folder.")

    protected_sources = pipeline.PROTECTED_SOURCES_ROOT.resolve()
    if output_resolved == protected_sources or protected_sources in output_resolved.parents:
        raise GuiValidationError("Output folder must not be inside sources/.")
    if not output_path.exists():
        _require_creatable_parent(output_path, "Output folder cannot be created")

    timezone = settings.timezone.strip()
    if timezone:
        try:
            validate_timezone_name(timezone)
        except ValueError as exc:
            raise GuiValidationError(str(exc)) from exc

    if settings.write_report:
        if not settings.report_path.strip():
            raise GuiValidationError("Report path is required when saving an audit report.")
        report_path = _resolve_user_path(settings.report_path)
        _require_creatable_parent(report_path.parent, "Report folder cannot be created")


def build_options(settings: GuiSettings, exiftool_path: str) -> Options:
    """Build copy-mode pipeline options from validated GUI settings."""
    return Options(
        input=_resolve_user_path(settings.input_dir),
        output=_resolve_user_path(settings.output_dir),
        in_place=False,
        apply=not settings.dry_run,
        timezone=settings.timezone.strip() or None,
        exiftool_path=exiftool_path,
        overwrite_output=settings.overwrite_output,
        move_json=None,
    )


def summary_lines(rows: Sequence[dict], apply: bool) -> List[str]:
    """Mirror the CLI summary block using report.summarize()."""
    counts = report.summarize(rows)
    lines = [f"processed {len(rows)} files" + ("" if apply else " (dry-run)")]
    lines.extend(f"  {status}: {count}" for status, count in sorted(counts.items()))
    return lines


def cancelled_lines(rows: Sequence[dict]) -> List[str]:
    """Summary block for a cancelled run."""
    return ["Processing cancelled.", f"Processed: {len(rows)} files"]


def open_in_finder(path: Path) -> None:
    """Open a path in Finder when running on macOS."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)

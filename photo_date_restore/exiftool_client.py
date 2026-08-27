"""Thin wrapper around the ExifTool CLI: batch read, write, and read-back verify.

Design reference: docs/design.md §9 (ExifTool 採用理由), §9.4 (read-back
verification / `_original` rollback), 要求仕様 §5, §13.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

READ_TAGS = [
    "-EXIF:DateTimeOriginal",
    "-EXIF:CreateDate",
    "-EXIF:ModifyDate",
    "-EXIF:OffsetTimeOriginal",
    "-Composite:GPSDateTime",
    "-XMP-photoshop:DateCreated",
    "-XMP-exif:DateTimeOriginal",
    "-XMP:MetadataDate",
    "-File:FileModifyDate",
    "-File:FileType",
    "-File:MIMEType",
    "-File:ImageWidth",
    "-File:ImageHeight",
    "-File:FileSize#",
]


class ExifToolError(Exception):
    pass


def find_exiftool(explicit_path: Optional[str] = None) -> str:
    path = explicit_path or shutil.which("exiftool")
    if not path:
        raise ExifToolError(
            "exiftool not found. Install it (e.g. `brew install exiftool`) or pass --exiftool PATH."
        )
    return path


def exiftool_version(exiftool_path: str) -> str:
    result = subprocess.run([exiftool_path, "-ver"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def read_tags_batch(paths: List[Path], exiftool_path: str = "exiftool") -> Dict[str, dict]:
    """Read the whitelisted tags for a batch of files. Returns SourceFile -> tags."""
    if not paths:
        return {}
    args = [exiftool_path, "-j", "-G0", "-a", "-api", "QuickTimeUTC=1", *READ_TAGS, *[str(p) for p in paths]]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):  # 1 = some files had warnings, still parseable
        raise ExifToolError(f"exiftool read failed: {result.stderr.strip()}")
    try:
        records = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ExifToolError(f"could not parse exiftool JSON output: {exc}") from exc
    return {rec["SourceFile"]: rec for rec in records}


def read_tags(path: Path, exiftool_path: str = "exiftool") -> dict:
    return read_tags_batch([path], exiftool_path=exiftool_path).get(str(path), {})


def write_tags(path: Path, tag_args: List[str], exiftool_path: str = "exiftool") -> "WriteResult":
    """Write tags to `path`, keeping ExifTool's `<file>_original` backup.

    `tag_args` are already-formatted ExifTool CLI args, e.g. ["-EXIF:DateTimeOriginal=2017:11:07 08:40:23"].
    Never re-encodes image data (ExifTool edits the container in place).
    """
    args = [exiftool_path, "-P", "-api", "QuickTimeUTC=1", *tag_args, str(path)]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return WriteResult(
        success=result.returncode == 0 and "error" not in result.stdout.lower(),
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
        original_backup=path.with_name(path.name + "_original"),
    )


def restore_original(path: Path) -> None:
    backup = path.with_name(path.name + "_original")
    if backup.exists():
        backup.replace(path)


def discard_original_backup(path: Path) -> None:
    backup = path.with_name(path.name + "_original")
    if backup.exists():
        backup.unlink()


class WriteResult:
    def __init__(self, success: bool, stdout: str, stderr: str, original_backup: Path):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.original_backup = original_backup

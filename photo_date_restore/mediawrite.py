"""write_media_datetime(): format-dispatching, non-destructive datetime writer.

Design reference: docs/design.md §9.2 (2026-08-27 追補: JPEG 専用にしない),
§9.4 (読み戻し検証必須), §18.2 (v1.0 対応範囲は JPEG/TIFF/PNG に限定).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import exiftool_client as et
from .tz import format_offset

JPEG_TIFF_TYPES = {"JPEG", "TIFF"}
PNG_TYPES = {"PNG"}
SUPPORTED_WRITE_TYPES = JPEG_TIFF_TYPES | PNG_TYPES


@dataclass
class WriteOutcome:
    attempted: bool
    success: bool = False
    verified: bool = False
    error: str = ""


def _fmt_local(dt: datetime) -> str:
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def _jpeg_tiff_args(local_naive: datetime, offset_seconds: Optional[int]) -> list:
    dt_str = _fmt_local(local_naive)
    args = [
        f"-EXIF:DateTimeOriginal={dt_str}",
        f"-EXIF:CreateDate={dt_str}",
    ]
    if offset_seconds is not None:
        off = format_offset(offset_seconds)
        args += [f"-EXIF:OffsetTimeOriginal={off}", f"-EXIF:OffsetTimeDigitized={off}"]
    return args


def _png_args(local_naive: datetime, offset_seconds: Optional[int]) -> list:
    dt_str = _fmt_local(local_naive)
    suffix = format_offset(offset_seconds) if offset_seconds is not None else ""
    return [
        f"-XMP-photoshop:DateCreated={dt_str}{suffix}",
        f"-XMP-xmp:CreateDate={dt_str}{suffix}",
    ]


def write_media_datetime(
    file_type: str,
    path: Path,
    local_naive: datetime,
    offset_seconds: Optional[int],
    exiftool_path: str = "exiftool",
) -> WriteOutcome:
    """Dispatch to the format-specific writer and read-back-verify the result.

    Never re-encodes image data. Keeps ExifTool's `_original` backup until the
    read-back verification succeeds; on failure the backup is left in place so
    the caller (applier) can restore it.
    """
    file_type = (file_type or "").upper()
    if file_type in JPEG_TIFF_TYPES:
        args = _jpeg_tiff_args(local_naive, offset_seconds)
    elif file_type in PNG_TYPES:
        args = _png_args(local_naive, offset_seconds)
    else:
        return WriteOutcome(attempted=False, error=f"unsupported file type for metadata write: {file_type}")

    before = et.read_tags(path, exiftool_path=exiftool_path)
    result = et.write_tags(path, args, exiftool_path=exiftool_path)
    if not result.success:
        return WriteOutcome(attempted=True, success=False, error=result.stderr or result.stdout)

    after = et.read_tags(path, exiftool_path=exiftool_path)
    verified = _verify(before, after, local_naive, file_type)
    return WriteOutcome(attempted=True, success=True, verified=verified, error="" if verified else "read-back verification failed")


def _verify(before: dict, after: dict, expected_local: datetime, file_type: str) -> bool:
    if not after:
        return False
    if before.get("File:FileType") and after.get("File:FileType") != before.get("File:FileType"):
        return False
    if before.get("File:ImageWidth") and after.get("File:ImageWidth") != before.get("File:ImageWidth"):
        return False
    if before.get("File:ImageHeight") and after.get("File:ImageHeight") != before.get("File:ImageHeight"):
        return False
    if not after.get("File:FileSize#", 1):
        return False

    expected_str = _fmt_local(expected_local)
    if file_type in JPEG_TIFF_TYPES:
        return after.get("EXIF:DateTimeOriginal", "").startswith(expected_str)
    if file_type in PNG_TYPES:
        got = after.get("XMP:DateCreated", "")
        return got.startswith(expected_str)
    return False

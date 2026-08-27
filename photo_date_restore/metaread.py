"""Turn raw ExifTool tag dicts into whitelisted DateCandidate values.

Design reference: docs/design.md §6.1 (whitelist), §16 (24:00:00 / zero-date
normalization).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import DateCandidate

# Priority order for the "existing capture datetime" candidate (case A).
# EXIF:ModifyDate is last-resort/low-confidence and only used if nothing else
# whitelisted is present. Everything else (XMP:MetadataDate, ICC ProfileDateTime,
# File:FileModifyDate, album date, JSON creationTime, filesystem mtime) is
# deliberately never read here (blacklist, §6.1).
PRIMARY_TAGS = (
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    # ExifTool's -G0 grouping collapses XMP-photoshop:DateCreated and
    # XMP-exif:DateTimeOriginal to "XMP:DateCreated" / "XMP:DateTimeOriginal".
    "XMP:DateCreated",
    "XMP:DateTimeOriginal",
)
FALLBACK_TAGS = ("EXIF:ModifyDate",)

_DT_RE = re.compile(
    r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?\s*(Z)?$"
)
_OFFSET_RE = re.compile(r"^([+-])(\d{2}):(\d{2})$")


def parse_exif_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse an ExifTool "YYYY:MM:DD HH:MM:SS[.ffffff][Z]" string.

    Returns a naive datetime unless the string ends in "Z" (GPSDateTime),
    in which case it is returned as aware UTC. Returns None for zero-dates
    ("0000:00:00 00:00:00") and unparseable strings (§16).
    """
    if not raw:
        return None
    m = _DT_RE.match(raw.strip())
    if not m:
        return None
    year, month, day, hour, minute, second, frac, zulu = m.groups()
    year, month, day = int(year), int(month), int(day)
    hour, minute, second = int(hour), int(minute), int(second)
    if year == 0 and month == 0 and day == 0:
        return None  # "0000:00:00 00:00:00" — treated as no date (§16)
    microsecond = int((frac or "0").ljust(6, "0")[:6])

    extra_day = False
    if hour == 24 and minute == 0 and second == 0:
        # §16: EXIF's "24:00:00" means midnight of the next day.
        hour = 0
        extra_day = True

    try:
        dt = datetime(year, month, day, hour, minute, second, microsecond)
    except ValueError:
        return None
    if extra_day:
        dt = dt + timedelta(days=1)
    if zulu:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_offset(raw: Optional[str]) -> Optional[int]:
    """Parse an ExifTool "+HH:MM" / "-HH:MM" offset string into seconds."""
    if not raw:
        return None
    m = _OFFSET_RE.match(raw.strip())
    if not m:
        return None
    sign, hh, mm = m.groups()
    seconds = int(hh) * 3600 + int(mm) * 60
    return -seconds if sign == "-" else seconds


def extract_existing_candidate(tags: dict) -> Optional[DateCandidate]:
    """Pick the highest-priority whitelisted "existing capture datetime" tag."""
    for tag in PRIMARY_TAGS:
        dt = parse_exif_datetime(tags.get(tag))
        if dt is not None:
            return DateCandidate(value=dt, source_tag=tag)
    for tag in FALLBACK_TAGS:
        dt = parse_exif_datetime(tags.get(tag))
        if dt is not None:
            return DateCandidate(value=dt, source_tag=tag)
    return None


def extract_explicit_offset_seconds(tags: dict) -> Optional[int]:
    return parse_offset(tags.get("EXIF:OffsetTimeOriginal"))


def extract_gps_datetime(tags: dict) -> Optional[datetime]:
    raw = tags.get("Composite:GPSDateTime") or tags.get("GPS:GPSDateTime")
    dt = parse_exif_datetime(raw)
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

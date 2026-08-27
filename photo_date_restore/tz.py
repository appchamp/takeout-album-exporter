"""Low-level timezone-offset arithmetic. Pure functions only.

Design reference: docs/design.md §6.3, §8.2 (2026-08-27 追補).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QUARTER_HOUR = 900  # seconds
MAX_TZ_OFFSET = 14 * 3600  # seconds; covers up to UTC+14 (Kiribati)
DEFAULT_TZ_TOLERANCE = 90  # seconds; absorbs GPS fix delay / clock drift
SIBLING_MIN_COUNT = 3  # design §8.2 tier 3: "既定 3 件以上"


def validate_timezone_name(name: str) -> str:
    """Return a valid IANA timezone name or raise ValueError."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"invalid IANA timezone: {name}") from exc
    return name


def round_to_quarter_hour(seconds: int, tolerance: int = DEFAULT_TZ_TOLERANCE) -> Optional[int]:
    """Return the nearest multiple of 900s if `seconds` is within `tolerance`
    of it and the result is within +/-14h, else None (not timezone-shaped)."""
    nearest = round(seconds / QUARTER_HOUR) * QUARTER_HOUR
    if abs(seconds - nearest) <= tolerance and abs(nearest) <= MAX_TZ_OFFSET:
        return nearest
    return None


def implied_offset_seconds(local_naive: datetime, reference_utc: datetime) -> int:
    """§6.3: treat `local_naive` as if its wall-clock digits were UTC, and
    subtract the true UTC instant `reference_utc`. The result is the offset
    that would make `local_naive` correct as a local reading of that instant.
    """
    naive_as_utc = local_naive.replace(tzinfo=timezone.utc)
    return int((naive_as_utc - reference_utc).total_seconds())


def gps_derived_offset(
    local_naive: datetime, gps_utc: datetime, tolerance: int = DEFAULT_TZ_TOLERANCE
) -> Optional[int]:
    """Offset implied by comparing a local wall-clock reading to the media's
    own GPSDateTime (UTC). Returns None if not quarter-hour-shaped."""
    raw = implied_offset_seconds(local_naive, gps_utc)
    return round_to_quarter_hour(raw, tolerance)


def format_offset(seconds: int) -> str:
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(seconds)
    hh, rem = divmod(seconds, 3600)
    mm = rem // 60
    return f"{sign}{hh:02d}:{mm:02d}"

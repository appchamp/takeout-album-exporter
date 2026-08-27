"""Shared enums and dataclasses used across photo_date_restore.

Design reference: docs/design.md §6, §8, §15 (2026-08-27 追補).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Status(str, Enum):
    """Per-file audit status. See docs/design.md §15.3."""

    NO_CHANGE = "NO_CHANGE"
    OK_EXIF = "OK_EXIF"
    EXIF_JSON_MATCH = "EXIF_JSON_MATCH"
    EXIF_JSON_MATCH_TZ_EXPLICIT = "EXIF_JSON_MATCH_TZ_EXPLICIT"
    EXIF_JSON_MATCH_TZ_GPS = "EXIF_JSON_MATCH_TZ_GPS"
    EXIF_JSON_MATCH_TZ_INFERRED = "EXIF_JSON_MATCH_TZ_INFERRED"
    EXIF_JSON_POSSIBLE_TZ = "EXIF_JSON_POSSIBLE_TZ"
    EXIF_JSON_CONFLICT = "EXIF_JSON_CONFLICT"
    JSON_TIME_USED = "JSON_TIME_USED"
    JSON_TIME_MTIME_ONLY = "JSON_TIME_MTIME_ONLY"
    NO_JSON = "NO_JSON"
    NO_DATE = "NO_DATE"
    AMBIGUOUS_JSON = "AMBIGUOUS_JSON"
    UNSUPPORTED = "UNSUPPORTED"
    VERIFY_FAILED = "VERIFY_FAILED"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


# Message / reason codes placed in the `message` report column (not `status`).
MSG_TIMEZONE_REQUIRED_FOR_METADATA = "TIMEZONE_REQUIRED_FOR_METADATA"


class TzSource(str, Enum):
    """Timezone evidence tier. See docs/design.md §8.2 (2026-08-27 追補)."""

    EXPLICIT = "EXPLICIT"
    GPS = "GPS"
    INFERRED = "INFERRED"
    CLI = "CLI"
    NONE = "NONE"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class JsonMatchTier(str, Enum):
    T1_EXACT_TITLE = "T1_EXACT_TITLE"
    T2_EXACT_NAME = "T2_EXACT_NAME"
    T3_DERIVED_VERIFIED = "T3_DERIVED_VERIFIED"
    T4_TRUNCATED_PREFIX = "T4_TRUNCATED_PREFIX"
    NONE = "NONE"


@dataclass(frozen=True)
class DateCandidate:
    """A single "existing datetime" candidate read from media metadata.

    `value` is a naive local wall-clock datetime (no tzinfo) unless
    `offset_seconds` is provided, in which case `value` still represents the
    local wall-clock reading and `offset_seconds` is the tag's own explicit
    offset (e.g. from EXIF:OffsetTimeOriginal).
    """

    value: datetime
    source_tag: str
    offset_seconds: Optional[int] = None


@dataclass(frozen=True)
class SidecarInfo:
    """Parsed Google Takeout JSON sidecar (media sidecar only, not album metadata)."""

    path: str
    title: Optional[str]
    photo_taken_time: Optional[datetime]  # aware, UTC
    creation_time: Optional[datetime]  # aware, UTC — read-only in v1.0
    is_album_metadata: bool = False


@dataclass
class TimezoneResolution:
    offset_seconds: Optional[int]
    source: TzSource
    corroborating_files: int = 0


@dataclass
class MatchResult:
    """Result of comparing an existing DateCandidate against JSON photoTakenTime."""

    status: Status
    difference_seconds: Optional[int]
    implied_offset_seconds: Optional[int]
    tz: TimezoneResolution
    confidence: Confidence


@dataclass
class Decision:
    """Final per-file decision produced by decide.py."""

    status: Status
    selected_datetime: Optional[datetime] = None  # aware, if timezone known
    selected_datetime_source: Optional[str] = None
    timezone_source: TzSource = TzSource.NONE
    timezone_offset_seconds: Optional[int] = None
    difference_seconds: Optional[int] = None
    implied_offset_seconds: Optional[int] = None
    confidence: Optional[Confidence] = None
    planned_metadata_action: str = "NONE"  # NONE|WRITE|SKIP_TIMEZONE_REQUIRED|SKIP_EXISTING
    planned_mtime_action: str = "NONE"  # NONE|SET
    mtime_datetime: Optional[datetime] = None  # aware UTC instant to set as mtime
    message: str = ""
    error: str = ""

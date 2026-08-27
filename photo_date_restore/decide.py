"""The datetime decision engine. Pure function — no file I/O.

Design reference: docs/design.md §6 (decision flow), §6.3 (match tiers),
§7 (case A/B/D), §8 (timezone ladder), 2026-08-27 追補.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .models import (
    Confidence,
    DateCandidate,
    Decision,
    MSG_TIMEZONE_REQUIRED_FOR_METADATA,
    SidecarInfo,
    Status,
    TzSource,
)
from .tz import DEFAULT_TZ_TOLERANCE, SIBLING_MIN_COUNT, implied_offset_seconds, round_to_quarter_hour

DEFAULT_CONFLICT_SECONDS = 60


def decide(
    existing: Optional[DateCandidate],
    sidecar: Optional[SidecarInfo],
    *,
    gps_utc: Optional[datetime] = None,
    explicit_offset_seconds: Optional[int] = None,
    sibling_offset_seconds: Optional[int] = None,
    sibling_count: int = 0,
    cli_offset_seconds: Optional[int] = None,
    conflict_seconds: int = DEFAULT_CONFLICT_SECONDS,
    tz_tolerance: int = DEFAULT_TZ_TOLERANCE,
) -> Decision:
    json_utc = sidecar.photo_taken_time if sidecar is not None else None

    if existing is None and json_utc is None:
        return Decision(status=Status.NO_DATE, planned_metadata_action="NONE", planned_mtime_action="NONE")

    if existing is not None:
        return _decide_case_a(
            existing,
            json_utc,
            gps_utc=gps_utc,
            explicit_offset_seconds=explicit_offset_seconds,
            sibling_offset_seconds=sibling_offset_seconds,
            sibling_count=sibling_count,
            cli_offset_seconds=cli_offset_seconds,
            conflict_seconds=conflict_seconds,
            tz_tolerance=tz_tolerance,
        )

    return _decide_case_b(
        json_utc,
        sibling_offset_seconds=sibling_offset_seconds,
        sibling_count=sibling_count,
        cli_offset_seconds=cli_offset_seconds,
    )


def _decide_case_a(
    existing: DateCandidate,
    json_utc: Optional[datetime],
    *,
    gps_utc: Optional[datetime],
    explicit_offset_seconds: Optional[int],
    sibling_offset_seconds: Optional[int],
    sibling_count: int,
    cli_offset_seconds: Optional[int],
    conflict_seconds: int,
    tz_tolerance: int,
) -> Decision:
    if json_utc is None:
        # No sidecar to verify against — trust the existing metadata as-is.
        return Decision(
            status=Status.OK_EXIF,
            selected_datetime=existing.value,
            selected_datetime_source=existing.source_tag,
            planned_metadata_action="NONE",
            planned_mtime_action="NONE",
        )

    delta = implied_offset_seconds(existing.value, json_utc)

    if abs(delta) <= conflict_seconds:
        return Decision(
            status=Status.EXIF_JSON_MATCH,
            selected_datetime=existing.value,
            selected_datetime_source=existing.source_tag,
            timezone_source=TzSource.NONE,
            difference_seconds=delta,
            confidence=Confidence.HIGH,
            planned_metadata_action="NONE",
            planned_mtime_action="SET",
            mtime_datetime=json_utc,
        )

    quarter = round_to_quarter_hour(delta, tz_tolerance)
    if quarter is None:
        return Decision(
            status=Status.EXIF_JSON_CONFLICT,
            selected_datetime=None,
            difference_seconds=delta,
            planned_metadata_action="NONE",
            planned_mtime_action="NONE",
            message="EXIF と JSON の差分が timezone として説明できない",
        )

    # Evidence-tier check, strongest first (design §8.2 追補の優先順:
    # EXPLICIT > GPS > INFERRED(siblings) > CLI > none).
    if explicit_offset_seconds is not None and round_to_quarter_hour(explicit_offset_seconds, tz_tolerance) == quarter:
        status, tz_source, confidence = Status.EXIF_JSON_MATCH_TZ_EXPLICIT, TzSource.EXPLICIT, Confidence.HIGH
    elif gps_utc is not None and round_to_quarter_hour(implied_offset_seconds(existing.value, gps_utc), tz_tolerance) == quarter:
        status, tz_source, confidence = Status.EXIF_JSON_MATCH_TZ_GPS, TzSource.GPS, Confidence.HIGH
    elif (
        sibling_offset_seconds is not None
        and sibling_count >= SIBLING_MIN_COUNT
        and round_to_quarter_hour(sibling_offset_seconds, tz_tolerance) == quarter
    ):
        status, tz_source, confidence = Status.EXIF_JSON_MATCH_TZ_INFERRED, TzSource.INFERRED, Confidence.MEDIUM
    elif cli_offset_seconds is not None and round_to_quarter_hour(cli_offset_seconds, tz_tolerance) == quarter:
        status, tz_source, confidence = Status.EXIF_JSON_MATCH_TZ_EXPLICIT, TzSource.CLI, Confidence.HIGH
    else:
        status, tz_source, confidence = Status.EXIF_JSON_POSSIBLE_TZ, TzSource.NONE, Confidence.LOW

    return Decision(
        status=status,
        selected_datetime=existing.value,
        selected_datetime_source=existing.source_tag,
        timezone_source=tz_source,
        timezone_offset_seconds=quarter if tz_source != TzSource.NONE else None,
        difference_seconds=delta,
        implied_offset_seconds=quarter,
        confidence=confidence,
        planned_metadata_action="NONE",  # case A never overwrites existing EXIF
        planned_mtime_action="SET",
        mtime_datetime=json_utc,
    )


def _decide_case_b(
    json_utc: Optional[datetime],
    *,
    sibling_offset_seconds: Optional[int],
    sibling_count: int,
    cli_offset_seconds: Optional[int],
) -> Decision:
    if json_utc is None:
        return Decision(status=Status.NO_DATE, planned_metadata_action="NONE", planned_mtime_action="NONE")

    offset: Optional[int] = None
    tz_source = TzSource.NONE
    if sibling_offset_seconds is not None and sibling_count >= SIBLING_MIN_COUNT:
        offset, tz_source = sibling_offset_seconds, TzSource.INFERRED
    elif cli_offset_seconds is not None:
        offset, tz_source = cli_offset_seconds, TzSource.CLI

    if offset is None:
        return Decision(
            status=Status.JSON_TIME_MTIME_ONLY,
            timezone_source=TzSource.NONE,
            planned_metadata_action="SKIP_TIMEZONE_REQUIRED",
            planned_mtime_action="SET",
            mtime_datetime=json_utc,
            message=MSG_TIMEZONE_REQUIRED_FOR_METADATA,
        )

    # Represent as a naive local wall-clock value plus its offset for writing.
    local_naive = (json_utc + timedelta(seconds=offset)).replace(tzinfo=None)
    return Decision(
        status=Status.JSON_TIME_USED,
        selected_datetime=local_naive,
        selected_datetime_source="PHOTO_TAKEN_TIME",
        timezone_source=tz_source,
        timezone_offset_seconds=offset,
        confidence=Confidence.HIGH if tz_source == TzSource.INFERRED else Confidence.MEDIUM,
        planned_metadata_action="WRITE",
        planned_mtime_action="SET",
        mtime_datetime=json_utc,
    )

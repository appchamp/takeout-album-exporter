"""Filesystem mtime handling.

Design reference: docs/design.md §10. ctime is never touched (not settable
from Python anyway). birth time is left to the APFS "mtime lowered => btime
follows" side effect; no direct birth-time API is used in v1.0.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

MTIME_TOLERANCE_SECONDS = 1.0


def get_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def mtime_matches(path: Path, target_utc: datetime, tolerance: float = MTIME_TOLERANCE_SECONDS) -> bool:
    return abs(path.stat().st_mtime - target_utc.timestamp()) < tolerance


def set_mtime(path: Path, target_utc: datetime) -> None:
    ts = target_utc.timestamp()
    os.utime(path, (ts, ts))

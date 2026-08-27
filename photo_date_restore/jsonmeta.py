"""Parse and classify Google Takeout JSON sidecar files.

Design reference: docs/design.md §4, §5.1, §16.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import SidecarInfo

_ENCODINGS = ("utf-8", "utf-8-sig", "cp932")

_MIN_TS = 0  # 1970-01-01
_MAX_FUTURE_SLACK_SECONDS = 24 * 3600  # now + 1 day


class JsonParseError(Exception):
    pass


def _read_json_text(path: Path) -> dict:
    raw = path.read_bytes()
    last_err: Optional[Exception] = None
    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
            return json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_err = exc
            continue
    raise JsonParseError(f"could not decode/parse {path}: {last_err}")


def _extract_timestamp(obj: dict, key: str) -> Optional[datetime]:
    """Extract an aware UTC datetime from a Takeout {timestamp, formatted} block.

    Returns None if the key is absent, malformed, or out of a sane range
    (GPTH #436: negative/zero/absurd-future timestamps).
    """
    block = obj.get(key)
    if not isinstance(block, dict):
        return None
    ts_raw = block.get("timestamp")
    if ts_raw is None:
        return None
    try:
        ts = int(ts_raw)
    except (TypeError, ValueError):
        return None
    now = datetime.now(timezone.utc).timestamp()
    if ts <= _MIN_TS or ts > now + _MAX_FUTURE_SLACK_SECONDS:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def load_sidecar(path: Path) -> SidecarInfo:
    """Load and classify one *.json file next to a media file (or album metadata).

    Never raises for "not a sidecar" — that is expressed via is_album_metadata.
    Raises JsonParseError only for unreadable/corrupt JSON.
    """
    data = _read_json_text(path)
    if not isinstance(data, dict):
        raise JsonParseError(f"{path}: top-level JSON is not an object")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        title = None

    photo_taken_time = _extract_timestamp(data, "photoTakenTime")
    creation_time = _extract_timestamp(data, "creationTime")

    is_sidecar = title is not None and (photo_taken_time is not None or creation_time is not None)

    return SidecarInfo(
        path=str(path),
        title=title,
        photo_taken_time=photo_taken_time,
        creation_time=creation_time,
        is_album_metadata=not is_sidecar,
    )

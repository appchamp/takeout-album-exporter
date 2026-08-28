"""Top-level orchestration: walk INPUT, decide, and (optionally) apply changes.

Design reference: docs/design.md §6.2 (flow), §11 (copy mode), §12 (in-place),
§14 (dry-run), §17 (idempotency).
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import exiftool_client as et
from . import fsdates
from . import jsonmeta
from . import metaread
from .decide import decide
from .mediawrite import SUPPORTED_WRITE_TYPES, write_media_datetime
from .models import Decision, JsonMatchTier, SidecarInfo, Status, TzSource
from .sidecar import make_candidate, match_all
from .tz import validate_timezone_name

IGNORED_NAMES = {".DS_Store"}
IGNORED_PREFIXES = ("._",)
MEDIA_EXTENSIONS_ALL = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".webp", ".dng",
    ".heic", ".heif", ".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".mpg", ".mts",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".mpg", ".mts"}
SIDECAR_INDEX_NAME = "_sidecar_index.csv"
SIDECAR_INDEX_COLUMNS = (
    "media_relative_path",
    "original_sidecar_relative_path",
    "moved_sidecar_relative_path",
    "status",
)
PROTECTED_SOURCES_ROOT = Path(__file__).resolve().parents[1] / "sources"


@dataclass
class Options:
    input: Path
    output: Optional[Path] = None
    in_place: bool = False
    apply: bool = False
    timezone: Optional[str] = None  # IANA name, e.g. "Asia/Tokyo"
    exiftool_path: str = "exiftool"
    overwrite_output: bool = False
    conflict_seconds: int = 60
    tz_tolerance: int = 90
    move_json: Optional[Path] = None


def _is_ignored(name: str) -> bool:
    if name in IGNORED_NAMES:
        return True
    return any(name.startswith(p) for p in IGNORED_PREFIXES)


def _cli_offset_seconds(tz_name: Optional[str], instant_utc: Optional[datetime]) -> Optional[int]:
    if not tz_name or instant_utc is None:
        return None
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(tz_name)
    local = instant_utc.astimezone(zone)
    return int(local.utcoffset().total_seconds())


def discover_directories(root: Path) -> List[Path]:
    dirs = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if any(not _is_ignored(f) for f in filenames):
            dirs.append(Path(dirpath))
    return sorted(dirs)


ProgressCallback = Callable[[int, int, Path], None]
FileProgressCallback = Callable[[int, dict], None]
DirectoryStartCallback = Callable[[int, int, Path], None]


def run(opts: Options, progress: Optional[ProgressCallback] = None,
        file_progress: Optional[FileProgressCallback] = None,
        directory_start: Optional[DirectoryStartCallback] = None,
        cancel_event=None) -> List[dict]:
    """Process INPUT and return one audit row per discovered media file.

    ``progress``, when given, is notified after each directory is processed
    with ``(completed_count, total_count, directory)``. It cannot affect
    processing: exceptions raised by the callback are suppressed.

    ``file_progress``, when given, is notified as ``(index, row)`` whenever a
    file row is finalized. ``index`` is a one-based sequential count. It
    cannot affect processing: exceptions raised by the callback are suppressed.

    ``cancel_event``, when set, stops processing at a safe file or directory
    boundary and returns the rows finalized so far without raising an exception.
    """
    _validate_options(opts)
    rows: List[dict] = []
    directories = discover_directories(opts.input)
    total = len(directories)
    file_index = 0

    def _on_row(row: dict) -> None:
        nonlocal file_index
        file_index += 1
        _notify_file_progress(file_progress, file_index, row)

    for index, directory in enumerate(directories, start=1):
        if cancel_event is not None and cancel_event.is_set():
            break
        _notify_directory_start(directory_start, index, total, directory)
        kwargs = {}
        if file_progress is not None:
            kwargs["on_row"] = _on_row
        if cancel_event is not None:
            kwargs["cancel_event"] = cancel_event
        rows.extend(process_directory(directory, opts, **kwargs))
        _notify_progress(progress, index, total, directory)
    return rows


def _notify_progress(progress, done: int, total: int, directory: Path) -> None:
    if progress is None:
        return
    try:
        progress(done, total, directory)
    except Exception:
        pass


def _notify_file_progress(file_progress, index: int, row: dict) -> None:
    if file_progress is None:
        return
    try:
        file_progress(index, row)
    except Exception:
        pass


def _notify_directory_start(directory_start, index: int, total: int, directory: Path) -> None:
    if directory_start is None:
        return
    try:
        directory_start(index, total, directory)
    except Exception:
        pass


def _validate_options(opts: Options) -> None:
    if opts.timezone is not None:
        validate_timezone_name(opts.timezone)
    if opts.move_json is None:
        return
    if not opts.in_place:
        raise ValueError("--move-json requires --in-place")
    input_path = opts.input.resolve()
    destination = opts.move_json.resolve()
    if destination == input_path or input_path in destination.parents:
        raise ValueError("--move-json destination must be outside INPUT")
    protected_sources = PROTECTED_SOURCES_ROOT.resolve()
    if destination == protected_sources or protected_sources in destination.parents:
        raise ValueError("--move-json destination must be outside sources/")
    if opts.move_json.exists() and not opts.move_json.is_dir():
        raise ValueError("--move-json destination must be a directory")


def process_directory(dir_path: Path, opts: Options, on_row=None, cancel_event=None) -> List[dict]:
    entries = [e for e in os.scandir(dir_path) if e.is_file() and not _is_ignored(e.name)]
    json_entries = [e for e in entries if e.name.lower().endswith(".json")]
    media_entries = [e for e in entries if Path(e.name).suffix.lower() in MEDIA_EXTENSIONS_ALL]
    if not media_entries:
        return []

    sidecars: Dict[str, SidecarInfo] = {}
    candidates = []
    corrupt_json = []
    for je in json_entries:
        try:
            info = jsonmeta.load_sidecar(Path(je.path))
        except jsonmeta.JsonParseError as exc:
            corrupt_json.append((je.name, str(exc)))
            continue
        if info.is_album_metadata:
            candidate = make_candidate(je.name, je.name, info.title)
            if Path(candidate.stem).suffix.lower() in MEDIA_EXTENSIONS_ALL:
                corrupt_json.append((
                    je.name,
                    f"{je.path}: media sidecar has no usable photoTakenTime or creationTime",
                ))
            continue
        sidecars[je.name] = info
        candidates.append(make_candidate(je.name, je.name, info.title))

    media_names = [e.name for e in media_entries]
    match_results = match_all(media_names, candidates)
    corrupt_by_media = {name: [] for name in media_names}
    for json_name, error in corrupt_json:
        candidate = make_candidate(json_name, json_name, None)
        corrupt_matches = match_all(media_names, [candidate])
        for media_name, outcome in corrupt_matches.items():
            if outcome.tier != JsonMatchTier.NONE:
                corrupt_by_media[media_name].append((json_name, error))

    tags_by_path = et.read_tags_batch([Path(e.path) for e in media_entries], exiftool_path=opts.exiftool_path)

    ctx_by_name: Dict[str, dict] = {}
    for e in media_entries:
        path = Path(e.path)
        tags = tags_by_path.get(str(path), {})
        outcome = match_results[e.name]
        sidecar = sidecars.get(outcome.sidecar_ref) if outcome.sidecar_ref else None
        ctx_by_name[e.name] = dict(
            path=path,
            tags=tags,
            outcome=outcome,
            sidecar=sidecar,
            existing=metaread.extract_existing_candidate(tags),
            gps_utc=metaread.extract_gps_datetime(tags),
            explicit_offset=metaread.extract_explicit_offset_seconds(tags),
            cli_offset=_cli_offset_seconds(opts.timezone, sidecar.photo_taken_time if sidecar else None),
            sidecar_errors=corrupt_by_media[e.name],
        )

    pass1 = _decide_all(ctx_by_name, opts)
    sibling_offset, sibling_count = _infer_sibling_offset(pass1)
    final = _redecide_with_siblings(ctx_by_name, pass1, sibling_offset, sibling_count, opts)

    rows = []
    for name, ctx in ctx_by_name.items():
        if cancel_event is not None and cancel_event.is_set():
            break
        row = _build_row(dir_path, opts, ctx, final.get(name))
        rows.append(row)
        if on_row is not None:
            on_row(row)
    return rows


def _decide_all(ctx_by_name: Dict[str, dict], opts: Options) -> Dict[str, Optional[Decision]]:
    """Pass 1: decide using only each file's own EXPLICIT/GPS evidence.

    `--timezone` (CLI) is deliberately withheld here so it can never pre-empt
    a same-directory sibling INFERRED match that isn't known yet at this
    point (design §8.2 追補 priority: EXPLICIT > GPS > INFERRED > CLI).
    """
    result: Dict[str, Optional[Decision]] = {}
    for name, ctx in ctx_by_name.items():
        outcome = ctx["outcome"]
        if ctx["sidecar_errors"]:
            result[name] = None
            continue
        if outcome.tier == JsonMatchTier.NONE:
            result[name] = None
            continue
        if outcome.sidecar_ref is None:
            result[name] = None  # AMBIGUOUS_JSON, handled in _build_row
            continue
        result[name] = decide(
            ctx["existing"], ctx["sidecar"],
            gps_utc=ctx["gps_utc"], explicit_offset_seconds=ctx["explicit_offset"],
            cli_offset_seconds=None,
            conflict_seconds=opts.conflict_seconds, tz_tolerance=opts.tz_tolerance,
        )
    return result


def _infer_sibling_offset(pass1: Dict[str, Optional[Decision]]):
    from .tz import SIBLING_MIN_COUNT

    confirmed = [
        d.timezone_offset_seconds
        for d in pass1.values()
        if d is not None
        and d.timezone_source in (TzSource.EXPLICIT, TzSource.GPS)
        and d.timezone_offset_seconds is not None
    ]
    if confirmed and len(set(confirmed)) == 1 and len(confirmed) >= SIBLING_MIN_COUNT:
        return confirmed[0], len(confirmed)
    return None, 0


def _redecide_with_siblings(ctx_by_name, pass1, sibling_offset, sibling_count, opts) -> Dict[str, Optional[Decision]]:
    """Pass 2: re-decide anything pass 1 couldn't resolve with strong evidence,
    now offering both the inferred sibling offset (if any) and `--timezone`.
    decide()'s own tier ordering (INFERRED before CLI) still applies."""
    final = dict(pass1)
    for name, d in pass1.items():
        if d is not None and d.status in (Status.EXIF_JSON_POSSIBLE_TZ, Status.JSON_TIME_MTIME_ONLY):
            ctx = ctx_by_name[name]
            final[name] = decide(
                ctx["existing"], ctx["sidecar"],
                gps_utc=ctx["gps_utc"], explicit_offset_seconds=ctx["explicit_offset"],
                sibling_offset_seconds=sibling_offset, sibling_count=sibling_count,
                cli_offset_seconds=ctx["cli_offset"],
                conflict_seconds=opts.conflict_seconds, tz_tolerance=opts.tz_tolerance,
            )
    return final


def _build_row(dir_path: Path, opts: Options, ctx: dict, decision: Optional[Decision]) -> dict:
    path: Path = ctx["path"]
    rel = path.relative_to(opts.input)
    tags = ctx["tags"]
    file_type = tags.get("File:FileType") or path.suffix.lstrip(".").upper()
    media_type = "video" if path.suffix.lower() in VIDEO_EXTENSIONS else "image"
    outcome = ctx["outcome"]
    sidecar: Optional[SidecarInfo] = ctx["sidecar"]

    row = dict(
        file=str(path),
        relative_path=str(rel),
        album_name=dir_path.name,
        media_type=media_type,
        file_type=file_type,
        json_sidecar=outcome.sidecar_ref or "",
        json_match_tier=outcome.tier.value,
        json_candidates=outcome.candidate_count,
        existing_datetime=ctx["existing"].value.isoformat() if ctx["existing"] else "",
        existing_datetime_source=ctx["existing"].source_tag if ctx["existing"] else "",
        exif_offset=ctx["explicit_offset"] if ctx["explicit_offset"] is not None else "",
        gps_datetime=ctx["gps_utc"].isoformat() if ctx["gps_utc"] else "",
        json_photo_taken_time=sidecar.photo_taken_time.isoformat() if sidecar and sidecar.photo_taken_time else "",
        json_creation_time=sidecar.creation_time.isoformat() if sidecar and sidecar.creation_time else "",
        difference_seconds="",
        implied_offset_seconds="",
        selected_datetime="",
        selected_datetime_source="",
        timezone_source="",
        timezone_offset="",
        confidence="",
        planned_metadata_action="NONE",
        planned_mtime_action="NONE",
        status="",
        old_mtime=fsdates.get_mtime(path).isoformat(),
        new_mtime="",
        error="",
        message="",
        planned_json_action="NONE",
        planned_json_destination="",
    )

    if ctx["sidecar_errors"]:
        row["json_sidecar"] = ";".join(name for name, _error in ctx["sidecar_errors"])
        row["json_candidates"] = outcome.candidate_count + len(ctx["sidecar_errors"])
        row["status"] = Status.ERROR.value
        row["new_mtime"] = row["old_mtime"]
        row["error"] = "; ".join(
            f"SIDECAR_PARSE_ERROR({name}): {error}" for name, error in ctx["sidecar_errors"]
        )
        row["message"] = "SIDECAR_PARSE_ERROR"
        _handle_json_move(row, sidecar, opts)
        return row

    if outcome.tier == JsonMatchTier.NONE:
        row["status"] = Status.NO_JSON.value
        _finalize_no_action(row, path, opts)
        _handle_json_move(row, sidecar, opts)
        return row
    if outcome.sidecar_ref is None:
        row["status"] = Status.AMBIGUOUS_JSON.value
        row["message"] = f"{outcome.candidate_count} 件の JSON 候補が同点でした"
        _finalize_no_action(row, path, opts)
        _handle_json_move(row, sidecar, opts)
        return row

    assert decision is not None
    row["difference_seconds"] = decision.difference_seconds if decision.difference_seconds is not None else ""
    row["implied_offset_seconds"] = decision.implied_offset_seconds if decision.implied_offset_seconds is not None else ""
    row["selected_datetime"] = decision.selected_datetime.isoformat() if decision.selected_datetime else ""
    row["selected_datetime_source"] = decision.selected_datetime_source or ""
    row["timezone_source"] = decision.timezone_source.value
    row["timezone_offset"] = (
        _format_offset(decision.timezone_offset_seconds) if decision.timezone_offset_seconds is not None else ""
    )
    row["confidence"] = decision.confidence.value if decision.confidence else ""
    row["planned_metadata_action"] = decision.planned_metadata_action
    row["planned_mtime_action"] = decision.planned_mtime_action
    row["status"] = decision.status.value
    row["message"] = decision.message

    if decision.status in (Status.NO_DATE, Status.EXIF_JSON_CONFLICT):
        _finalize_no_action(row, path, opts)
        _handle_json_move(row, sidecar, opts)
        return row

    if file_type.upper() not in SUPPORTED_WRITE_TYPES and decision.planned_metadata_action == "WRITE":
        row["planned_metadata_action"] = "SKIP_TIMEZONE_REQUIRED"  # reuse: skip, format unsupported
        row["message"] = (row["message"] + "; " if row["message"] else "") + f"UNSUPPORTED_FORMAT_FOR_METADATA({file_type})"

    _apply(row, path, decision, file_type, opts)
    _handle_json_move(row, sidecar, opts)
    return row


_JSON_MOVE_SUCCESS_STATUSES = {
    Status.NO_CHANGE.value,
    Status.OK_EXIF.value,
    Status.EXIF_JSON_MATCH.value,
    Status.EXIF_JSON_MATCH_TZ_EXPLICIT.value,
    Status.EXIF_JSON_MATCH_TZ_GPS.value,
    Status.EXIF_JSON_MATCH_TZ_INFERRED.value,
    Status.JSON_TIME_USED.value,
}


def _handle_json_move(row: dict, sidecar: Optional[SidecarInfo], opts: Options) -> None:
    """Plan or perform one verified sidecar move after media processing succeeds."""
    if opts.move_json is None:
        return
    if sidecar is None or row["status"] not in _JSON_MOVE_SUCCESS_STATUSES:
        row["planned_json_action"] = "SKIP_STATUS"
        return

    source = Path(sidecar.path)
    try:
        relative = source.resolve().relative_to(opts.input.resolve())
    except ValueError:
        row["planned_json_action"] = "ERROR"
        row["error"] = "sidecar is outside INPUT"
        return

    destination = opts.move_json / relative
    row["planned_json_destination"] = str(destination)
    if not opts.apply:
        row["planned_json_action"] = "MOVE"
        return
    if destination.exists():
        row["planned_json_action"] = "SKIP_DESTINATION_EXISTS"
        row["message"] = _append_message(row["message"], "JSON_DESTINATION_EXISTS")
        return

    index_entry = {
        "media_relative_path": Path(row["relative_path"]).as_posix(),
        "original_sidecar_relative_path": relative.as_posix(),
        "moved_sidecar_relative_path": destination.relative_to(opts.move_json).as_posix(),
        "status": "MOVED",
    }
    try:
        already_indexed = _sidecar_index_contains(opts.move_json, index_entry)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _move_without_overwrite(source, destination)
    except FileExistsError:
        row["planned_json_action"] = "SKIP_DESTINATION_EXISTS"
        row["message"] = _append_message(row["message"], "JSON_DESTINATION_EXISTS")
    except (OSError, csv.Error, ValueError) as exc:
        row["planned_json_action"] = "ERROR"
        row["error"] = _append_message(row["error"], f"JSON_MOVE_FAILED: {exc}")
        row["status"] = Status.ERROR.value
    else:
        if not already_indexed:
            try:
                _append_sidecar_index(opts.move_json, index_entry)
            except (OSError, csv.Error, ValueError) as exc:
                try:
                    _move_without_overwrite(destination, source)
                except OSError as rollback_exc:
                    row["error"] = _append_message(
                        row["error"], f"JSON_INDEX_FAILED: {exc}; JSON_ROLLBACK_FAILED: {rollback_exc}"
                    )
                else:
                    row["error"] = _append_message(row["error"], f"JSON_INDEX_FAILED: {exc}")
                row["planned_json_action"] = "ERROR"
                row["status"] = Status.ERROR.value
                return
        row["planned_json_action"] = "MOVED"


def _sidecar_index_contains(index_root: Path, entry: dict) -> bool:
    index_path = index_root / SIDECAR_INDEX_NAME
    if not index_path.exists() or index_path.stat().st_size == 0:
        return False
    with index_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = [name for name in SIDECAR_INDEX_COLUMNS if name not in fieldnames]
        if missing:
            raise ValueError(f"incompatible sidecar index; missing columns: {', '.join(missing)}")
        key = _sidecar_index_key(entry)
        return any(_sidecar_index_key(existing) == key for existing in reader)


def _append_sidecar_index(index_root: Path, entry: dict) -> None:
    """Append one successful move without replacing existing index information."""
    index_path = index_root / SIDECAR_INDEX_NAME
    has_content = index_path.exists() and index_path.stat().st_size > 0
    if has_content:
        with index_path.open("r", newline="", encoding="utf-8-sig") as f:
            fieldnames = csv.DictReader(f).fieldnames or []
    else:
        fieldnames = list(SIDECAR_INDEX_COLUMNS)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    if not has_content:
        writer.writeheader()
    writer.writerow({name: entry.get(name, "") for name in fieldnames})

    existing = index_path.read_bytes() if has_content else b""
    separator = b"\n" if existing and not existing.endswith((b"\n", b"\r")) else b""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=index_root, prefix=".sidecar-index-", delete=False) as f:
            temp_path = Path(f.name)
            f.write(existing)
            f.write(separator)
            f.write(buffer.getvalue().encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, index_path)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def _sidecar_index_key(row: dict) -> tuple:
    return tuple(row.get(name, "") for name in SIDECAR_INDEX_COLUMNS[:3])


def _move_without_overwrite(source: Path, destination: Path) -> None:
    """Copy exclusively, verify bytes, then unlink the source sidecar."""
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, source.stat().st_mode & 0o777)
    created = True
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        if source.stat().st_size != destination.stat().st_size or _file_bytes(source) != _file_bytes(destination):
            raise OSError("sidecar verification failed")
        shutil.copystat(source, destination, follow_symlinks=False)
        source.unlink()
    except Exception:
        if created and destination.exists():
            destination.unlink()
        raise


def _file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _append_message(current: str, addition: str) -> str:
    return f"{current}; {addition}" if current else addition


def _format_offset(seconds: int) -> str:
    from .tz import format_offset

    return format_offset(seconds)


def _finalize_no_action(row: dict, path: Path, opts: Options) -> None:
    row["new_mtime"] = row["old_mtime"]
    if opts.output is not None:
        dest = _dest_path(row, opts)
        if opts.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or opts.overwrite_output:
                shutil.copyfile(path, dest)


def _dest_path(row: dict, opts: Options) -> Path:
    return opts.output / row["relative_path"]


def _target_path(row: dict, opts: Options) -> Path:
    if opts.in_place:
        return Path(row["file"])
    return _dest_path(row, opts)


def _already_correct(target: Path, decision: Decision, file_type: str) -> bool:
    if not target.exists():
        return False
    mtime_ok = True
    if decision.planned_mtime_action == "SET" and decision.mtime_datetime is not None:
        mtime_ok = fsdates.mtime_matches(target, decision.mtime_datetime)
    metadata_ok = True
    if decision.planned_metadata_action == "WRITE" and decision.selected_datetime is not None:
        tags = et.read_tags(target)
        expected = decision.selected_datetime.strftime("%Y:%m:%d %H:%M:%S")
        ft = file_type.upper()
        if ft in ("JPEG", "TIFF"):
            metadata_ok = tags.get("EXIF:DateTimeOriginal", "").startswith(expected)
        elif ft == "PNG":
            metadata_ok = tags.get("XMP:DateCreated", "").startswith(expected)
    return mtime_ok and metadata_ok


def _apply(row: dict, source_path: Path, decision: Decision, file_type: str, opts: Options) -> None:
    target = _target_path(row, opts)

    if opts.output is not None and not opts.in_place:
        if target.exists() and not opts.overwrite_output:
            if _already_correct(target, decision, file_type):
                row["status"] = Status.NO_CHANGE.value
                row["new_mtime"] = fsdates.get_mtime(target).isoformat()
                return
            row["status"] = Status.OUTPUT_EXISTS.value
            return
        if opts.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
        elif not target.exists():
            # dry-run: nothing on disk yet, nothing more to check.
            row["new_mtime"] = (
                decision.mtime_datetime.isoformat() if decision.mtime_datetime else row["old_mtime"]
            )
            return

    if opts.in_place and _already_correct(target, decision, file_type):
        row["status"] = Status.NO_CHANGE.value
        row["new_mtime"] = fsdates.get_mtime(target).isoformat()
        return

    if not opts.apply:
        row["new_mtime"] = (
            decision.mtime_datetime.isoformat() if decision.mtime_datetime else row["old_mtime"]
        )
        return

    if decision.planned_metadata_action == "WRITE" and decision.selected_datetime is not None:
        outcome = write_media_datetime(
            file_type, target, decision.selected_datetime, decision.timezone_offset_seconds,
            exiftool_path=opts.exiftool_path,
        )
        if not outcome.success or not outcome.verified:
            et.restore_original(target)
            row["status"] = Status.VERIFY_FAILED.value
            row["error"] = outcome.error
            return
        et.discard_original_backup(target)

    if decision.planned_mtime_action == "SET" and decision.mtime_datetime is not None:
        fsdates.set_mtime(target, decision.mtime_datetime)
        row["new_mtime"] = decision.mtime_datetime.isoformat()
    else:
        row["new_mtime"] = row["old_mtime"]

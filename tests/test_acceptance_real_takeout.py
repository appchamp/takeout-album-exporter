"""Acceptance tests against the real sources/Takeout tree (read-only input).

`sources/Takeout` is NEVER opened for writing here. Every test uses
`--output <tmp>` (copy mode only) or `--in-place` on a throwaway copy made in
a separate test module. This module's job is specifically to prove that
running the tool with `sources/Takeout` as INPUT leaves it byte-for-byte
unchanged, per docs/design.md §21.4 / §22.
"""
import hashlib
from pathlib import Path

from photo_date_restore.models import Status
from photo_date_restore.pipeline import Options, run

from conftest import SOURCES_TAKEOUT, requires_exiftool, requires_real_samples


def _snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, _sha256(p))
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@requires_exiftool
@requires_real_samples
def test_dry_run_against_real_sources_leaves_them_untouched(tmp_path):
    before = _snapshot(SOURCES_TAKEOUT)
    out = tmp_path / "should-not-be-created-by-dry-run"
    rows = run(Options(input=SOURCES_TAKEOUT, output=out, apply=False))
    after = _snapshot(SOURCES_TAKEOUT)
    assert before == after
    assert not out.exists()
    assert len(rows) == 22


@requires_exiftool
@requires_real_samples
def test_copy_apply_against_real_sources_leaves_them_untouched(tmp_path):
    before = _snapshot(SOURCES_TAKEOUT)
    out = tmp_path / "out"
    rows = run(Options(input=SOURCES_TAKEOUT, output=out, apply=True, timezone="Asia/Tokyo"))
    after = _snapshot(SOURCES_TAKEOUT)

    assert before == after, "sources/Takeout must be byte-for-byte unchanged after --output --apply"
    assert len(rows) == 22
    assert sum(1 for r in rows if r["status"] == Status.AMBIGUOUS_JSON.value) == 0
    assert sum(1 for r in rows if r["status"] == Status.EXIF_JSON_CONFLICT.value) == 0
    assert sum(1 for r in rows if r["status"] == Status.NO_DATE.value) == 0
    assert sum(1 for r in rows if r["status"] == Status.ERROR.value) == 0

    out_media = [p for p in out.rglob("*") if p.is_file()]
    assert len(out_media) == 22
    assert all(not p.name.endswith(".json") for p in out_media)


@requires_exiftool
@requires_real_samples
def test_second_apply_run_against_real_sources_is_idempotent(tmp_path):
    before = _snapshot(SOURCES_TAKEOUT)
    out = tmp_path / "out"
    run(Options(input=SOURCES_TAKEOUT, output=out, apply=True, timezone="Asia/Tokyo"))
    hashes_1 = {p: _sha256(p) for p in out.rglob("*") if p.is_file()}

    rows2 = run(Options(input=SOURCES_TAKEOUT, output=out, apply=True, timezone="Asia/Tokyo"))
    assert {r["status"] for r in rows2} == {Status.NO_CHANGE.value}

    hashes_2 = {p: _sha256(p) for p in out.rglob("*") if p.is_file()}
    assert hashes_1 == hashes_2
    assert _snapshot(SOURCES_TAKEOUT) == before

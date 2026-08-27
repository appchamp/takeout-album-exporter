"""argparse entry point. Design reference: docs/design.md §19."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import exiftool_client as et
from .models import Status
from .pipeline import Options, run
from .report import summarize, write_report
from .tz import validate_timezone_name

CONFLICT_STATUSES = {Status.AMBIGUOUS_JSON.value, Status.EXIF_JSON_CONFLICT.value}
ERROR_STATUSES = {Status.ERROR.value, Status.VERIFY_FAILED.value}


def _timezone_arg(value: str) -> str:
    try:
        return validate_timezone_name(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="photo-date-restore", description=__doc__)
    p.add_argument("input", type=Path, help="解析対象フォルダ（再帰）")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("-o", "--output", type=Path, help="別フォルダへ出力（推奨）")
    mode.add_argument("--in-place", action="store_true", help="その場で上書き（明示指定必須）")

    p.add_argument("--apply", action="store_true", help="実際に書き込む（既定は dry-run）")
    p.add_argument("--dry-run", action="store_true", help="解析のみ（既定。後方互換のため受け付ける）")
    p.add_argument("-y", "--yes", action="store_true", help="in-place の確認プロンプトを省略")

    p.add_argument("--timezone", type=_timezone_arg, default=None, help="IANA タイムゾーン名（例 Asia/Tokyo）")

    p.add_argument("--report", type=Path, default=None, help="監査レポート出力先（.csv / .jsonl）")
    p.add_argument("--report-format", choices=["csv", "jsonl"], default=None)
    p.add_argument("--csv-no-bom", action="store_true")

    p.add_argument("--overwrite-output", action="store_true")
    p.add_argument(
        "--move-json",
        type=Path,
        default=None,
        metavar="DIR",
        help="成功したsidecarを相対パスを保って退避（--in-place専用、実移動は--apply時のみ）",
    )
    p.add_argument("--conflict-seconds", type=int, default=60)
    p.add_argument("--tz-tolerance", type=int, default=90)
    p.add_argument("--exiftool", dest="exiftool_path", type=str, default=None)
    p.add_argument("--version", action="store_true")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__

        print(f"photo-date-restore {__version__}")
        return 0

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 3

    if args.move_json is not None and not args.in_place:
        parser.error("--move-json requires --in-place")

    if args.in_place and not args.yes and args.apply and sys.stdin.isatty():
        answer = input(f"--in-place --apply で {args.input} を書き換えます。よろしいですか？ [y/N]: ")
        if answer.strip().lower() not in ("y", "yes"):
            print("中止しました。")
            return 3

    try:
        exiftool_path = et.find_exiftool(args.exiftool_path)
    except et.ExifToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    opts = Options(
        input=args.input,
        output=args.output,
        in_place=args.in_place,
        apply=args.apply,
        timezone=args.timezone,
        exiftool_path=exiftool_path,
        overwrite_output=args.overwrite_output,
        conflict_seconds=args.conflict_seconds,
        tz_tolerance=args.tz_tolerance,
        move_json=args.move_json,
    )

    try:
        rows = run(opts)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if args.report:
        fmt = args.report_format
        write_report(rows, args.report, fmt=fmt, csv_bom=not args.csv_no_bom)

    counts = summarize(rows)
    print(f"processed {len(rows)} files" + ("" if args.apply else " (dry-run)"))
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")

    if any(s in ERROR_STATUSES for s in counts):
        return 2
    if any(s in CONFLICT_STATUSES or s in (Status.NO_DATE.value,) for s in counts):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

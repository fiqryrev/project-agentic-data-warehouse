"""Generate source partitions.

    uv run python -m generator --date 2026-11-01
    uv run python -m generator --start 2026-01-01 --end 2026-01-07 --seed 42 --out data/landing
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from generator.write import write_day


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="generator", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--date", type=dt.date.fromisoformat, help="one partition date")
    ap.add_argument("--start", type=dt.date.fromisoformat, help="first date of a range")
    ap.add_argument("--end", type=dt.date.fromisoformat, help="last date of a range (inclusive)")
    ap.add_argument("--out", type=Path, default=Path("data/landing"))
    args = ap.parse_args(argv)
    if args.date and (args.start or args.end):
        ap.error("use --date or --start/--end, not both")
    if args.date:
        days = [args.date]
    elif args.start and args.end:
        if args.end < args.start:
            ap.error("--end is before --start")
        days = [args.start + dt.timedelta(n) for n in range((args.end - args.start).days + 1)]
    else:
        ap.error("give --date, or --start and --end")
    try:
        for day in days:
            m = write_day(args.seed, day, args.out)
            rows = sum(t["rows"] for t in m["tables"].values())
            print(f"{day}: {len(m['tables'])} tables, {rows:,} rows -> {args.out}")
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

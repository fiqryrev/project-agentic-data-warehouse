"""Load landing partitions into the lake schema.

    uv run python -m loader --date 2026-11-01
    uv run python -m loader --start 2026-01-01 --end 2026-01-07 \
        --landing data/landing --db data/dev/dwh.duckdb

The default database is the development file data/dev/dwh.duckdb. Only Airflow writes
the daily build file under data/build/, passing --db explicitly (M7).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import duckdb

from loader.load import LoadError, load_day

DEV_DB = Path("data/dev/dwh.duckdb")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="loader", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=dt.date.fromisoformat)
    ap.add_argument("--start", type=dt.date.fromisoformat)
    ap.add_argument("--end", type=dt.date.fromisoformat)
    ap.add_argument("--landing", type=Path, default=Path("data/landing"))
    ap.add_argument("--db", type=Path, default=DEV_DB,
                    help="DuckDB file to write (default: the development file)")
    args = ap.parse_args(argv)
    if args.date and (args.start or args.end):
        ap.error("use --date or --start/--end, not both")
    if args.date:
        days = [args.date]
    elif args.start and args.end and args.end >= args.start:
        days = [args.start + dt.timedelta(n) for n in range((args.end - args.start).days + 1)]
    else:
        ap.error("give --date, or --start and --end (end on or after start)")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.db))
    try:
        for day in days:
            counts = load_day(con, args.landing, day)
            print(f"{day}: {len(counts)} lake tables, {sum(counts.values()):,} rows -> {args.db}")
    except (LoadError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

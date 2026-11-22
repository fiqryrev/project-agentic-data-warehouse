"""Print ops.run_log of a build file, read-only (`make run-log`).

    uv run python -m publish.show_run_log data/build/dwh.duckdb
"""
from __future__ import annotations

import sys

import duckdb

COLUMNS = ("run_date, run_status, test_pass_count, test_warn_count, test_fail_count, "
           "lake_day_row_count, warehouse_row_count, mart_row_count, git_commit_id")


def main(argv: list[str]) -> int:
    con = duckdb.connect(argv[0], read_only=True)
    try:
        con.sql(f"select {COLUMNS} from ops.run_log order by run_date").show(max_rows=400, max_width=200)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

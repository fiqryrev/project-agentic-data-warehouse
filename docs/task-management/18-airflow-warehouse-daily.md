# 18: M7 Airflow compose (core) and warehouse_daily tasks 1 to 4 and 9, ops.run_log, backfill

## Goal

PLAN section 11, row M7 (architecture in section 6, `ops.run_log` in section 7): run the
warehouse day by day in Airflow. Done when a 7-day backfill succeeds from a clean checkout with
`make up-core`, and `ops.run_log` holds one passing row per day.

## Plan (as approved)

Approved in chat on 2026-11-22 as issue B of the layout plan ("M7: Airflow compose with profile
core, DAG `warehouse_daily` with tasks 1-4 and 9, `ops.run_log`, backfill"); started after #17.

1. `airflow/Dockerfile`: Airflow 3.3 image plus the project's uv environment and the dbt binary.
2. `infra/compose.yml`, profile core: Postgres, Airflow api-server, scheduler, dag-processor.
3. DAG `warehouse_daily`: generate_source, load_lake, dbt_build (target prod), quality_gate,
   record_run.
4. `publish/quality_gate.py`, `publish/run_recorder.py` (`ops.run_log`); `make up-core`,
   `make down-core`, `make backfill`, `make run-log`.
5. Tests for the gate, the recorder, the `.env` helper and the DAG shape.

## Decisions

- **Airflow 3.3.2**, the last 3.3 release (2026-09-17, arm64 image): PLAN pins 3.3.x; 3.4.0 is two
  weeks old. LocalExecutor with Postgres 17.6 for metadata (PLAN section 2: own slim compose).
- **Two Python environments in one image.** Airflow keeps its own; the project runs from
  `/opt/wh-venv`, built with `uv sync --frozen --group dbt --no-dev` from the repo's lock, so the
  container runs the same generator, loader, DuckDB and dbt versions as the laptop and CI. dbt's
  DuckDB driver is fetched at build time (`dbt system install-drivers`), so runs need no network.
  The repository is mounted at `/opt/wh`; dbt's target and logs go to `/tmp` in the container so
  they never mix with a person's `dbt/target`.
- **Auth:** local only, ports bound to 127.0.0.1, so the simple auth manager makes every visitor an
  admin (no password to store). The api-server and scheduler share a JWT secret, which
  `make up-core` generates into the gitignored `.env` (`airflow/env_secrets.py`).
- **Backfill runs `airflow dags test` per day, not `airflow backfill create`.** Found by trying:
  the backfill's seven runs stayed queued because the scheduler starts no run of a paused DAG
  (`DagRun.get_queued_dag_runs_to_set_running` filters `DagModel.is_paused == false()`).
  Unpausing would start the daily catch-up beside the backfill, and the two count against separate
  `max_active_runs` budgets, so two runs would write the same DuckDB file. `allowed_run_types`
  (backfill and manual only) would block that, but the scheduler would then log a warning every
  loop, since it does not filter those DAGs when it looks for runs to create. `dags test` runs the
  real tasks as one recorded run per day, on the paused DAG, strictly in order; the script stops at
  the first failed day.
- **The DAG starts paused; `start_date` stays 2026-01-01.** The synthetic world must be
  contiguous: an order refers to customers and products created on earlier days, so a day cannot
  run without every day before it. Unpausing starts the daily schedule with `catchup=True`, which
  skips days that already have a run (`run already exists; skipping dagrun creation` in the
  scheduler) and runs the rest one at a time (`max_active_runs=1`, `depends_on_past`).
- **Quality gate:** fails when a dbt node errored, failed or was skipped (warnings pass: they are
  the known defects), when the lake has no row for the day, or when a mart table is empty. An
  empty warehouse table only reports: the first day has no refunds yet, and the first version of
  the gate failed on exactly that.
- **`ops.run_log`** has one row per day, replaced on a rerun: run id, commit, dbt invocation id,
  row counts per layer and for the day's partition, dbt test counts, status and the gate's
  problems. `record_run` runs after a failure too (`all_done`) and exits 1 unless the gate of the
  same run passed (the gate writes its run id; a verdict from an earlier run is ignored), so a bad
  day is both recorded and red in Airflow. Snapshot hash and model spend come with M9 and M8;
  `ops.table_stats` is left for later.
- **Commit:** `GIT_SHA` comes from `make up-core` (`git rev-parse HEAD` on the host), since a
  worktree's `.git` file points at a host path the container cannot read.

## Done

- Clean checkout (a fresh `git clone` of the branch, no `.env`, no `data/`): `make up-core` ->
  every container healthy; `make backfill FROM=2026-01-01 TO=2026-01-07` -> `every day passed`;
  `make run-log` -> seven rows `passed`, 0 failed tests (81 pass and 3 warn on days 1-2, 79 and 5
  after), the commit id of the clone; `airflow dags list-runs warehouse_daily` -> 7 `success`.
  The image layers came from the local build cache.
- The same backfill in the worktree gave identical row counts per day (deterministic).
- First attempt with `airflow backfill create`: seven runs stayed `queued` (see Decisions).
- First version of the gate failed day 1 on the empty `fact__sales__refunds`; relaxed to marts.
- Memory with the core stack idle after the backfill (`docker stats`): about 0.86 GiB (scheduler
  0.42, api-server 0.23, dag-processor 0.17, Postgres 0.04).
- `uv run pytest -q` -> 257 passed (19 new in `tests/pipeline/`); `make checks` -> all OK.

## Open

- `ops.table_stats` (PLAN section 7) and `docs/runs/<ds>.md`.
- CI does not build the image or run the DAG; the DAG is checked statically
  (`tests/pipeline/test_airflow_files.py`). A CI job with Docker could run one day.
- The run-backfill skill (PLAN section 9) can wrap `make backfill` when it is written.

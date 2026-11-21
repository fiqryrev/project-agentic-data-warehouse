# 6: M2 deterministic source generator

## Goal

PLAN section 11, row M2 (data design in section 5): a generator with a seed, daily
partitions, documented defects and unit tests. Done when the same seed and date give
identical files.

## Plan (as approved)

`generator/` in Python with pinned `pyarrow`; one RNG per `(seed, purpose, key)` from SHA-256,
no clock; Parquet per table per day under `data/landing/` plus a manifest; small hand-written
reference files; `shop`, `ledger` and `marketing` tables; the defects from PLAN section 5 at
fixed rates; tests in `tests/generator/`. Defaults: data starts 2026-01-01, about 500 orders a
day, snappy Parquet with no time metadata.

## Decisions

- **Branch in the session's own worktree.** The app already gives this session an isolated
  worktree, so the branch `6-source-generator` was cut there from `origin/main` instead of a
  second worktree under `.worktrees/`.
- **Master data grows by formula** (2,000 customers then 40 a day; 120 sellers then 1; 600
  products then 8). The ids that exist on any day are known without reading earlier days, and
  every customer, seller and product is a pure function of `(seed, id)`. That is what lets one
  day be regenerated alone (tested).
- **Exact defect counts per partition** (`round(n * rate)` chosen by a seeded sample) for
  casing, duplicates and late rows, so tests can assert counts. Orphan keys are a seeded draw
  per order line, because an order line appears in `order_items` and later in
  `invoice_lines` and must point at the same product in both.
- **Orders are event timelines, partitions are what the source wrote that day** (changed after
  the Codex review on PR #7: a `delivered` order had `delivered_at` after its partition date).
  Each order's timeline (created, cancelled or paid, shipped, delivered, refunded) is a pure
  function of `(seed, order_id)`. Partition d holds an `orders` row for every order with an
  event on d, with its status at the end of d, and the payment, shipment, refund and ledger
  rows of d's events, so no timestamp is later than the end of d (tested). This also gives M4
  real status history to model. The rename to `in_transit` follows the partition date.
- **Every table gets a file every day**, empty when nothing happened (vouchers and campaigns
  are monthly), so the M3 loader can replace a partition without checking for it.
- **Orphan items are left out of settlements** (no seller to pay); the ledger's invoice lines
  keep them.
- **Ledger refunds re-post the invoice** on the refund day with `refund_idr` and the new
  status, keeping `invoice_date`; `posted_at` tells the postings apart.
- **Golden checksums** for seed 42 on 2026-06-01 are committed, so CI on Linux proves the files
  are byte-identical to the laptop's, not only within one run.
- `gateway` and `langfuse` sources are not generated: they come from real exports (M3, M8).

## Done

- `uv run python -m generator --start 2026-05-30 --end 2026-06-02 --out <tmp>` writes 15 tables a
  day (6,292 to 7,207 rows a day) in under a second.
- `uv run pytest -q` → all tests pass, including `tests/generator/test_generator.py`:
  identical bytes for the same seed and date, a day generated alone equals the same day
  generated after others, another seed or date changes the data, schemas, keys, ledger money,
  no timestamp after its partition day, status equal to the timeline, and each defect.

## Open

- M3 loads these partitions into `lake` with audit columns and checks idempotence.
- Staging models (M4) fix each defect; knowledge entries (M6) record them.

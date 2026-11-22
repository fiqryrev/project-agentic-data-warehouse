{% docs ledger__settlements %}

Raw seller settlements from the finance ledger: for each seller, the value of the
invoice lines paid that day, the 5% marketplace commission and the payout. Written in the
partition of that day, one row per seller with sales. `staging__ledger__settlements` reads it.

## Potential Analyses

1. **Payout per seller** -- `sum(payout_idr)` grouped by `seller_ref`, `settlement_date`.
2. **Commission per day** -- `sum(commission_idr)` grouped by `settlement_date`.
3. **Settlement vs lines** -- compare `sum(gross_sales_idr)` per day with non-orphan `ledger__invoice_lines.line_amount_idr` of the same day.

## Grain

One row per `settlement_id` (`STL-<yyyymmdd>-<seller id>`, one per seller and day).

## Table Lineage

```
ledger__settlements
└── data/landing/ledger/settlements/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `commission_idr` = round(gross * 0.05); `payout_idr` = gross - commission.
- `seller_ref` is text, `S-` plus 5 digits.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Lines with an orphan product are left out: there is no seller to pay (da-0004).
- Settlements are not adjusted for refunds.
- A seller with no paid lines that day has no row.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

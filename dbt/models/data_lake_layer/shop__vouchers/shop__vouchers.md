{% docs shop__vouchers %}

Raw voucher catalog from the shop. A batch of voucher codes is written on the 1st
of each month (and on 2026-01-01), each valid for that calendar month, with its discount
percent, discount cap and minimum spend. Every other partition is empty.
`staging__shop__vouchers` reads it; orders name the voucher they used by `voucher_code`.

## Potential Analyses

1. **Voucher terms per month** -- `voucher_code`, `discount_pct`, `max_discount_idr`, `min_spend_idr` filtered by `valid_from`.
2. **Voucher use** -- join `shop__orders` on `voucher_code` and count distinct `order_id` per code.
3. **Discount generosity** -- `avg(discount_pct)` and `avg(max_discount_idr)` grouped by `valid_from`.

## Grain

One row per `voucher_code`.

## Table Lineage

```
shop__vouchers
└── data/landing/shop/vouchers/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `discount_pct` is a whole percent (5, 10, 15 or 20).
- `valid_from` and `valid_to` are the first and last day of the month (inclusive).
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Only the first partition of a month has rows; an empty partition is normal.
- `valid_to` is always set (the month end); it is not null for current vouchers.
- No generator defect touches this table (`generator/DEFECTS.md`).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

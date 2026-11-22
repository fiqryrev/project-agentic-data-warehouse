{% docs shop__orders %}

Raw order states from the shop. A partition holds one row for every order with an
event that day (placed, paid, cancelled, shipped, delivered), carrying the order's status at the
end of the day and `updated_at` = the day's last event. So an order has several rows over its
life. It is the most defect-heavy table in the lake on purpose; `staging__shop__orders` reads it
and `fact__sales__orders` derives the current state.

## Potential Analyses

1. **Current status per order** -- latest row per `order_id` by `updated_at` (then `_dt`), never by `_dt` alone; then `count(*)` grouped by `order_status`.
2. **Duplicate check** -- group by every column and keep `having count(*) > 1` (da-0002).
3. **Late rows per day** -- count rows where `updated_at::date < _dt`, grouped by `_dt` (da-0003).
4. **Status vocabulary over time** -- `count(*)` grouped by `_dt`, `order_status` for `shipped` and `in_transit` (da-0005).
5. **Voucher uptake** -- distinct `order_id` with `voucher_code` not null, grouped by `created_at::date`.

## Grain

One row per `order_id` and `updated_at` (one per order state), except for the exact duplicates described below.

## Table Lineage

```
shop__orders
└── data/landing/shop/orders/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `shipping_fee_idr` is the fee charged to the customer.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `order_id` = `<day index of creation> * 100000 + n`; the ledger writes it `ORD-<id>`.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Duplicates: 0.5% of a day's rows appear twice, identical (`generator/DEFECTS.md`, da-0002).
- Late rows: 2% of a day's rows are held back 1 to 3 days and land in a later partition, sometimes after a newer row of the same order (da-0003). The latest partition is not the current state.
- Renamed status: `shipped` before 2026-06-01, `in_transit` from that date, late rows included (da-0005). Filter both values, or use staging.
- `count(*)` here counts order states, not orders.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

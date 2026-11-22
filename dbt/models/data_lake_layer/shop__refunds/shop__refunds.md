{% docs shop__refunds %}

Raw refunds from the shop, written on the refund day, 1 to 7 days after delivery
for a small share of completed orders. A refund is either the whole payment or the first order
line. `staging__shop__refunds` reads it; the ledger reposts the invoice on the same day.

## Potential Analyses

1. **Refunded amount per day** -- `sum(amount_idr)` grouped by `refunded_at::date`.
2. **Refund reasons** -- `count(*)` and `sum(amount_idr)` grouped by `refund_reason`.
3. **Full vs partial** -- join `shop__payments` on `order_id` and compare `amount_idr` with the payment amount.
4. **Refund rate** -- distinct refunded `order_id` over distinct paid `order_id` from `shop__payments`, by payment month.

## Grain

One row per `refund_id` (equals the `order_id`; an order is refunded at most once).

## Table Lineage

```
shop__refunds
└── data/landing/shop/refunds/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `refund_reason` is one of `damaged`, `wrong_item`, `late_delivery`, `changed_mind`.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- No generator defect touches this table (`generator/DEFECTS.md`).
- A partial refund is the first line's value capped at the payment, so it carries no share of the voucher or shipping.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

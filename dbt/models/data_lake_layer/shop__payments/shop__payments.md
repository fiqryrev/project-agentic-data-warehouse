{% docs shop__payments %}

Raw payments from the shop, written on the payment day. Only completed orders are
paid; abandoned orders (stay placed) and cancelled orders never get a row. The amount is items
minus voucher plus shipping, PPN included. `staging__shop__payments` reads it.

## Potential Analyses

1. **Paid amount per day** -- `sum(amount_idr)` grouped by `paid_at::date`.
2. **Payment method mix** -- `count(*)` and `sum(amount_idr)` grouped by `payment_method`.
3. **Time to pay** -- join `shop__orders` on `order_id` and take `paid_at - created_at`.
4. **Shop vs ledger** -- compare `sum(amount_idr)` with `ledger__invoices.gross_idr` on the first posting per invoice, by day.

## Grain

One row per `payment_id` (equals the `order_id`).

## Table Lineage

```
shop__payments
└── data/landing/shop/payments/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `payment_method` is one of `bank_transfer`, `virtual_account`, `ewallet`, `card`, `cod`.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Refunds do not change this table; they are in `shop__refunds`.
- At the edge of the loaded dates a payment can point at an order whose row has not arrived yet (late rows, da-0003).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

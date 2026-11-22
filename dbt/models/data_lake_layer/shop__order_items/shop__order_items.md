{% docs shop__order_items %}

Raw order lines from the shop, written on the order's creation day, for every order
whatever its later outcome (cancelled and abandoned orders keep their lines). Each line has a
product, a quantity and the unit price on the order day. `staging__shop__order_items` reads it.

## Potential Analyses

1. **Units and item value per day** -- `sum(quantity)` and `sum(quantity * unit_price_idr)` grouped by `_dt`.
2. **Orphan lines** -- lines whose `product_id` has no match in `shop__products` (ids from 9,000,000), counted by `_dt` (da-0004).
3. **Lines per order** -- `count(*)` grouped by `order_id`, then a distribution of that count.
4. **Top products** -- `sum(quantity)` grouped by `product_id`, joined to `shop__products` for names.

## Grain

One row per `order_item_id` (`order_id * 10 + line number`).

## Table Lineage

```
shop__order_items
└── data/landing/shop/order_items/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `unit_price_idr` is the product's list price on the order day, PPN included, before any voucher.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Orphan keys: about 0.2% of lines point at a product that never existed (`generator/DEFECTS.md`, da-0004).
- Lines of cancelled and abandoned orders are here too; join to the order's current status before summing sales.
- Lines do not sum to the payment amount: vouchers and shipping are on the order.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

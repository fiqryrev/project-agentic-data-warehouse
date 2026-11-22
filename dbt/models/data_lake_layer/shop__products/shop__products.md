{% docs shop__products %}

Raw product versions from the shop. A row is written on the day a product is
created and again on each day its price changes (each product is repriced every 30 to 120 days).
It carries seller, category, name and list price (`price_idr`, PPN included).
`staging__shop__products` reads it; the warehouse builds product price history from it.

## Potential Analyses

1. **Price changes per day** -- count rows where `updated_at > created_at`, grouped by `_dt`.
2. **Price history of a product** -- filter one `product_id`, order by `updated_at`, and compare `price_idr` with the previous row (`lag`).
3. **Catalog by category** -- latest row per `product_id`, then `count(*)` and `median(price_idr)` grouped by `category_id`.
4. **Products per seller** -- latest row per `product_id`, `count(*)` grouped by `seller_id`.

## Grain

One row per `product_id` and `updated_at` (one per product version).

## Table Lineage

```
shop__products
└── data/landing/shop/products/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `price_idr` includes the 11% PPN and is rounded to Rp100.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- A product has one row per price version; take the latest `updated_at` for the current price, or the version valid on a given day for historical prices.
- Orphan product ids (from 9,000,000) used on order lines never appear here (`generator/DEFECTS.md`, da-0004).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

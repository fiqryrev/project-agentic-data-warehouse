{% docs staging__shop__products %}

Shop product versions: one row at creation and one more at each price change.
Columns pass through unchanged. Read by `dim__sales__products`, which builds the price history.

## Potential Analyses

1. **Current price list** -- latest row per `product_id` by `updated_at`.
2. **Price change size** -- `price_idr / lag(price_idr)` over `product_id` ordered by `updated_at`.
3. **Price on an order day** -- latest version with `updated_at` on or before the order's `created_at`.

## Grain

One row per `product_id` and `updated_at`.

## Table Lineage

```
staging__shop__products
└── source('lake', 'shop__products')   (data_lake_layer)
    └── data/landing/shop/products/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `price_idr` includes the 11% PPN.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Orphan product ids (from 9,000,000) on order lines have no row here (`generator/DEFECTS.md`, da-0004).
- Several rows per product; filter to one version before counting products.
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

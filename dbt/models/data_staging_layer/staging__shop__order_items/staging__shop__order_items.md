{% docs staging__shop__order_items %}

Shop order lines, `quantity` renamed `item_quantity`. Includes lines of cancelled
and abandoned orders. Read by `fact__sales__order_items`.

## Potential Analyses

1. **Item value per order** -- `sum(item_quantity * unit_price_idr)` grouped by `order_id`.
2. **Top products** -- `sum(item_quantity)` grouped by `product_id`, joined to `staging__shop__products`.
3. **Orphan lines** -- lines with no matching `product_id` in `staging__shop__products` (da-0004).

## Grain

One row per `order_item_id`.

## Table Lineage

```
staging__shop__order_items
└── source('lake', 'shop__order_items')   (data_lake_layer)
    └── data/landing/shop/order_items/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `unit_price_idr` is the list price on the order day, PPN included, before voucher.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Orphan keys kept: about 0.2% of lines have a `product_id` from 9,000,000; the `relationships` test only warns (`generator/DEFECTS.md`, da-0004).
- Join to the order's current status before summing sales.
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

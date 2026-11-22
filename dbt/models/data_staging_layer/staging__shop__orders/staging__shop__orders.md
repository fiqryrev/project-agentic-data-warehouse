{% docs staging__shop__orders %}

Shop order states without the exact duplicates, and with `shipped` renamed
`in_transit` across history. One order has one row per state it passed through, so it is not an
order list. Read by `fact__sales__orders` (current state per order) and
`fact__sales__order_items`.

## Potential Analyses

1. **Current status per order** -- latest row per `order_id` by `updated_at`, then `_dt`; then `count(*)` by `order_status`.
2. **Funnel timing** -- per `order_id`, the min `updated_at` per `order_status`, then differences between states.
3. **Cancellation rate by day** -- orders with a `cancelled` row over distinct `order_id`, grouped by `created_at::date`.
4. **Late rows** -- rows where `updated_at::date < _dt` (da-0003).

## Grain

One row per `order_id` and `updated_at`.

## Table Lineage

```
staging__shop__orders
└── source('lake', 'shop__orders')   (lake)
    └── data/landing/shop/orders/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `order_status` is one of `placed`, `paid`, `in_transit`, `delivered`, `cancelled`.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Duplicates removed by `select distinct` (`generator/DEFECTS.md`, da-0002).
- Late rows kept: a late row's status is older than the order's current one; pick the latest `updated_at`, never the latest `_dt` (da-0003).
- `shipped` mapped to `in_transit` for all history (da-0005).
- `count(*)` counts order states, not orders.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

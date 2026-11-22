{% docs staging__shop__shipments %}

Shop shipment states with `shipped` renamed `in_transit` across history and
`courier` renamed `courier_name`. A parcel has an in-transit row and a delivered row, or only a
delivered row when both happen on one day. Read by `fact__sales__shipments`.

## Potential Analyses

1. **Delivery time by courier** -- delivered rows: `avg(delivered_at - shipped_at)` grouped by `courier_name`.
2. **Open shipments** -- `shipment_id` with no `delivered` row.
3. **Shipments per day** -- `count(distinct shipment_id)` grouped by `shipped_at::date`.

## Grain

One row per `shipment_id` and `shipment_status`.

## Table Lineage

```
staging__shop__shipments
└── source('lake', 'shop__shipments')   (data_lake_layer)
    └── data/landing/shop/shipments/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `shipment_status` is `in_transit` or `delivered`.
- `delivered_at` is null on the in-transit row.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- `shipped` mapped to `in_transit` for all history (`generator/DEFECTS.md`, da-0005).
- Count shipments with distinct `shipment_id`, not in-transit rows (same-day deliveries have none).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

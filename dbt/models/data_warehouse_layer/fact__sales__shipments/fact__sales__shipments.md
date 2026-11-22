{% docs fact__sales__shipments %}

Shipments in their current state: one row per shipment, the latest state the shop wrote. The shop
writes a row when the parcel is handed to the courier and another when it is delivered; this
table keeps the later one. Analysts use it for courier performance and delivery times.

## Potential Analyses

1. **Delivery time by courier** -- average `delivered_at - shipped_at` grouped by `courier_name`, for rows with `shipment_status = 'delivered'`.
2. **Parcels in transit** -- count rows with `shipment_status = 'in_transit'` by `courier_name` and `shipped_at::date`.
3. **Order to delivery** -- join `fact__sales__orders` on `order_id` and average `delivered_at - created_at` by `order_date`.
4. **Courier share** -- count shipments by `courier_name` and month of `shipped_at`.

## Grain

One row per `shipment_id` (equal to `order_id`, one shipment per paid order).

## Table Lineage

```
fact__sales__shipments
└── staging__shop__shipments          (staging)
    └── lake.shop__shipments          (lake)
```

## Units and Conventions

- `shipped_at` and `delivered_at` are naive UTC; `delivered_at` is null until delivery.
- `shipment_status` is `in_transit` or `delivered`.

## Known Caveats

- The source renamed `shipped` to `in_transit` from 2026-06-01; staging maps old rows too (da-0005), so only `in_transit` appears here.
- Only paid orders ship; cancelled and abandoned orders have no shipment.
- Status is current: a delivered parcel no longer shows its in-transit row. For the state history, read `staging__shop__shipments`.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

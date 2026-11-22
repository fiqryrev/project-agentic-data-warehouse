{% docs fact__sales__orders %}

Orders in their current state: one row per order, the latest state the shop wrote for it. The
shop writes an order row on each day the order has an event (placed, paid, cancelled, shipped,
delivered); this table keeps the row with the latest `updated_at`. It is the place to count
orders and read their status, voucher and shipping fee. Money received is in
`fact__sales__payments`, line detail in `fact__sales__order_items`.

## Potential Analyses

1. **Orders per day and status mix** -- count `order_id` grouped by `order_date` and `order_status`.
2. **Cancellation rate** -- `count(*) filter (where order_status = 'cancelled') / count(*)` per `order_date` or month.
3. **Abandoned orders** -- orders still `placed` more than a day after `created_at` were abandoned (paid orders pay within hours, cancellations land within 12 hours); count them by `order_date`.
4. **Voucher use** -- share of orders with `voucher_code is not null`, and their status mix against orders without one.
5. **Fulfilment time** -- join `fact__sales__shipments` on `order_id` and average `delivered_at - created_at` by `order_date`.

## Grain

One row per `order_id`.

## Table Lineage

```
fact__sales__orders
└── staging__shop__orders          (staging)
    └── lake.shop__orders          (lake)
```

## Units and Conventions

- `shipping_fee_idr` is whole rupiah charged to the customer.
- `created_at` and `updated_at` are naive UTC; `order_date = created_at::date`.
- `order_status`: `placed`, `paid`, `in_transit`, `delivered` or `cancelled`.
- `order_id` is `<day index of creation> * 100000 + n`; the ledger writes `ORD-<order_id>`.

## Known Caveats

- The source renamed `shipped` to `in_transit` from 2026-06-01; staging maps old rows too, so only `in_transit` appears here (da-0005). Do not filter on `shipped`.
- Exact duplicate rows in the source (da-0002) are dropped in staging; `count(*)` here is an order count.
- Late rows (da-0003) never win, because the latest `updated_at` wins. At the edge of the loaded dates the newest row of an order may still be in transit, so the most recent days can show a status that is one step behind.
- Status is current, not as of a past date: an order placed in January and delivered later shows `delivered`. For status history, read `staging__shop__orders`.
- Abandoned orders have no status of their own; they stay `placed`.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

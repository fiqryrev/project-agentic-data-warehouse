{% docs rpt__sales__orders__daily %}

Orders created per day: how many, how many are now cancelled or delivered, the units ordered and
their merchandise value. It is the table to read for order volume and status mix over time.
Status is the order's current status, so older days settle while recent days are still moving.

## Potential Analyses

1. **Order volume trend** -- `order_count` by `order_date`, or summed by month.
2. **Cancellation and delivery rates** -- `cancelled_order_count / order_count` and `delivered_order_count / order_count` per `order_date`.
3. **Units per order** -- `unit_count / nullif(order_count, 0)` per day.
4. **Average merchandise value per order** -- `merchandise_idr / nullif(order_count, 0)` per day.
5. **Orders against marketing spend** -- join `rpt__marketing__spend__daily` (summed per day) on `spend_date = order_date`; same-day comparison only.

## Grain

One row per `order_date`.

## Table Lineage

```
rpt__sales__orders__daily
├── fact__sales__orders                  (data_warehouse_layer)
│   └── staging__shop__orders            (data_staging_layer)
└── fact__sales__order_items             (data_warehouse_layer)
    └── staging__shop__order_items       (data_staging_layer)
```

## Units and Conventions

- `merchandise_idr` is whole rupiah, PPN included, before voucher and shipping.
- `order_date` is the day the order was created; counts are of orders created that day.

## Known Caveats

- `merchandise_idr` is not revenue: it counts lines of every order, cancelled and abandoned ones included, before voucher and shipping. For revenue use `rpt__finance__revenue__daily`.
- The cancelled and delivered counts are current status: a day's `delivered_order_count` grows for several days after the order date. Orders neither cancelled nor delivered are still placed (including abandoned), paid or in transit.
- An order whose row is still a late row in transit (da-0003) is missing from that day until it lands, so the newest days can undercount.
- Merchandise includes lines with orphan product ids (da-0004).

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

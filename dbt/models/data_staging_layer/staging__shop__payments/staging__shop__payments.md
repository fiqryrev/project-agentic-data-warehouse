{% docs staging__shop__payments %}

Shop payments, one per paid order, `payment_method` renamed
`payment_method_code`. Read by `fact__sales__payments`.

## Potential Analyses

1. **Paid amount per day** -- `sum(amount_idr)` grouped by `paid_at::date`.
2. **Method mix** -- `count(*)` grouped by `payment_method_code`.
3. **Average order value** -- `avg(amount_idr)` by week of `paid_at`.

## Grain

One row per `payment_id`.

## Table Lineage

```
staging__shop__payments
└── source('lake', 'shop__payments')   (data_lake_layer)
    └── data/landing/shop/payments/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `amount_idr` = items minus voucher plus shipping, PPN included.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Abandoned and cancelled orders have no payment.
- A payment can point at an order whose row is still in transit at the edge of the loaded dates (da-0003).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

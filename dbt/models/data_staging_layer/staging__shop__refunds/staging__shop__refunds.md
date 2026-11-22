{% docs staging__shop__refunds %}

Shop refunds, one per refunded order, `refund_reason` renamed
`refund_reason_code`. Read by `fact__sales__refunds`.

## Potential Analyses

1. **Refunds per day** -- `sum(amount_idr)` grouped by `refunded_at::date`.
2. **Reasons** -- `count(*)` grouped by `refund_reason_code`.
3. **Days from delivery to refund** -- join `staging__shop__shipments` (delivered rows) on `order_id`, `refunded_at - delivered_at`.

## Grain

One row per `refund_id`.

## Table Lineage

```
staging__shop__refunds
└── source('lake', 'shop__refunds')   (lake)
    └── data/landing/shop/refunds/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- No generator defect touches refunds (`generator/DEFECTS.md`).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

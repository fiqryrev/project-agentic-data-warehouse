{% docs staging__shop__sellers %}

Shop sellers, one row per seller, renamed to warehouse names (`city_name`,
`province_name`). Sellers never change after creation. Read by `dim__sales__sellers`.

## Potential Analyses

1. **Sellers by province** -- `count(*)` grouped by `province_name`.
2. **Seller growth** -- `count(*)` grouped by `created_at::date`, cumulative.
3. **Seller payouts** -- join `staging__ledger__settlements` on `seller_id` and sum `payout_idr`.

## Grain

One row per `seller_id`.

## Table Lineage

```
staging__shop__sellers
└── source('lake', 'shop__sellers')   (lake)
    └── data/landing/shop/sellers/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- Seller names are fictional.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- No generator defect touches sellers (`generator/DEFECTS.md`).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

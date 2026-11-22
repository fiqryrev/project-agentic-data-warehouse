{% docs staging__ledger__settlements %}

Daily seller settlements from the ledger, with `seller_ref` turned back into the
shop's numeric `seller_id`. Read by `fact__finance__settlements`.

## Potential Analyses

1. **Payout per seller per month** -- `sum(payout_idr)` grouped by `seller_id`, month of `settlement_date`.
2. **Commission per day** -- `sum(commission_idr)` grouped by `settlement_date`.
3. **Top sellers** -- `sum(gross_sales_idr)` grouped by `seller_id`, joined to `staging__shop__sellers`.

## Grain

One row per `settlement_id`.

## Table Lineage

```
staging__ledger__settlements
└── source('lake', 'ledger__settlements')   (data_lake_layer)
    └── data/landing/ledger/settlements/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `commission_idr` is 5% of `gross_sales_idr`; `payout_idr` = gross - commission.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Orphan-product lines are not settled (da-0004).
- Not adjusted for refunds.
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

{% docs fact__finance__settlements %}

Daily seller settlements from the ledger: one row per seller and day on which the seller had paid
order lines, with the seller's sales, the 5% marketplace commission and the payout. The ledger
seller key is turned back into the shop's numeric `seller_id`. Analysts use it for seller payouts
and for the marketplace's commission income.

## Potential Analyses

1. **Commission income per month** -- sum `commission_idr` grouped by month of `settlement_date`.
2. **Top sellers by payout** -- sum `payout_idr` per `seller_id`, join `dim__sales__sellers` for `seller_name` and `city_name`.
3. **Active sellers per day** -- count `seller_id` per `settlement_date`; a seller with no paid lines that day has no row.
4. **Commission check** -- compare `commission_idr` with `round(gross_sales_idr * 0.05)` and `payout_idr` with `gross_sales_idr - commission_idr`.

## Grain

One row per `settlement_id` (one seller on one `settlement_date`).

## Table Lineage

```
fact__finance__settlements
└── staging__ledger__settlements          (staging)
    └── lake.ledger__settlements          (lake)
```

## Units and Conventions

- Money in whole rupiah (`_idr`), PPN included.
- `payout_idr = gross_sales_idr - commission_idr`; `commission_idr = round(gross_sales_idr * 0.05)`.
- `settlement_date` is the payment day of the lines settled.
- `settlement_id` is `STL-<yyyymmdd>-<seller_id>`.

## Known Caveats

- `gross_sales_idr` sums invoice lines, which are items before voucher and shipping, so a day's settlements do not add up to the day's invoice `gross_idr` or `net_revenue_idr`.
- Lines with orphan product keys (da-0004) have no known seller and are left out of settlements.
- Settlements are not adjusted for later refunds.
- No row means no paid sales that day, not a zero payout row.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

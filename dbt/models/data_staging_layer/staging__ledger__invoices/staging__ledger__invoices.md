{% docs staging__ledger__invoices %}

Ledger invoice postings with the ledger's text keys turned back into the shop's
numeric `order_id` and `customer_id`. An invoice has a posting on the payment day and another on
a refund. Read by `fact__finance__invoices`.

## Potential Analyses

1. **Net revenue per day** -- latest posting per `invoice_id` by `posted_at`, `sum(net_revenue_idr)` grouped by `invoice_date`.
2. **Status mix** -- latest posting per invoice, `count(*)` by `invoice_status`.
3. **Shop vs ledger** -- join `staging__shop__payments` on `order_id` and compare `gross_idr` with `amount_idr`.

## Grain

One row per `invoice_id` and `posted_at`.

## Table Lineage

```
staging__ledger__invoices
└── source('lake', 'ledger__invoices')   (lake)
    └── data/landing/ledger/invoices/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `gross_idr` includes PPN; `net_revenue_idr` excludes PPN and refunds.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Summing all postings double counts refunded invoices; take the latest posting.
- Status words stay the ledger's (`PAID`, `PARTIAL_REFUND`, `REFUNDED`); only keys are converted.
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

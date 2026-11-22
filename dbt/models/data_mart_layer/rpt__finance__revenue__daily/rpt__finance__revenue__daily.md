{% docs rpt__finance__revenue__daily %}

Revenue per day as the two systems see it: money the shop received (`shop_paid_idr`), and the
ledger's gross, refunds, PPN and net revenue on invoices raised that day. It is the first table
to read for "how much did we make": `net_revenue_idr` is revenue net of refunds and PPN. Both
sides are keyed on the payment date, so the shop and ledger columns line up day by day.

## Potential Analyses

1. **Net revenue trend** -- sum `net_revenue_idr` by month of `revenue_date`, or a 7-day moving average over `revenue_date`.
2. **Shop and ledger reconciliation** -- compare `shop_paid_idr` with `ledger_gross_idr` per day; they agree because every invoice's gross equals its payment.
3. **Refund share** -- `ledger_refund_idr / nullif(ledger_gross_idr, 0)` per month of `revenue_date`.
4. **Average invoice value** -- `ledger_gross_idr / nullif(invoice_count, 0)` per day.
5. **Revenue against marketing spend** -- join `rpt__marketing__spend__daily` (summed per day) on `spend_date = revenue_date`; a same-day comparison, not attribution.

## Grain

One row per `revenue_date`.

## Table Lineage

```
rpt__finance__revenue__daily
├── fact__sales__payments              (data_warehouse_layer)
│   └── staging__shop__payments        (data_staging_layer)
└── fact__finance__invoices            (data_warehouse_layer)
    └── staging__ledger__invoices      (data_staging_layer)
```

## Units and Conventions

- Money in whole rupiah (`_idr`). `shop_paid_idr` and `ledger_gross_idr` include PPN; `net_revenue_idr` excludes PPN and refunds.
- `revenue_date` is the payment date (shop) and the invoice date (ledger), which is the same day.
- Days with no activity on one side show 0 on that side.

## Known Caveats

- Refunds sit on the payment date, not the refund date: `ledger_refund_idr` and `net_revenue_idr` for a past day go down when a later refund lands, so recent days are not final. For refunds by the day they happened, use `fact__sales__refunds`.
- `shop_paid_idr` is not reduced by refunds; only the ledger columns are.
- `ledger_tax_idr` is PPN on the original gross and is not reduced by refunds, so `ledger_gross_idr - ledger_tax_idr - ledger_refund_idr` is not `net_revenue_idr`.
- Net revenue is rounded per invoice before summing, so it can differ by a few rupiah from `(ledger_gross_idr - ledger_refund_idr) / 1.11` on the day's totals.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

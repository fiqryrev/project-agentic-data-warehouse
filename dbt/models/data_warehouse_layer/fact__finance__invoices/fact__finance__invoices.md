{% docs fact__finance__invoices %}

Ledger invoices in their current state: one row per invoice, its latest posting. The ledger
raises an invoice when an order is paid and posts it again, same `invoice_date`, when the order is
refunded, so the current row carries the refund and the new status. This is the source of truth
for revenue: `net_revenue_idr` is net of refunds and of the 11% PPN. Ledger keys are turned back
into the shop's numeric `order_id` and `customer_id` so it joins to the sales facts.

## Potential Analyses

1. **Net revenue per day or month** -- sum `net_revenue_idr` grouped by `invoice_date` (or its month). This is revenue on the payment date, net of refunds whenever they happened.
2. **Refund rate** -- `count(*) filter (where invoice_status <> 'PAID') / count(*)` and `sum(refund_idr) / sum(gross_idr)` per month of `invoice_date`.
3. **Revenue by customer city at order time** -- join `fact__sales__order_items` on `order_id` for `customer_version_key`, then `dim__sales__customers`; take the invoice amounts once per order (aggregate lines first) to avoid multiplying them.
4. **Shop and ledger reconciliation** -- join `fact__sales__payments` on `order_id` and compare `gross_idr` with `amount_idr`; they agree on every paid order (test `assert_invoice_gross_matches_shop_payment`).
5. **Refunds posted late** -- compare `posted_at::date` with `invoice_date` for refunded invoices to see how long after payment the refund landed.

## Grain

One row per `invoice_id` (also unique per `order_id`).

## Table Lineage

```
fact__finance__invoices
└── staging__ledger__invoices          (staging)
    └── lake.ledger__invoices          (lake)
```

## Units and Conventions

- Money in whole rupiah (`_idr`). `gross_idr` is what the customer paid: items minus voucher plus shipping, PPN included.
- `net_revenue_idr = round((gross_idr - refund_idr) / 1.11)`, within one rupiah (test `assert_net_revenue_is_net_of_refunds_and_tax`).
- `invoice_date` is the payment date; `posted_at` (naive UTC) is when this version was posted.
- `invoice_status`: `PAID`, `PARTIAL_REFUND` (refund below gross) or `REFUNDED` (refund equals gross).
- `invoice_id` is `INV-<order_id>`.

## Known Caveats

- `tax_idr` is the PPN inside the original gross and is not reduced by a refund, so `gross_idr - tax_idr - refund_idr` is not net revenue; use `net_revenue_idr`.
- A refund changes an old row: the refund is attributed to `invoice_date` (payment day), not the refund day. Past days' revenue drops when a refund lands, up to several days after delivery. For refunds by the day they happened, use `fact__sales__refunds.refund_date`.
- Only paid orders have an invoice; cancelled and abandoned orders never reach the ledger.
- Invoice lines (not in this table) hold items before voucher and shipping, so they do not sum to `gross_idr`.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

{% docs fact__sales__payments %}

Payments the shop received: one row per paid order, with method, amount and time. Only orders
that complete are paid; cancelled and abandoned orders have no payment. This is the shop's view
of money in (gross, PPN included, before refunds); the ledger's view, net of refunds and PPN, is
`fact__finance__invoices`.

## Potential Analyses

1. **Money received per day** -- sum `amount_idr` grouped by `paid_date`.
2. **Payment method mix** -- count and sum `amount_idr` by `payment_method_code` and month of `paid_date`.
3. **Time to pay** -- join `fact__sales__orders` on `order_id` and average `paid_at - created_at`.
4. **Average order value** -- `avg(amount_idr)` by `paid_date`; this includes shipping and is net of vouchers.
5. **Received net of refunds** -- left join `fact__sales__refunds` on `order_id` and sum `amount_idr - coalesce(r.amount_idr, 0)`.

## Grain

One row per `payment_id` (equal to `order_id`, one payment per order).

## Table Lineage

```
fact__sales__payments
└── staging__shop__payments          (staging)
    └── lake.shop__payments          (lake)
```

## Units and Conventions

- `amount_idr` is whole rupiah: items minus voucher plus shipping, PPN included.
- `paid_at` is naive UTC; `paid_date = paid_at::date`.
- `payment_method_code` is one of `bank_transfer`, `virtual_account`, `ewallet`, `card`, `cod`.

## Known Caveats

- Amounts are gross of PPN and not reduced by refunds; for revenue use `fact__finance__invoices.net_revenue_idr`.
- Every payment equals the ledger invoice `gross_idr` of the same order (test `assert_invoice_gross_matches_shop_payment`).
- The `order_id` relationship test warns, not fails: the order row may be a late row not loaded yet at the edge of the loaded dates (da-0003).

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

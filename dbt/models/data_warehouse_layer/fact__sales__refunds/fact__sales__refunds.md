{% docs fact__sales__refunds %}

Refunds the shop paid back: one row per refunded order, with reason, amount and time. A refund
comes 1 to 7 days after delivery and is either the whole payment or the amount of the order's
first line. Use it for refunds by the day they happened; the ledger records the same refund on
the invoice's payment date in `fact__finance__invoices`.

## Potential Analyses

1. **Refunds per day** -- count and sum `amount_idr` grouped by `refund_date`.
2. **Refund reasons** -- count by `refund_reason_code` and month of `refund_date`.
3. **Full against partial refunds** -- join `fact__sales__payments` on `order_id`; `amount_idr = p.amount_idr` is a full refund, otherwise partial.
4. **Days from delivery to refund** -- join `fact__sales__shipments` on `order_id` and average `refunded_at - delivered_at`.
5. **Refunds by category** -- join `fact__sales__order_items` and `dim__sales__products`; for partial refunds the refunded line is the first line (`order_item_id = order_id * 10 + 1`).

## Grain

One row per `refund_id` (equal to `order_id`, at most one refund per order).

## Table Lineage

```
fact__sales__refunds
└── staging__shop__refunds          (staging)
    └── lake.shop__refunds          (lake)
```

## Units and Conventions

- `amount_idr` is whole rupiah, PPN included (the same basis as payments).
- `refunded_at` is naive UTC; `refund_date = refunded_at::date`.
- `refund_reason_code` is one of `damaged`, `wrong_item`, `late_delivery`, `changed_mind`.

## Known Caveats

- A partial refund is the first line's quantity times unit price, which can be for an orphan product (da-0004).
- The refund amount includes PPN; to compare with net revenue divide by 1.11, or use `fact__finance__invoices`.
- Totals by `refund_date` differ from `rpt__finance__revenue__daily.ledger_refund_idr`, which puts each refund on the payment date.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

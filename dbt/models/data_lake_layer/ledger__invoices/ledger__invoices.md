{% docs ledger__invoices %}

Raw invoice postings from the finance ledger. An invoice is posted on the payment
day and posted again, with the refund amount and new status, on the refund day; `invoice_date`
stays the payment date. The ledger uses its own keys (`ORD-<id>`, `C-0001234`) and status
words (`PAID`, `PARTIAL_REFUND`, `REFUNDED`). Revenue here is net of refunds and PPN.
`staging__ledger__invoices` reads it.

## Potential Analyses

1. **Net revenue by invoice date** -- latest posting per `invoice_id` by `posted_at`, then `sum(net_revenue_idr)` grouped by `invoice_date`.
2. **Refund postings** -- rows where `invoice_status <> 'PAID'`, grouped by `posted_at::date`.
3. **Tax collected** -- first posting per `invoice_id`, `sum(tax_idr)` by `invoice_date`.
4. **Shop vs ledger reconciliation** -- join `shop__payments` on `order_ref = 'ORD-' || order_id` and compare `gross_idr` with `amount_idr`.

## Grain

One row per `invoice_id` and `posted_at` (one per posting).

## Table Lineage

```
ledger__invoices
└── data/landing/ledger/invoices/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `gross_idr` includes PPN; `tax_idr` is the 11% PPN inside it; `net_revenue_idr` = (gross - refund) / 1.11, rounded.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- Keys are text: `invoice_id` `INV-<order id>`, `order_ref` `ORD-<order id>`, `cust_ref` `C-` plus 7 digits.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- A refunded invoice has two rows; summing all rows double counts. Take the latest posting per `invoice_id`.
- The ledger disagrees with the shop on keys, status words and revenue on purpose (`generator/DEFECTS.md`, section on the ledger).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

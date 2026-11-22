{% docs ledger__invoice_lines %}

Raw invoice lines from the finance ledger, written on the payment day, one per
order line of a paid order. Lines hold items before voucher and shipping, so they do not sum to
the invoice's `gross_idr`. Lines are not reposted on a refund. `staging__ledger__invoice_lines`
reads it.

## Potential Analyses

1. **Item value per invoice** -- `sum(line_amount_idr)` grouped by `invoice_id`, compared with `ledger__invoices.gross_idr` to size voucher and shipping.
2. **Orphan product refs** -- lines whose `product_ref` has no match in `shop__products` (da-0004).
3. **Units per day** -- `sum(quantity)` grouped by `_dt`.

## Grain

One row per `invoice_id` and `line_no`.

## Table Lineage

```
ledger__invoice_lines
└── data/landing/ledger/invoice_lines/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `line_amount_idr` = `quantity` * unit price, PPN included, before voucher.
- `product_ref` is the shop's numeric product id (int64).
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Orphan keys: about 0.2% of lines carry a `product_ref` from 9,000,000 with no product (`generator/DEFECTS.md`, da-0004); these lines are left out of settlements.
- Lines never sum to `gross_idr` (no voucher, no shipping).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

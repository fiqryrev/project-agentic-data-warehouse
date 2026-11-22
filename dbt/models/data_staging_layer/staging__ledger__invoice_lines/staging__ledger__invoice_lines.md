{% docs staging__ledger__invoice_lines %}

Ledger invoice lines, with `line_no`, `product_ref` and `quantity` renamed
`line_number`, `product_id` and `item_quantity`. No warehouse model reads it yet.

## Potential Analyses

1. **Item value per invoice** -- `sum(line_amount_idr)` grouped by `invoice_id`.
2. **Voucher and shipping gap** -- join `staging__ledger__invoices` (first posting) and compare `gross_idr` with the line total.
3. **Orphan lines** -- `product_id` with no match in `staging__shop__products` (da-0004).

## Grain

One row per `invoice_id` and `line_number`.

## Table Lineage

```
staging__ledger__invoice_lines
└── source('lake', 'ledger__invoice_lines')   (lake)
    └── data/landing/ledger/invoice_lines/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `line_amount_idr` = quantity * unit price, PPN included, before voucher.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Orphan keys kept: about 0.2% of lines carry a `product_id` from 9,000,000 (`generator/DEFECTS.md`, da-0004).
- Lines do not sum to `gross_idr`.
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

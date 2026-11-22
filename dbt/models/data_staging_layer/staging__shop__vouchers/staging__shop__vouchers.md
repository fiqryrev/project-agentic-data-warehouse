{% docs staging__shop__vouchers %}

The shop's monthly voucher catalog, one row per voucher code, with `valid_from`
and `valid_to` renamed `valid_from_date` and `valid_to_date`. No warehouse model reads it yet;
it is the reference for `voucher_code` on orders.

## Potential Analyses

1. **Voucher terms** -- `discount_pct`, `max_discount_idr`, `min_spend_idr` per `voucher_code`.
2. **Voucher use** -- join `staging__shop__orders` on `voucher_code`, count distinct `order_id` per code.
3. **Vouchers valid on a day** -- filter `<day> between valid_from_date and valid_to_date`.

## Grain

One row per `voucher_code`.

## Table Lineage

```
staging__shop__vouchers
└── source('lake', 'shop__vouchers')   (data_lake_layer)
    └── data/landing/shop/vouchers/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `discount_pct` is a whole percent.
- `valid_from_date` and `valid_to_date` are inclusive month bounds.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- `valid_to_date` is always the month end in the source, never null, although its column description says it can be null.
- No generator defect touches vouchers (`generator/DEFECTS.md`).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

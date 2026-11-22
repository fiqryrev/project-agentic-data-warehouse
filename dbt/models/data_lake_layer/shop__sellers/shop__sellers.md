{% docs shop__sellers %}

Raw seller records from the shop, written once on the day each seller is created
(the base sellers on 2026-01-01, then new ones each day). Sellers never change after creation.
`staging__shop__sellers` reads it; the ledger refers to the same sellers as `S-00007`.

## Potential Analyses

1. **New sellers per day** -- `count(*)` grouped by `_dt`.
2. **Sellers by province** -- `count(*)` grouped by `province`, `city`.
3. **Seller age** -- `created_at` joined to products (`seller_id`) to compare catalog size with how long a seller has existed.

## Grain

One row per `seller_id`.

## Table Lineage

```
shop__sellers
└── data/landing/shop/sellers/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- Seller names are fictional.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- No generator defect touches this table (`generator/DEFECTS.md`); `city` is already in title case.
- There is no update row: a seller's city never changes in the source.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

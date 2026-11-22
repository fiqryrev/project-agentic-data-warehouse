{% docs shop__categories %}

Raw copy of the shop's category list. The generator writes the full list of
categories every day (from `generator/reference/categories.csv`), so each partition repeats
every category. It exists so staging can pick the latest copy of each category; only
`staging__shop__categories` reads it.

## Potential Analyses

1. **Category list drift** -- compare `category_name` and `parent_name` per `category_id` across `_dt` (`count(distinct category_name)` grouped by `category_id`) to spot a renamed category.
2. **Partition completeness** -- `count(*)` grouped by `_dt` to confirm every loaded day carries the full list.
3. **Category tree** -- distinct `parent_name`, `category_name` from the latest `_dt` to list the top-level groups and their categories.

## Grain

One row per `category_id` per `_dt` (the whole list, repeated every day).

## Table Lineage

```
shop__categories
└── data/landing/shop/categories/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Ids are int64; names are Indonesian text.
- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- The same category appears in every partition; never count rows here as categories. Use `staging__shop__categories` (latest copy per id).
- No generator defect touches this table (`generator/DEFECTS.md`).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

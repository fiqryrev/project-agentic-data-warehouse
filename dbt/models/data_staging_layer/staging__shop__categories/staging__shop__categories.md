{% docs staging__shop__categories %}

The shop's categories, one row per category: the latest copy from the lake, where
the full list arrives every day. Columns: id, Indonesian name and top-level group
(`parent_name`). Read by `dim__sales__categories` and `dim__sales__products`.

## Potential Analyses

1. **Category tree** -- `parent_name`, `category_name` ordered by `parent_name`.
2. **Products per category** -- join `staging__shop__products` on `category_id` (latest version per product) and count.
3. **Sales by category group** -- join order lines through products to `category_id`, then sum by `parent_name`.

## Grain

One row per `category_id`.

## Table Lineage

```
staging__shop__categories
└── source('lake', 'shop__categories')   (lake)
    └── data/landing/shop/categories/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Names are Indonesian text; `_dt` on the kept row is the latest partition that carried the category.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- None from `generator/DEFECTS.md`; the only treatment is keeping the latest copy of the daily full list (`row_number()` by `_dt` desc).

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

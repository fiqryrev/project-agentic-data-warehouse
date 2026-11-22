{% docs dim__sales__categories %}

Product categories of the shop, one row per category, with its Indonesian name and the
top-level group it belongs to. The list comes from a fixed reference file and arrives in full
every day; staging keeps the latest copy. Analysts use it to roll products and sales up by
category or group.

## Potential Analyses

1. **Sales by category group** -- join `fact__sales__order_items` to `dim__sales__products` on `product_version_key`, then to this table on `category_id`, and sum `line_amount_idr` by `parent_name`.
2. **Catalogue size per category** -- join `dim__sales__products` filtered to `is_current`, count `product_id` per `category_name`.
3. **Category lookup** -- list `category_id`, `category_name`, `parent_name` to translate ids in other tables.

## Grain

One row per `category_id`.

## Table Lineage

```
dim__sales__categories
└── staging__shop__categories          (staging)
    └── lake.shop__categories          (lake)
```

## Units and Conventions

- `category_name` is Indonesian; `parent_name` is the top-level group.
- `dim__sales__products` already carries `category_name` and `parent_name`, so a join here is only needed for category-level questions.

## Known Caveats

- None known: the list is a fixed reference file written in full every day and no defect in `generator/DEFECTS.md` touches it.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

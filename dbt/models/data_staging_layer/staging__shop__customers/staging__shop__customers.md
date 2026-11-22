{% docs staging__shop__customers %}

Shop customer versions: one row when a customer is created and one more each time
they move to another city. Columns are renamed to warehouse names (`email_address`, `city_name`,
`province_name`) and the city is put in title case. Read by `dim__sales__customers`, which builds
the customer history.

## Potential Analyses

1. **Current city** -- latest row per `customer_id` by `updated_at`, then `count(*)` grouped by `city_name`.
2. **Moves per month** -- rows where `updated_at > created_at`, grouped by `date_trunc('month', updated_at)`.
3. **City as of a day** -- latest row per `customer_id` with `updated_at <= <day>`.

## Grain

One row per `customer_id` and `updated_at`.

## Table Lineage

```
staging__shop__customers
└── source('lake', 'shop__customers')   (data_lake_layer)
    └── data/landing/shop/customers/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `city_name` is title case.
- `full_name` and `email_address` are fictional.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- Casing defect fixed: `city_name` is title case (`generator/DEFECTS.md`, da-0001).
- Several rows per customer; filter to the latest version before counting customers.
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

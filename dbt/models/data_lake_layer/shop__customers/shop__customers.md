{% docs shop__customers %}

Raw customer versions from the shop. A row is written on the day a customer is
created (the base customers on 2026-01-01, migrated at midnight, then new customers each day) and
again on each day an existing customer moves to another city. It holds the customer's name,
email, city and province, with `created_at` and `updated_at` (the moment the shop wrote that
version). `staging__shop__customers` reads it; the warehouse builds customer history from it.

## Potential Analyses

1. **Moves per day** -- count rows where `updated_at > created_at`, grouped by `_dt`, to see how many customers moved each day.
2. **New customers per day** -- count rows where `updated_at = created_at`, grouped by `_dt`.
3. **City casing check** -- count rows where `city = upper(city) or city = lower(city)`, grouped by `_dt` (da-0001).
4. **Customer's city history** -- filter one `customer_id`, order by `updated_at`, to list each city they lived in.

## Grain

One row per `customer_id` and `updated_at` (one per customer version).

## Table Lineage

```
shop__customers
└── data/landing/shop/customers/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `email` and `full_name` are fictional (`example.com` addresses).
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Casing defect: about 10% of the rows written each day carry `city` all upper or all lower case (`generator/DEFECTS.md`, da-0001). Staging fixes it.
- A customer has several rows once they move; take the latest `updated_at` for the current city.
- A mover's row repeats the original `created_at`; only `city`, `province` and `updated_at` change.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

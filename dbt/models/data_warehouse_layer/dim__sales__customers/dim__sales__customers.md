{% docs dim__sales__customers %}

Customers with history: one row per customer version, the first when the customer is created
and another each time they move to a new city, valid from `valid_from_at` until `valid_to_at`.
It is built from the whole lake history, so a backfill rebuilds the same versions. Analysts use
it to place an order in the city the customer lived in when they ordered (through
`customer_version_key` on `fact__sales__order_items`) or to see where customers live now
(`is_current`).

## Potential Analyses

1. **Sales by city at order time** -- join `fact__sales__order_items` on `customer_version_key` and sum `line_amount_idr` by `city_name` or `province_name`; this uses the city valid when the order was placed.
2. **Customers by current city** -- filter `is_current` and count `customer_id` by `city_name`.
3. **Movers** -- count versions per `customer_id`; customers with more than one row have moved, and `lag(city_name)` over `valid_from_at` gives the from and to cities.
4. **New customers per day** -- count distinct `customer_id` by `created_at::date`.
5. **City on a given moment** -- filter `valid_from_at <= :ts and (valid_to_at is null or valid_to_at > :ts)` to get one row per customer as of `:ts`.

## Grain

One row per `customer_version_key` (equivalently, per `customer_id` and `valid_from_at`).

## Table Lineage

```
dim__sales__customers
└── staging__shop__customers          (staging)
    └── lake.shop__customers          (lake)
```

## Units and Conventions

- Timestamps `_at` are naive UTC; `valid_to_at` is null on the current version.
- `is_current` is true on exactly one version per customer (tested by `scd2_valid`).
- `customer_version_key` is `md5(customer_id || '|' || updated_at)`.
- `city_name` is title case. The ledger writes the customer as `cust_ref` `C-0001234`; here it is the numeric `customer_id`.
- Names and emails are fictional.

## Known Caveats

- Counting rows counts versions, not customers; use `count(distinct customer_id)` or filter `is_current`.
- The source writes some cities all upper or all lower case (da-0001); staging fixes it, so filter on the title-case value here.
- Every new version is a real move to another city (test `assert_customer_versions_record_a_move`), and versions never overlap or leave gaps (`scd2_valid`).
- Join facts on `customer_version_key`, not `customer_id`: joining on `customer_id` alone multiplies rows for customers who moved. The version is chosen by order timestamp, so a move later on the order day does not apply (test `assert_order_customer_existed_at_order_time`).
- The base customers of 2026-01-01 were migrated at midnight, so their first `valid_from_at` is that midnight.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}

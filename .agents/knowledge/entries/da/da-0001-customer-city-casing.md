---
id: da-0001
title: Customer city casing in the shop source
tags: [shop, customers, city, casing, defect, data-quality]
paths: [generator/DEFECTS.md, generator/model.py, dbt/models/data_staging_layer/staging__shop__customers/staging__shop__customers.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Casing |
  - dbt/models/data_staging_layer/staging__shop__customers/staging__shop__customers.sql::title_case
  - generator/model.py::customers += [dict(moved_customer(seed, cid, day))
supersedes: []
---

## Meaning

`lake.shop__customers.city` is a city name. 10% of the customer rows written each day (new
customers and the versions of customers who moved) carry the city all upper case or all lower
case (`JAKARTA`, `bandung`). It is the same city as its title-case spelling; nothing else
differs. `generator/DEFECTS.md` says "new customers"; the generator samples over every row it
writes that day.

## Counts

On the 3-day CI dataset (`make dbt-ci`, 2026-01-01 to 01-03): 208 of 2,088 customer rows.

```sql
select count(*) filter (where city = upper(city) or city = lower(city)) as miscased,
       count(*) as customer_rows
from lake.shop__customers;
```

## Terms

"Casing", "upper-case city", "messy city names". Downstream, `staging__shop__customers` and
every warehouse table carry the title-case city as `city_name`.

## Data quality

Fixed in staging with the `title_case` macro, so filter `city_name` in `staging` and `warehouse`
on the title-case value; filter the lake only with `lower(city)`. DuckDB has no `initcap`, though
`generator/DEFECTS.md` names it as the way to spot the defect; use the query above.

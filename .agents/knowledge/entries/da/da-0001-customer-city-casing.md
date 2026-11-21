---
id: da-0001
title: Customer city casing in the shop source
tags: [shop, customers, city, casing, defect, data-quality]
paths: [generator/DEFECTS.md, dbt/models/staging/shop/staging__shop__customers.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Casing |
  - dbt/models/staging/shop/staging__shop__customers.sql::title_case
supersedes: []
---

## Meaning

`lake.shop__customers.city` is a city name. About 10% of a day's new customers arrive with
the city written all upper case or all lower case (`JAKARTA`, `bandung`). It is the same city
as its title-case spelling; nothing else differs.

## Counts

On the 3-day CI dataset (`make dbt-ci`, 2026-01-01 to 01-03): 208 of 2,088 customer rows.

```sql
select count(*) filter (where city = upper(city) or city = lower(city)) as miscased,
       count(*) as customer_rows
from lake.shop__customers;
```

## Terms

"Casing", "upper-case city", "messy city names". Downstream, `staging__shop__customers` and
every warehouse table carry the title-case city.

## Data quality

Fixed in staging with the `title_case` macro, so filter `staging` and `warehouse` on the
title-case value; filter the lake only with `lower(city)`. DuckDB has no `initcap`, though
`generator/DEFECTS.md` names it as the way to spot the defect; use the query above.

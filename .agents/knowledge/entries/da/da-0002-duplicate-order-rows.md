---
id: da-0002
title: Exact duplicate order rows in the shop source
tags: [shop, orders, duplicates, defect, data-quality]
paths: [generator/DEFECTS.md, dbt/models/staging/shop/staging__shop__orders.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Duplicates |
  - dbt/models/staging/shop/staging__shop__orders.sql::select distinct
supersedes: []
---

## Meaning

0.5% of a day's `lake.shop__orders` rows appear twice, identical in every column including
`_dt`. They are one order state written twice, not two events.

## Counts

On the 3-day CI dataset (`make dbt-ci`): 12 duplicated rows.

```sql
select count(*) as duplicated_rows
from (select order_id, updated_at, order_status, _dt
      from lake.shop__orders group by all having count(*) > 1);
```

## Terms

"Duplicate orders", "double rows". Not the same as late rows (da-0003), where the copy
arrives in a later partition.

## Data quality

Every staging model selects distinct rows, so `count(*)` on staging and warehouse is safe;
`count(*)` on the lake over-counts orders. Count orders with `count(distinct order_id)`.

---
id: da-0002
title: Exact duplicate order rows in the shop source
tags: [shop, orders, duplicates, defect, data-quality]
paths: [generator/DEFECTS.md, dbt/models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Duplicates |
  - dbt/models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql::select distinct
supersedes: []
---

## Meaning

0.5% of a day's `data_lake_layer.shop__orders` rows appear twice, identical in every column including
`_dt`. They are one order state written twice, not two events.

## Counts

On the 3-day CI dataset (`make dbt-ci`): 12 duplicated rows.

```sql
select count(*) as duplicated_rows
from (select order_id, updated_at, order_status, _dt
      from data_lake_layer.shop__orders group by all having count(*) > 1);
```

## Terms

"Duplicate orders", "double rows". Not the same as late rows (da-0003), where the copy
arrives in a later partition.

## Data quality

Every staging model selects distinct rows, so the exact copies are gone from staging. That does
not make `count(*)` an order count there: `staging__shop__orders` keeps one row per order
*state*, so an order that was placed, paid and shipped has three rows. `count(*)` counts orders
only on the current-state fact, `fact__sales__orders` (one row per order); on the lake or in
staging use `count(distinct order_id)`.

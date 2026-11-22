---
id: da-0003
title: Late order rows land in a later partition
tags: [shop, orders, late-rows, partition, defect, data-quality]
paths: [generator/DEFECTS.md, dbt/models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Late rows |
  - dbt/models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql::a late row never wins
supersedes: []
---

## Meaning

2% of a day's order rows are held back 1 to 3 days and land in a later partition, sometimes
after a newer row of the same order. Such a row has `updated_at::date < _dt`. Its status is
older than the order's current one.

## Counts

On the 3-day CI dataset (`make dbt-ci`): 10 late rows out of 2,532 order rows (the first day
cannot receive late rows, so the share is below 2%).

```sql
select count(*) filter (where updated_at::date < _dt) as late_rows,
       count(*) as order_rows
from data_lake_layer.shop__orders;
```

## Terms

"Late rows", "late-arriving data", "out-of-order updates".

## Data quality

Never take "the row from the latest partition" as current. `fact__sales__orders` picks the
latest `updated_at` (then `_dt`), so a late row never wins. At the edge of the loaded dates a
held-back row may not have arrived yet, so payments can point at an order missing from
`fact__sales__orders`; those relationship tests warn.

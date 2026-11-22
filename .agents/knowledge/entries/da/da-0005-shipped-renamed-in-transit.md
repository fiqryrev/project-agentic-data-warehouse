---
id: da-0005
title: Status shipped renamed in_transit from 2026-06-01
tags: [shop, orders, shipments, status, rename, defect, data-quality]
paths: [generator/DEFECTS.md, dbt/models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql, dbt/models/data_staging_layer/staging__shop__shipments/staging__shop__shipments.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Renamed status |
  - dbt/models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql::when order_status = 'shipped' then 'in_transit'
  - dbt/models/data_staging_layer/staging__shop__shipments/staging__shop__shipments.sql::when shipment_status = 'shipped' then 'in_transit'
supersedes: []
---

## Meaning

`order_status` and `shipment_status` say `shipped` in partitions before 2026-06-01 and
`in_transit` from 2026-06-01, late rows included. Same state, new name. Both values exist across
history, never in one partition.

## Counts

Generated and loaded 2026-05-31 and 06-01 into a scratch file (`uv run python -m generator
--start 2026-05-31 --end 2026-06-01`, then the loader): 666 `shipped` order rows on 05-31,
619 `in_transit` on 06-01, none of the other value on either day.

```sql
select _dt, order_status, count(*)
from lake.shop__orders
where order_status in ('shipped', 'in_transit')
group by all order by all;
```

## Terms

"Shipped", "in transit", "on the way". Use `in_transit` downstream.

## Data quality

Staging maps `shipped` to `in_transit` across history, so filter staging and warehouse on
`in_transit` only. A lake filter on one value misses half the history (rule: verify a literal
before filtering on it).

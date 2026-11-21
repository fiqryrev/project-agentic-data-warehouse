---
id: da-0004
title: Orphan product keys on order lines
tags: [shop, ledger, order_items, products, orphan-keys, defect, data-quality]
paths: [generator/DEFECTS.md, dbt/models/staging/shop/_staging__shop.yml]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - generator/DEFECTS.md::| Orphan keys |
  - dbt/models/staging/shop/_staging__shop.yml::ids from 9,000,000 are orphan keys
supersedes: []
---

## Meaning

About 0.2% of order lines (`shop.order_items.product_id`, and the ledger's
`invoice_lines.product_ref`) point at a product that never existed. Orphan ids start at
9,000,000. These lines are left out of seller settlements: there is no seller to pay.

## Counts

On the 3-day CI dataset (`make dbt-ci`): 3 orphan lines out of 2,971.

```sql
select count(*) filter (where product_id >= 9000000) as orphan_lines,
       count(*) as lines
from lake.shop__order_items;
```

## Terms

"Orphan keys", "unknown product", "missing product".

## Data quality

Kept in staging and warehouse; their `relationships` and `not_null` tests warn instead of
failing. An inner join to `dim__sales__products` drops these lines, so revenue by category is
slightly below total revenue. `product_version_key` is null for them.

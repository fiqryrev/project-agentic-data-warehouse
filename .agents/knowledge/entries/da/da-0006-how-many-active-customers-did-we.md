---
id: da-0006
title: "Active customer means one who ordered that day, not a valid customer version"
tags: [active, customers, orders, scd2, valid_from, label, wrong-definition]
paths: [evals/labels/processed.yaml, dbt/models/data_warehouse_layer/dim__sales__customers/dim__sales__customers.sql, dbt/models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - "evals/labels/processed.yaml::8f48413776644145a3da572fa82b7b05"
supersedes: []
---

## Meaning

A person labelled Auto Ontology's answer to "How many active customers did we have on 2026-01-05?" as `wrong_definition`
(reasoning_ok: partly). Their note: 'Active customer' means a customer who placed at least one order that day (fact__sales__orders). The chat read it as a customer whose dim__sales__customers version is valid on that date; valid_from_at/valid_to_at track changes to the customer record, not activity.

Correct answer, as labelled: 416 customers placed at least one order on 2026-01-05.

## Counts

On the snapshot of 2026-01-10 (`data/serve/analytics.duckdb`, read-only),
the labeller's correct SQL returns: [(416,)].

```sql
select count(distinct customer_id) as active_customer_count from data_warehouse_layer.fact__sales__orders where order_date = '2026-01-05'
```

## Terms

The question's words, as a person asks: "How many active customers did we have on 2026-01-05?". The chat answered:
"There were 2,120 active customers on 2026-01-05. This count is based on the dim__sales__customers table where each customer version has a validity period defined by valid_from_at and valid_to_at colum" with `SELECT COUNT(DISTINCT customer_id) as active_on_date FROM data_warehouse_layer.dim__sales__customers WHERE valid_from_at <= '2026-01-05' AND (valid_to_at IS NULL OR valid_to_at > '2026-01-05')`.

## Data quality

From label `8f48413776644145a3da572fa82b7b05` by `api` (API, 2026-11-22T09:17:27.073Z).
A proposed ontology correction is in the pull request that added this entry; nothing is changed in
Auto Ontology without a person approving it.

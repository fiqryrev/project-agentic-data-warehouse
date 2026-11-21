"""A three-model dbt project that passes every dbt checker; tests break one piece of it."""
from pathlib import Path

SOURCES = """version: 2
sources:
  - name: lake
    schema: lake
    tables:
      - name: shop__orders
        description: Shop orders.
"""

STAGING_SQL = """-- One row per order state.
select distinct order_id, order_status, amount_idr, updated_at, _dt
from {{ source('lake', 'shop__orders') }}
"""

STAGING_YML = """version: 2
models:
- name: staging__shop__orders
  description: Order states.
  columns:
  - name: order_id
    description: Order id.
  - name: order_status
    description: Order status.
  - name: amount_idr
    description: Order amount, in rupiah.
  - name: updated_at
    description: When the state was written.
  - name: _dt
    description: Partition date.
  data_tests:
  - unique_combination:
      arguments:
        columns: [order_id, updated_at]
"""

FACT_SQL = """with s as (select * from {{ ref('staging__shop__orders') }})
select
    order_id,
    order_status,
    amount_idr,
    updated_at::date as order_date,
    {{ dbt_audit_columns() }}
from s
qualify row_number() over (partition by order_id order by updated_at desc) = 1
"""

FACT_YML = """version: 2
models:
- name: fact__sales__orders
  description: Current state of each order.
  columns:
  - name: order_id
    description: Order id.
    data_tests: [unique, not_null]
  - name: order_status
    description: Latest status.
  - name: amount_idr
    description: Order amount, in rupiah.
  - name: order_date
    description: Day of the latest state.
  - name: _dbt_invocation_id
    description: dbt invocation that built this row.
  - name: _dbt_updated_at
    description: When dbt built this row.
"""

MART_SQL = """select
    order_date,
    count(*) as orders,
    sum(amount_idr) as amount_idr,
    {{ dbt_audit_columns() }}
from {{ ref('fact__sales__orders') }}
group by 1
"""

MART_YML = """version: 2
models:
- name: rpt__sales__orders__daily
  description: Orders per day.
  columns:
  - name: order_date
    description: Day.
    data_tests:
    - unique
    - not_null
  - name: orders
    description: Orders that day.
  - name: amount_idr
    description: Order amount that day, in rupiah.
  - name: _dbt_invocation_id
    description: dbt invocation that built this row.
  - name: _dbt_updated_at
    description: When dbt built this row.
"""

FILES = {
    "models/staging/_sources.yml": SOURCES,
    "models/staging/shop/staging__shop__orders.sql": STAGING_SQL,
    "models/staging/shop/_staging__shop.yml": STAGING_YML,
    "models/warehouse/sales/fact__sales__orders.sql": FACT_SQL,
    "models/warehouse/sales/_warehouse__sales.yml": FACT_YML,
    "models/mart/sales/rpt__sales__orders__daily.sql": MART_SQL,
    "models/mart/sales/_mart__sales.yml": MART_YML,
}


def make_project(root: Path, **overrides: str | None) -> Path:
    """Write the project under root. overrides: {relative path with / as __S__: text or None}."""
    files = dict(FILES)
    for key, text in overrides.items():
        path = key.replace("__S__", "/")
        if text is None:
            files.pop(path, None)
        else:
            files[path] = text
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

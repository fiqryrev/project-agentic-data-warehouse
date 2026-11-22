"""A lake table and three models that pass every dbt checker; tests break one piece of it.

Layout as in the repo: models/<layer folder>/<table>/<table>.{sql,yml,md}.
"""
from pathlib import Path

SOURCES = """version: 2
sources:
  - name: lake
    schema: lake
    tables:
      - name: shop__orders
        description: '{{ doc("shop__orders") }}'
"""

STAGING_SQL = """-- One row per order state.
select distinct order_id, order_status, amount_idr, updated_at, _dt
from {{ source('lake', 'shop__orders') }}
"""

STAGING_YML = """version: 2
models:
- name: staging__shop__orders
  description: '{{ doc("staging__shop__orders") }}'
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
  description: '{{ doc("fact__sales__orders") }}'
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
    count(*) as order_count,
    sum(amount_idr) as amount_idr,
    {{ dbt_audit_columns() }}
from {{ ref('fact__sales__orders') }}
group by 1
"""

MART_YML = """version: 2
models:
- name: rpt__sales__orders__daily
  description: '{{ doc("rpt__sales__orders__daily") }}'
  columns:
  - name: order_date
    description: Day.
    data_tests:
    - unique
    - not_null
  - name: order_count
    description: Orders that day.
  - name: amount_idr
    description: Order amount that day, in rupiah.
  - name: _dbt_invocation_id
    description: dbt invocation that built this row.
  - name: _dbt_updated_at
    description: When dbt built this row.
"""

SECTIONS = ("Potential Analyses", "Grain", "Table Lineage", "Units and Conventions",
            "Known Caveats", "Refresh Cadence", "Change History")


def doc(name: str, sections: tuple[str, ...] = SECTIONS, opening: str = "What this table holds.") -> str:
    """A doc block that passes check_bundle, with the given sections in the given order."""
    body = {"Change History": "| Version | Date | Author | Summary |\n| --- | --- | --- | --- |\n"
                              "| 1.0.0 | 2026-11-22 | data-engineering | First version. |"}
    parts = [f"{{% docs {name} %}}", "", opening, ""]
    for s in sections:
        parts += [f"## {s}", "", body.get(s, f"About {s.lower()}."), ""]
    return "\n".join(parts + ["{% enddocs %}", ""])


LAKE = "models/data_lake_layer/shop__orders/shop__orders"
STAGING = "models/data_staging_layer/staging__shop__orders/staging__shop__orders"
FACT = "models/data_warehouse_layer/fact__sales__orders/fact__sales__orders"
MART = "models/data_mart_layer/rpt__sales__orders__daily/rpt__sales__orders__daily"

FILES = {
    f"{LAKE}.yml": SOURCES,
    f"{LAKE}.md": doc("shop__orders"),
    f"{STAGING}.sql": STAGING_SQL,
    f"{STAGING}.yml": STAGING_YML,
    f"{STAGING}.md": doc("staging__shop__orders"),
    f"{FACT}.sql": FACT_SQL,
    f"{FACT}.yml": FACT_YML,
    f"{FACT}.md": doc("fact__sales__orders"),
    f"{MART}.sql": MART_SQL,
    f"{MART}.yml": MART_YML,
    f"{MART}.md": doc("rpt__sales__orders__daily"),
}


def make_project(root: Path, overrides: dict[str, str | None] | None = None) -> Path:
    """Write the project under root. overrides: {relative path: text, or None to leave it out}."""
    files = dict(FILES)
    for path, text in (overrides or {}).items():
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

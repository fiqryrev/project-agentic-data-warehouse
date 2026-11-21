select category_id, category_name, parent_name, {{ dbt_audit_columns() }}
from {{ ref('staging__shop__categories') }}

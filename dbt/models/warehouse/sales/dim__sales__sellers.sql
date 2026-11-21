select seller_id, seller_name, city, province, created_at, {{ dbt_audit_columns() }}
from {{ ref('staging__shop__sellers') }}

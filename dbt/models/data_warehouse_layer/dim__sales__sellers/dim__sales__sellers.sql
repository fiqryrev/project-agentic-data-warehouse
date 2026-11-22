select seller_id, seller_name, city_name, province_name, created_at, {{ dbt_audit_columns() }}
from {{ ref('staging__shop__sellers') }}

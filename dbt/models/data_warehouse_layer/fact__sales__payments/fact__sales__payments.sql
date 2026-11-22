select
    payment_id, order_id, payment_method_code, amount_idr, paid_at, paid_at::date as paid_date,
    {{ dbt_audit_columns() }}
from {{ ref('staging__shop__payments') }}

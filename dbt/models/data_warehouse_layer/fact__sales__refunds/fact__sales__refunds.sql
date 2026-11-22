select
    refund_id, order_id, refund_reason_code, amount_idr, refunded_at,
    refunded_at::date as refund_date,
    {{ dbt_audit_columns() }}
from {{ ref('staging__shop__refunds') }}

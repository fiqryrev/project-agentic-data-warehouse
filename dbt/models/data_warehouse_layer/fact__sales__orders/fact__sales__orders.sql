-- Current state of each order: its latest row (by updated_at; a late row never wins).
select
    order_id,
    customer_id,
    order_status,
    voucher_code,
    shipping_fee_idr,
    created_at,
    created_at::date as order_date,
    updated_at,
    {{ dbt_audit_columns() }}
from {{ ref('staging__shop__orders') }}
qualify row_number() over (partition by order_id order by updated_at desc, _dt desc) = 1

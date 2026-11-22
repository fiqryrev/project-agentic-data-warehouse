-- One row per order state the shop wrote. Exact duplicate rows are dropped; late rows stay
-- (their updated_at is older than _dt); `shipped` is renamed `in_transit` across history.
select distinct
    order_id,
    customer_id,
    case when order_status = 'shipped' then 'in_transit' else order_status end as order_status,
    voucher_code,
    shipping_fee_idr,
    created_at,
    updated_at,
    _dt
from {{ source('lake', 'shop__orders') }}

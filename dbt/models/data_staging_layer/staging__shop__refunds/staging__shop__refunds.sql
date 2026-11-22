select distinct refund_id, order_id, refund_reason as refund_reason_code, amount_idr, refunded_at, _dt
from {{ source('lake', 'shop__refunds') }}

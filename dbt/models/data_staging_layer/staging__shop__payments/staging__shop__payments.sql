select distinct payment_id, order_id, payment_method as payment_method_code, amount_idr, paid_at, _dt
from {{ source('lake', 'shop__payments') }}

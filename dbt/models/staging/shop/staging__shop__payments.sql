select distinct payment_id, order_id, payment_method, amount_idr, paid_at, _dt
from {{ source('lake', 'shop__payments') }}

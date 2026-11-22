select distinct order_item_id, order_id, product_id, quantity as item_quantity, unit_price_idr, _dt
from {{ source('lake', 'shop__order_items') }}

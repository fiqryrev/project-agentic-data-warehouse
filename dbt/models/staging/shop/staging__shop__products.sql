-- One row per product version (creation, then each price change).
select distinct
    product_id, seller_id, category_id, product_name, price_idr, created_at, updated_at, _dt
from {{ source('lake', 'shop__products') }}

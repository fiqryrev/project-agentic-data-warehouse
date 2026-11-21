select distinct seller_id, seller_name, city, province, created_at, _dt
from {{ source('lake', 'shop__sellers') }}

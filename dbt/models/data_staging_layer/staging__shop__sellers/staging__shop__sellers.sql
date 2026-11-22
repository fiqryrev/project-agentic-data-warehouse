select distinct seller_id, seller_name, city as city_name, province as province_name, created_at, _dt
from {{ source('lake', 'shop__sellers') }}

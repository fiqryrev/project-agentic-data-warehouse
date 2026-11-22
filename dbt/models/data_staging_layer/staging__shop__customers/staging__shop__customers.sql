-- One row per customer version (creation, then each move). City casing fixed.
select distinct
    customer_id,
    full_name,
    email as email_address,
    {{ title_case('city') }} as city_name,
    province as province_name,
    created_at,
    updated_at,
    _dt
from {{ source('lake', 'shop__customers') }}

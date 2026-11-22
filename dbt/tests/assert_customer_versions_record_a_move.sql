-- Every new customer version is a real move: the city differs from the previous version.
with v as (
    select
        customer_id, valid_from_at, city_name,
        lag(city_name) over (partition by customer_id order by valid_from_at) as previous_city
    from {{ ref('dim__sales__customers') }}
)
select customer_id, valid_from_at, city_name
from v
where previous_city is not null and city_name = previous_city

-- Every new customer version is a real move: the city differs from the previous version.
with v as (
    select
        customer_id, valid_from, city,
        lag(city) over (partition by customer_id order by valid_from) as previous_city
    from {{ ref('dim__sales__customers') }}
)
select customer_id, valid_from, city
from v
where previous_city is not null and city = previous_city

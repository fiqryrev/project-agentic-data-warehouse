-- Orders created per day, their current status mix and merchandise value.
with items as (
    select order_id, sum(quantity) as units, sum(line_amount_idr) as merchandise_idr
    from {{ ref('fact__sales__order_items') }}
    group by order_id
)
select
    o.order_date,
    count(*) as orders,
    count(*) filter (where o.order_status = 'cancelled') as cancelled_orders,
    count(*) filter (where o.order_status = 'delivered') as delivered_orders,
    coalesce(sum(i.units), 0) as units,
    coalesce(sum(i.merchandise_idr), 0) as merchandise_idr,
    {{ dbt_audit_columns() }}
from {{ ref('fact__sales__orders') }} o
left join items i using (order_id)
group by o.order_date

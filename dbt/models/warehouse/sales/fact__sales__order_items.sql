-- Order lines with the product version and customer version valid on the order day (the
-- shop prices a whole day at one price, so versions are matched by date).
-- Orphan product keys keep a null product_version_key. Lines arrive on the order's creation
-- day, so their _dt is the order date even when the order row itself is late; an order row
-- that has not arrived yet leaves customer_id and customer_version_key null until it does.
with orders as (
    select order_id, customer_id, created_at, created_at::date as order_date
    from {{ ref('staging__shop__orders') }}
    qualify row_number() over (partition by order_id order by updated_at) = 1
)
select
    i.order_item_id,
    i.order_id,
    coalesce(o.order_date, i._dt) as order_date,
    i.product_id,
    p.product_version_key,
    o.customer_id,
    c.customer_version_key,
    i.quantity,
    i.unit_price_idr,
    i.quantity * i.unit_price_idr as line_amount_idr,
    {{ dbt_audit_columns() }}
from {{ ref('staging__shop__order_items') }} i
left join orders o using (order_id)
left join {{ ref('dim__sales__products') }} p
    on p.product_id = i.product_id
    and coalesce(o.order_date, i._dt) >= p.valid_from::date
    and (p.valid_to is null or coalesce(o.order_date, i._dt) < p.valid_to::date)
left join {{ ref('dim__sales__customers') }} c
    on c.customer_id = o.customer_id
    and o.order_date >= c.valid_from::date
    and (c.valid_to is null or o.order_date < c.valid_to::date)

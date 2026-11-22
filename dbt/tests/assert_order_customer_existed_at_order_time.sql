-- Every order line resolves to the customer version valid when the order was placed.
select i.order_item_id
from {{ ref('fact__sales__order_items') }} i
join {{ ref('fact__sales__orders') }} o using (order_id)
left join {{ ref('dim__sales__customers') }} c using (customer_version_key)
where c.customer_version_key is null
   or o.created_at < c.valid_from_at
   or (c.valid_to_at is not null and o.created_at >= c.valid_to_at)

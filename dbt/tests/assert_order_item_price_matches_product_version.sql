-- History check: every order line was priced at the product version valid on its order day.
select i.order_item_id, i.unit_price_idr, p.price_idr
from {{ ref('fact__sales__order_items') }} i
join {{ ref('dim__sales__products') }} p using (product_version_key)
where i.unit_price_idr <> p.price_idr

-- Product history: one row per price version, valid until the next price change.
with versions as (
    select * from {{ ref('staging__shop__products') }}
)
select
    md5(p.product_id::varchar || '|' || p.updated_at::varchar) as product_version_key,
    p.product_id,
    p.product_name,
    p.seller_id,
    p.category_id,
    c.category_name,
    c.parent_name,
    p.price_idr,
    p.created_at,
    p.updated_at as valid_from,
    lead(p.updated_at) over (partition by p.product_id order by p.updated_at) as valid_to,
    lead(p.updated_at) over (partition by p.product_id order by p.updated_at) is null as is_current,
    {{ dbt_audit_columns() }}
from versions p
left join {{ ref('staging__shop__categories') }} c using (category_id)

-- Customer history: one row per version, valid from the moment the shop wrote it until the
-- next version. Built from the lake's history, so a backfill rebuilds the same history.
with versions as (
    select * from {{ ref('staging__shop__customers') }}
)
select
    md5(customer_id::varchar || '|' || updated_at::varchar) as customer_version_key,
    customer_id,
    full_name,
    email_address,
    city_name,
    province_name,
    created_at,
    updated_at as valid_from_at,
    lead(updated_at) over (partition by customer_id order by updated_at) as valid_to_at,
    lead(updated_at) over (partition by customer_id order by updated_at) is null as is_current,
    {{ dbt_audit_columns() }}
from versions

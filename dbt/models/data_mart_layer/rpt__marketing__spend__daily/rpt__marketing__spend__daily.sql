-- Spend per day and channel.
select
    spend_date,
    channel_name,
    sum(spend_idr) as spend_idr,
    sum(impression_count) as impression_count,
    sum(click_count) as click_count,
    case when sum(click_count) > 0 then sum(spend_idr) / sum(click_count) end as cost_per_click_idr,
    {{ dbt_audit_columns() }}
from {{ ref('fact__marketing__daily_spend') }}
group by spend_date, channel_name

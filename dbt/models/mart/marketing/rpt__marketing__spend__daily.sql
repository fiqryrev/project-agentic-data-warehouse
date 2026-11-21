-- Spend per day and channel.
select
    spend_date,
    channel,
    sum(spend_idr) as spend_idr,
    sum(impressions) as impressions,
    sum(clicks) as clicks,
    case when sum(clicks) > 0 then sum(spend_idr) / sum(clicks) end as cost_per_click_idr,
    {{ dbt_audit_columns() }}
from {{ ref('fact__marketing__daily_spend') }}
group by spend_date, channel
